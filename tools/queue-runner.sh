#!/usr/bin/env bash
# codex-queue-runner — drain the actionable queue with one `codex exec`
# session per work item, each in an isolated git worktree, with a bounded
# concurrency cap. A pass covers BOTH kinds of actionable work:
#   - issues with no open PR yet   -> implementation session
#   - existing non-draft open PRs  -> finisher session (reviews, CI, merge) The model never waits in a poll loop: CI waits happen
# inside the session via blocking `gh pr checks --watch` calls, and queue
# scheduling lives here, outside any LLM context.
#
# Configuration (env):
#   QUEUE_REPO         required  owner/repo, e.g. majiayu000/remem
#   QUEUE_CHECKOUT     required  path to the local clone
#   QUEUE_CONCURRENCY  default 2 parallel issue sessions
#   QUEUE_LIMIT        default 6 max issue sessions started per run
#                      (skipped issues do not consume the limit)
#   QUEUE_LABEL        optional  only issues/PRs with this label
#   QUEUE_CODEX_BIN    default codex
#   QUEUE_CODEX_FLAGS  default "--full-auto"
#   QUEUE_RUN_DIR      default ~/.codex/queue-runner/runs/<timestamp>
set -euo pipefail

REPO=${QUEUE_REPO:?set QUEUE_REPO (owner/repo)}
CHECKOUT=${QUEUE_CHECKOUT:?set QUEUE_CHECKOUT (local clone path)}
CONCURRENCY=${QUEUE_CONCURRENCY:-2}
LIMIT=${QUEUE_LIMIT:-6}
LABEL=${QUEUE_LABEL:-}
SKIP_LABELS=${QUEUE_SKIP_LABELS:-parked}
SESSION_TIMEOUT=${QUEUE_SESSION_TIMEOUT:-10800}
CODEX_BIN=${QUEUE_CODEX_BIN:-codex}
CODEX_FLAGS=${QUEUE_CODEX_FLAGS:---full-auto}
RUN_DIR=${QUEUE_RUN_DIR:-$HOME/.codex/queue-runner/runs/$(date +%Y%m%d-%H%M%S)}

mkdir -p "$RUN_DIR"
echo "run dir: $RUN_DIR"

# Fresh remote truth before mapping the queue (anti-duplication baseline).
git -C "$CHECKOUT" fetch origin --prune --quiet

# Fetch a larger candidate pool; skips (already-referenced issues) must not
# consume the session limit.
POOL=$(( LIMIT * 5 > 30 ? LIMIT * 5 : 30 ))
list_args=(issue list --repo "$REPO" --state open --limit "$POOL" --json number,labels)
[ -n "$LABEL" ] && list_args+=(--label "$LABEL")
skip_re=$(printf '%s' "$SKIP_LABELS" | tr ',' '|')
issues=$(gh "${list_args[@]}" \
  --jq ".[] | select([.labels[].name | test(\"^(${skip_re})\$\")] | any | not) | .number")

# In-flight work detection: an open PR referencing the issue, or a remote
# branch named for it (another session may be mid-flight before its PR).
remote_branches=$(git -C "$CHECKOUT" ls-remote --heads origin 2>/dev/null | awk '{print $2}')

# Skip issues that already have an open PR referencing them.
open_pr_text=$(gh pr list --repo "$REPO" --state open --limit 100 \
  --json number,title,body,headRefName \
  --jq '.[] | "\(.title) \(.body) \(.headRefName)"')

# Snapshot existing non-draft open PRs BEFORE launching issue workers so a
# PR opened by a worker in this pass never gets a duplicate finisher
# session. Drafts are filtered server-side so the fetch limit only spends
# slots on finishable PRs.
pr_pool=$(gh pr list --repo "$REPO" --state open --search "draft:false" \
  --limit "$POOL" --json number,title,body,headRefName,labels \
  --jq '.[] | "\(.number)\t,\(.labels | map(.name) | join(",")),\t\(.title) \(.body // "" | gsub("\\s+"; " ")) \(.headRefName)"')
if [ -n "$LABEL" ]; then
  # Label runs finish PRs that carry the label themselves PLUS PRs linked
  # to the selected labeled issues (issue labels are not mirrored to PRs).
  open_prs=""
  while IFS=$'\t' read -r pr_num pr_labels pr_text; do
    [ -n "$pr_num" ] || continue
    if printf '%s' "$pr_labels" | grep -qF ",$LABEL,"; then
      open_prs="$open_prs $pr_num"
      continue
    fi
    for i in $issues; do
      if printf '%s' "$pr_text" | grep -qE "(#$i\b|gh$i\b|GH$i\b)"; then
        open_prs="$open_prs $pr_num"
        break
      fi
    done
  done <<<"$pr_pool"
  open_prs=$(printf '%s\n' $open_prs | sort -un)
