# Product Spec

## Linked Issue

GH-63
status: legacy

## User Problem

`gh pr merge --delete-branch` fails repeatedly when a local worktree still
owns the PR head branch (or main). Audited sessions across sage/rui/loom show
merges wrongly reported as failed, stale worktrees left behind
(`/Users/apple/.codex/worktrees/79d8/rui`), and the workaround living only in
per-session tribal memory notes ("Do not treat a failing local `gh pr merge`
as evidence that merge failed; another worktree may still own the branch") —
see GH-63 issue body for rollout file paths. The same trap recurs because no
skill documents a safe merge path. Related: #55 covers branch-naming and
duplicate-PR discipline; this issue covers the merge-stage symptom of the
same branch-lifecycle problem.

## Goals

- Define one documented, portable merge path that is immune to local
  worktree/branch ownership: neutral cwd + `--repo`, with a
  `gh api -X PUT /repos/{owner}/{repo}/pulls/{n}/merge` fallback.
- Make remote API state the only source of truth for merge success/failure.
- Add post-merge worktree cleanup (prune + report) to the closure phase.

## Non-Goals

- No wrapper tooling or scripts shipped by SpecRail; this is contract text
  plus evidence fields (SpecRail remains a contract pack).
- No change to merge authorization or gate requirements (GH-57/58/59 own
  those).
- No management of worktrees created by other tools beyond prune-and-report.

## Behavior Invariants

1. The merge step is executed from a neutral cwd (not inside any worktree of
   the target repo) and always passes `--repo <owner>/<repo>` explicitly.
2. If `gh pr merge` fails with a local branch/worktree ownership error, the
   agent falls back to `gh api -X PUT /repos/{owner}/{repo}/pulls/{n}/merge`
   (pure API path, never touches local branches).
3. Merge success or failure is determined solely by querying the remote PR
   state after the attempt; a failing local `gh pr merge` invocation is never
   recorded as "merge failed" without that query.
4. Post-merge closure runs worktree cleanup: `git worktree prune` plus an
   explicit list of removed/stale worktrees in the closure report.
5. The merge evidence records which path executed (`gh_pr_merge` |
   `api_fallback`) and the post-merge remote confirmation (merged flag +
   merge commit SHA).

## Acceptance Criteria

- [ ] `skills/specrail-implement-queue/SKILL.md` (merge/closure section)
      documents the full path: neutral cwd + `--repo`, API fallback, remote
      confirmation, worktree prune.
- [ ] The contract states explicitly that local `gh pr merge` failure is not
      evidence of merge failure; remote state is authoritative.
- [ ] pr_gate / closure-audit evidence includes `merge_path` and remote
      confirmation fields; the gate rejects merge records lacking remote
      confirmation.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- API fallback also fails (permissions, ruleset, required checks): record
  the API error verbatim; the item stays unmerged and reports the blocker —
  no retry loops that mask policy failures.
- `--delete-branch` semantics under the API fallback: branch deletion is a
  separate follow-up call and may legitimately fail while the merge
  succeeded; evidence keeps merge and branch-deletion outcomes separate.
- Race: another actor merges between the failed local attempt and the
  fallback: the remote-state query resolves it; record `merged_by_other`.
- Repos with merge-queue or required merge methods: the fallback must pass
  the repo's allowed merge method (e.g. squash); the contract requires
  reading the repo merge settings, not hardcoding a method.

## Rollout Notes

Contract text plus additive evidence fields. This intentionally replaces
per-session memory notes; once merged, those notes should be retired in the
consuming repos. CHANGELOG notes that closure audits now expect merge-path
evidence.