else
  open_prs=$(printf '%s\n' "$pr_pool" | cut -f1)
fi

# PR-only queues are still actionable: only exit when neither exists.
[ -n "$issues" ] || [ -n "$open_prs" ] || { echo "no actionable issues or PRs"; exit 0; }

run_session() {
  # run_session <wt> <log> <prompt> — codex exec with a watchdog timeout.
  local wt=$1 log=$2 prompt=$3 status=0
  (cd "$wt" && "$CODEX_BIN" exec $CODEX_FLAGS "$prompt") >>"$log" 2>&1 &
  local cpid=$!
  ( sleep "$SESSION_TIMEOUT" && kill "$cpid" 2>/dev/null \
      && echo "[watchdog] session killed after ${SESSION_TIMEOUT}s" >>"$log" ) &
  local wpid=$!
  wait "$cpid" || status=$?
  kill "$wpid" 2>/dev/null
  return "$status"
}

run_pr() {
  local n=$1
  local wt="$RUN_DIR/wt-pr$n"
  local log="$RUN_DIR/pr$n.log"
  echo "[pr$n] start -> $log"
  if ! git -C "$CHECKOUT" worktree add --detach "$wt" origin/main \
      >>"$log" 2>&1; then
    echo "[pr$n] worktree add failed"; return 1
  fi
  local prompt="implx auto: bounded_tranche, only existing PR #$n of $REPO. \
Finish this PR: gh pr checkout $n, address unresolved review threads, run \
focused checks, wait for CI with a single blocking \
'gh pr checks $n --repo $REPO --watch --fail-fast', and merge on complete \
green evidence (with issue closure semantics). If evidence gaps need a \
human, report and stop. Do not touch any other PR or issue. Run builds \
and tests only inside this worktree."
  local status=0
  run_session "$wt" "$log" "$prompt" || status=$?
  git -C "$CHECKOUT" worktree remove --force "$wt" >>"$log" 2>&1 || true
  echo "[pr$n] done exit=$status"
  return "$status"
}

run_issue() {
  local n=$1
  local wt="$RUN_DIR/wt-gh$n"
  local log="$RUN_DIR/gh$n.log"
  echo "[gh$n] start -> $log"
  if ! git -C "$CHECKOUT" worktree add --detach "$wt" origin/main \
      >>"$log" 2>&1; then
    echo "[gh$n] worktree add failed"; return 1
  fi
  local prompt="implx auto: bounded_tranche, only issue #$n. Do the full \
flow inside this worktree (spec coverage, implementation, PR, blocking CI \
wait via 'gh pr checks <n> --repo $REPO --watch --fail-fast', reviewer \
lane, merge on green evidence). Do not touch any other issue. Run cargo \
only inside this worktree."
  local status=0
  run_session "$wt" "$log" "$prompt" || status=$?
  git -C "$CHECKOUT" worktree remove --force "$wt" >>"$log" 2>&1 || true
  echo "[gh$n] done exit=$status"
  return "$status"
}

fail=0
started=0
# Existing non-draft open PRs (snapshotted above) get finisher sessions
# FIRST so a steady stream of new issues cannot starve older PRs of the
# shared session budget.
for n in $open_prs; do
  [ "$started" -ge "$LIMIT" ] && break
  started=$((started + 1))
  while [ "$(jobs -rp | wc -l)" -ge "$CONCURRENCY" ]; do
    wait -n || fail=1
  done
  run_pr "$n" &
done
for n in $issues; do
  [ "$started" -ge "$LIMIT" ] && break
  if printf '%s' "$open_pr_text" | grep -qE "(#$n\b|gh$n\b|GH$n\b)"; then
    echo "[gh$n] skip: open PR already references it"
    continue
  fi
  if printf '%s' "$remote_branches" | grep -qiE "gh-?$n([^0-9]|\$)"; then
    echo "[gh$n] skip: remote branch already exists for it"
    continue
  fi
  started=$((started + 1))
  while [ "$(jobs -rp | wc -l)" -ge "$CONCURRENCY" ]; do
    wait -n || fail=1
  done
  run_issue "$n" &
done

while [ "$(jobs -rp | wc -l)" -gt 0 ]; do wait -n || fail=1; done

git -C "$CHECKOUT" worktree prune
pass_tokens=0
for log in "$RUN_DIR"/*.log; do
  [ -f "$log" ] || continue
  t=$(awk '/^tokens used/{getline; gsub(/[^0-9]/,""); v=$0} END{print v}' "$log")
  case "$t" in ''|*[!0-9]*) ;; *) pass_tokens=$((pass_tokens + t));; esac
done
echo "queue pass complete: tokens=$pass_tokens (logs: $RUN_DIR)"
exit "$fail"
