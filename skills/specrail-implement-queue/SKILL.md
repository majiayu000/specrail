---
name: specrail-implement-queue
description: Use ONLY when explicitly delegated by the implx skill or when the user names this skill (specrail-implement-queue) directly. Do not self-activate from descriptive language about optimizing a repository, finishing issues, draining work, or making many PRs — without an explicit implx or by-name invocation, follow the repository's AGENTS.md conventions as a normal agent instead. When invoked, implements or drains a GitHub issue/PR queue in a SpecRail-governed repository where approved specs already exist: maps issues to specs and existing PRs, supports full-queue drain requests from implx, selects single-agent or optional threads orchestration, preserves partial versus final closing semantics, and requires SpecRail verification plus PR gates before merge-readiness claims.
---

# SpecRail Implement Queue

Use this skill for approved-spec implementation queues. For one small issue,
route to `skills/specrail-implement/SKILL.md` instead.

## Startup

1. SpecRail startup: read `AGENTS.md`, `AGENT_USAGE.md`, `workflow.yaml`,
   `states.yaml`, `labels.yaml`, `skills/specrail-workflow/SKILL.md` when
   present; select the locale; identify the `implement` route and human gates.
2. Fetch remote state; list open issues/PRs, local branch, dirty files,
   worktrees. Exclude items carrying a `QUEUE_SKIP_LABELS` label (default:
   `parked`), open PRs whose linked issue carries one, and draft PRs; report
   skips once in `human_decisions`, never re-enter them in-run (including
   after compaction); a skip label wins over any actionable label.
3. Per candidate issue, read the issue and `specs/GH<n>/{product,tech,tasks}.md`;
   map existing PRs before creating replacement PRs.
4. Duplicate-work evidence before opening an implementation lane:

```sh
python3 checks/github_duplicate_evidence.py --github-repo <owner/repo> --issue <n> --json > duplicate-work-evidence.json
python3 checks/route_gate.py --repo . --route implement --issue <n> --state ready_to_implement --duplicate-evidence duplicate-work-evidence.json --json
```

Missing evidence → human input. Open PR for the issue → blocked. Matching
remote branch only → ownership decision: `review` stop and ask; `auto` skip
to `human_decisions` and keep draining.

## Spec Coverage Gate

Classify by the canonical `spec_status` values (`checks/specrail_lib.py`
`SPEC_STATUSES`). Scope: `full_queue_drain` classifies every open issue and
linked PR; `bounded_tranche` classifies only the target issue(s) and their
linked PRs — never the whole repository.

- `complete`: all three spec files exist and `product.md` is not
  `status: legacy` (GH142); a legacy packet is NOT complete.
- `needs_tasks`: product and tech exist, `tasks.md` missing.
- `needs_spec`: product or tech missing, or packet is `status: legacy` (a
  depth-gate-passing rewrite is the only way to shed the marker).
- `umbrella_covered`: another complete GH spec explicitly includes the issue.
- `exception_allowed`: dependency bump, focused CI fix, docs-only
  correction, or another explicitly justified small non-spec change.

Only `complete`, `umbrella_covered`, or `exception_allowed` are candidates;
route the rest to spec-writing/task-planning first. Never implement from
issue text, PR comments, or old chat context unless the user authorizes a
non-spec exception recorded in the checkpoint.

### Done-When Gate

A candidate also needs a decidable completion criterion: an enumerated
checklist, pass/fail acceptance criteria, or a closing verification command.
Otherwise classify `needs_scope` (signals: "backlog", "edge cases as
discovered", 补齐, 持续优化 — open-ended issues regenerate work forever under
compaction). Routing: `auto` — never implement; skip with reason
`no decidable done-when`, never auto-apply readiness labels; `review` — ask
the human to scope or park. Rescoping into a finite checklist is valid queue
work, but the checklist is a human gate in both modes: auto drafts, never
self-approves.
Spec drafting: `auto` (explicit `implx auto` only) drafts missing packets
with the spec-writing skill's own gates and continues to implementation
in-run (subject to the Spec/Impl Mix Gate), escalating only architecture
rewrites or evidence-starved specs; `review` drafts, then waits for human
confirmation. Readiness labels: `auto` may add a missing label to
`complete`/`umbrella_covered` issues (record
`readiness_label_source: auto_drain`, list all auto-applied labels), never
to `needs_spec`/`needs_tasks`/legacy packets; in `review` they remain a
human gate. In `full_queue_drain`, `needs_spec`/`needs_tasks` are
actionable planning work: with no implementation-ready tranche, select the
smallest spec/task tranche instead of ending the drain (unless the user
limited the run to implementation-only work or a human gate blocks it).

## PR Tier Lanes

Classify every candidate into `pr_tier` before planning PRs; tier decides
process weight, gates stay identical.

- `heavy`: architecture, schema/migration, security surfaces, cross-module
  rewrites, spec-marked high risk. Two PRs: spec first, then impl.
- `standard`: normal feature/fix. ONE `mixed_impl` PR carrying spec delta
  plus implementation; no separate spec-only PR.
- `fastlane`: ≤50 changed lines, no protected paths (API schema, migrations,
  auth/security code, CI workflow definitions). One PR; spec content may
  live in the PR description when gates accept `exception_allowed`.

Record `pr_tier` with current-head adapter evidence (changed-line count,
complete touched paths, `source: github_changed_files`, head SHA, path
digest) — self-declaration is never evidence. When in doubt, pick the
heavier tier (authorization included). Tiering never weakens CI,
review-thread, or pr_gate evidence; the only substitution is `fastlane`
self-review under `basis: fastlane_policy` (see Orchestration).

## Queue Planning

One issue per implementation PR by default; `standard`/`fastlane` spec
content travels in the same `mixed_impl` PR; multiple PRs per issue only
when the task plan or risk justifies slices; combined PRs only when specs
share one acceptance surface; `Refs #<issue>` for partial slices; closing
keywords only for the final slice satisfying every acceptance criterion.
Gate partial slices with `--issue <n>` on the evidence adapter. Deprecation
windows in auto: default to the next minor release, record
`deprecation_default: true` on the item and PR description, continue.
Record the plan as the `specrail_implementation_queue` YAML shape in
`templates/queue_plan.yaml` (objective, modes, spec coverage, per-issue
plan, gates, context budget ratios 0.50/0.65/0.75, checkpoint, stop policy).
Default `auth_mode: review` when not provided; never promote to auto from
persisted configuration. Broad queues execute as bounded tranches: from
`implx` (or an ask to finish actionable issues/PRs) set
`queue_mode: full_queue_drain` unless the prompt limits scope; pick the
smallest mergeable tranche, checkpoint, repeat until drained or every
remaining item is blocked/deferred/waiting/needs-human. A blocked tranche
does not stop the drain — checkpoint, refresh remote truth, pick an
independent tranche. Stop only when every remaining item has `spec_status`,
`blocker`, and `next_action` in `remaining_queue`. Without explicit
full-drain authorization, do the smallest tranche and checkpoint the rest.

Spec/Impl mix gate:
classify every created PR as `pr_kind`: `spec` (specs/docs/planning only),
`impl` (production code or tests), `mixed_impl` (any production code). More
than 3 consecutive `spec` PRs is a blocking violation unless the user
confirmed a spec-only tranche (quoted `spec_only_declaration`). Non-PR items
don't reset the streak; `impl`/`mixed_impl` do. Maintain `tranche_mix`
counters (`spec_pr_count`, `impl_pr_count`, `consecutive_spec_only`);
`checks/runtime_ledger_gate.py` cross-checks. Never present spec PR counts
as implementation progress.

## Orchestration

Use `integrations/threads.md` and an available threads skill for parallel
lanes, review/CI/merge gates, or closure audit; native dispatch is required
for GitHub queues when available. Before implementation, review, push,
comment, or merge, record the `thread_dispatch_gate` object (shape in
`templates/tranche_checkpoint.md`) once in the runtime checkpoint;
handoffs/reports reference it, never copy. When
`spawn_requirement: required`, dispatch the planned bounded lanes. PR merge
work needs a real read-only `reviewer`/`merge_reviewer` thread with
`agent_id_or_thread_id`, wait/close evidence, and output; the coordinator
is not that reviewer.
Fastlane exception: only exact-head GitHub evidence proving ≤50 changed
lines, no protected paths, and `enforcement_sensitive: false` may use
`basis: fastlane_policy`: the coordinator records
`review_source: self_review`, a schema-valid exact-head local
artifact/manifest, scope, and conversation marker; `lane_failures[]` is not
required, every other PR-gate class is; runtime copies the allowed tier/
sensitivity evidence exactly. Otherwise the native reviewer requirement
stands. If threads is unavailable, record `fallback_mode: single_agent`
with reason and report that no native threads launched.

Spawn every lane with a minimal context pack: task statement, exact diff or
branch ref, linked spec packet paths, compact carry. Never fork coordinator
history into a lane (`fork_turns: all` and equivalents forbidden for every
role); a lane needing more gets explicit file paths. Planner/reviewer lanes
are read-only (low effort when configurable); worker lanes own disjoint
files; shared verification belongs to one coordinator; dependent specs run
serially; builds/tests run only in the lane's worktree, one at a time.

## Bounded Review Contract And Reviewer Lanes

Use the canonical manifest-v2 `bounded_diff_v1` contract in
`skills/specrail-review-pr/SKILL.md`; do not copy it here. Load that Skill
before review; `checks/review_json_gate.py` plus
`checks/review_result_semantics.py` remain the deterministic authority.

One reviewer lane per PR is the default and satisfies review for `fastlane`
and `standard`; do not stack extra lanes (mechanical audit, cross-review,
adversarial, re-review). Multiple lanes only for `heavy`, an explicit human
request, or a recorded lane failure forcing a retry. Artifact-defect repair
is not review: when a review artifact fails schema/manifest validation but
the review output exists, regenerate the artifact and re-run
`checks/review_json_gate.py` only — no new round, no test re-run, no fresh
GitHub evidence for an unchanged head.
Give the reviewer only the exact diff, linked spec packet, and compact
carry. Resume/message first; otherwise dispatch the next bounded `diff_only`
lane. One bounded wait plus one stop request precedes `zero_output`. Record
every usage-limit/crash/zero-output/early-close in `lane_failures[]` (lane
id, kind, optional `other`, marker); downgrade to `blocked`/`needs_human`
with `blocked_reason: reviewer_lane_failure`. Recover via a different local
lane or authorized local `self_review` (actor, source, quoted scope,
marker); generic authorization cannot substitute. Two distinct recorded lane
failures let `implx auto` authorize scoped self-review; one requires retry;
review mode has no exception. The `basis: fastlane_policy` path is separate
and needs no lane failures. In `review` mode a fastlane self-review item
cannot reach `standard_auto` (no independent party) and keeps per-PR human
authorization; in `auto`, standing authorization covers it once evidence is
green.

## Context Budget And Bounded Tranche Hard Stop

Record a parent context budget before spawning lanes — defaults: soft stop
50%, hard 65%, critical 75% of the active window (record overrides). Soft:
no new lanes or scope. Hard: finish the current critical step, checkpoint,
hand off. Critical: checkpoint and resume instructions only. A hard-stop
handoff in `full_queue_drain` preserves the full objective and next tranche.

`full_queue_drain` is a sequence of bounded tranches, each declaring a hard
budget at tranche start in the checkpoint `budget` object
(checkpoint_version 2): `basis: compaction | item_cap | both` (compaction is
the primary signal; use `item_cap` where unavailable); `compaction_budget`
default 1; `item_cap` default 3 in auto (`item_cap: 1` needs a recorded
`item_cap_reason`); record observed `compaction_count`. Budget exhaustion
ends the tranche, not necessarily the session: write
`stop_reason: budget_exhausted` plus `resume_prompt`, then either
Same-Session Tranche Rollover (`auto` + basis `item_cap` +
`compaction_count` ≤ `compaction_budget` + context below soft stop: declare
the next `tranche_id` with a fresh budget and keep draining — not a
`budget_override`), or fresh-session handoff in every other case, leading
with the copy-paste `resume_prompt`.
Goal/session decoupling: a thread goal never exempts a session/tranche from
the compaction budget. The goal persists (stable `goal_id`); the session
does not. At compaction budget, goal active or not: checkpoint (increment
`tranche_id`, record `tranche_started_at`, `tranche_session_offset`), lead
with `resume_prompt`, hand off; the new session resumes under the same
`goal_id` from checkpoint plus fresh remote truth; counters restart,
historical tranche records are append-only.

checkpoint_version 3 adds trusted counters and four hard dimensions —
`max_wall_clock_minutes` (120), `max_tool_calls` (250),
`max_review_correction_rounds` (2), `max_full_test_runs_per_head` (1, bound
to `full_test_head_sha`) — blocking on `observed > limit`;
`telemetry_source: unavailable` forbids `basis: compaction`/`both`.
Continuing past any exceeded dimension needs an explicit user override with
quoted scope and marker (`budget_override` v2, per-dimension
`budget_overrides` v3); `checks/runtime_ledger_gate.py` blocks over-budget
continuation without one and drain checkpoints declaring no budget.
Reviewer lanes stay bounded and do not inherit the parent budget.

After every compaction, in order: run `python3 -m checks.session_telemetry
<session-jsonl> --tranche-start-offset <tranche_session_offset>`; write
`observed_compaction_count`, `telemetry_source`,
`last_compaction_window_id` into the budget; re-read the checkpoint;
refresh remote truth; run `checks/runtime_ledger_gate.py` and obey it.
Never read raw `~/.codex/sessions` logs or old transcripts as queue state —
the only permitted session-jsonl access is `checks/session_telemetry.py`
(counters, never content).
Same-issue circuit breaker:
bounds one issue across tranches/sessions. Before opening an implementation
lane, check remote truth: trip on any of ≥5 commits referencing the issue
without closure, ≥3 consecutive near-identical commit-message prefixes
targeting it, or ≥3 prior checkpoint tranches on it without closure. When
tripped: no lane — `auto` applies `parked` to the issue and its PRs,
converts PRs to draft, records evidence in `human_decisions`, keeps
draining; `review` stops and presents the evidence. Re-entry only after a
human removes `parked`; no auto override.

## Cost Discipline: Output Firewall, Turn Batching, Waiting

Output firewall: large-output commands run only with raw stdout/stderr
going to artifact files (`artifacts/logs/<tranche>/...`); the coordinator
reads exit code, short tail, targeted grep, and the artifact path. No raw
`gh run view --log`, full test output, or broad `rg`/`git grep` across
`.codex`, `.claude`, `target`, `node_modules`, session JSONL, or logs in
parent context; parent stdout tail and subagent final output ≤150 lines.

Turn batching: turn count is a first-order cost (every turn re-sends the
history). Batch consecutive read-only steps into one scripted call with
output to an artifact; combine patch set plus focused check into as few
calls as tooling allows; target <500 turns per single-PR session (>1000
without a merge is a stall — checkpoint and prefer a fresh scoped session);
never spend a turn on a no-op poll or unchanged re-read.

Waiting: wait inside a single blocking tool call, never a model-driven poll
loop (openai/codex#13733). CI: `gh pr checks <n> --repo OWNER/REPO --watch
--fail-fast` or `gh run watch <run-id> --exit-status`. Long local checks:
foreground with adequate timeout, output to artifact. Reviewer lanes: one
bounded wait plus one stop request. Through `exec_command`/`wait` sessions,
request the maximum yield (`background_terminal_max_timeout`), growing
exponentially across waits.

Test layering: focused tests during iteration; the full suite plus
deterministic checks once, immediately before claiming PR-ready — the one
run counted by `max_full_test_runs_per_head`; record `full_test_head_sha`.
A review-fix head does NOT restart the full-suite obligation: focused tests
plus the PR's green CI rollup are full-coverage evidence for that head;
re-run locally only when CI lacks full-suite coverage or the fix touched
build/test configuration. Exact-head discipline governs evidence records,
not re-execution.

## Runtime Checkpoint

Create/update the local checkpoint at three required points: tranche start
(before the first writable action), before claiming merge readiness (the
ledger-gate evaluation point), and tranche end (compaction, handoff, close,
or next-tranche selection). Between them, update only on material change
(new PR, lane failure, budget event). Shape:
`templates/tranche_checkpoint.md`; validate with
`python3 checks/runtime_ledger_gate.py --checkpoint
.specrail/runtime/current.json`. The checkpoint is a local handoff layer;
GitHub and spec packets are the durable truth. For `full_queue_drain`,
record the overall objective, spec coverage, current tranche, completed
items, remaining queue, blockers, and next resume action;
`needs_spec`/`needs_tasks`/`eligible_impl`/`waiting_ci`/`needs_review` do
not count as drained under status `complete`. Resume from checkpoint plus
fresh remote truth only.

Goal use — auto drain (all of: `auth_mode: auto`, `queue_mode: full_queue_drain`, goal
capability available): create a thread goal at startup stating the whole
drain objective, the four termination conditions (queue empty or fully
blocked, token budget exhausted, user interrupt, only `human_decisions`
remaining), and per-turn re-anchoring from checkpoint plus fresh remote
truth; record a token budget in the checkpoint `goal` object. Every other
case: no goal; record a `goal_candidate`. Never mark the goal complete
while actionable items remain; on budget exhaustion, checkpoint and hand
off leading with `resume_prompt`. Goal status never substitutes for the
checkpoint, GitHub truth, or gates.

## Implementation, Review And Verification

Per issue slice: use `skills/specrail-implement/SKILL.md`; search before
adding files/APIs/assets/schemas; run duplicate-work evidence and the
implement route gate before creating a PR; implement only acceptance
criteria from the linked spec and task plan; add tests proving the changed
behavior; machine identifiers in English, human-facing text in the locale.

Before readiness: focused tests, repository deterministic checks,
`python3 checks/check_workflow.py --repo .` (plus `--spec-dir specs/GH<n>`
when specs changed), applying the test layering above. Compare the diff with
linked specs via `skills/specrail-check-impl-against-spec/SKILL.md`, then
use `skills/specrail-pr-gate/SKILL.md` before reporting merge readiness.
The complete GitHub PR evidence class list (head, CI rollup, review
decision, merge state, closing intent, reviewer/thread evidence with
terminal `review_execution: local`, `review_source`, `lane_failures[]`,
`self_review_authorization`, GraphQL threads with resolver roles, serial
gate query timestamp/head, `pr_tier` evidence, authorization fields) is
defined once in `skills/specrail-pr-gate/SKILL.md`; do not restate it. The
checkpoint must not mark a PR `complete`/`merged`/`merge_ready` unless
`checks/runtime_ledger_gate.py` accepts it with `pr_gate.evidence` present
and evaluating to `allowed`.

### Merge Authorization

Mode selection and evidence details: `skills/implx/SKILL.md` and
`skills/specrail-pr-gate/SKILL.md`; runtime enforcement:
`checks/runtime_ledger_gate.py`. `auto` exists only after the current user
says `implx auto` / `implx 自动`; its standing authorization applies only
when every evidence class is green; gaps go to `remaining_queue`; it is
never self-review authorization. In `review`, `standard_auto` needs
non-sensitive `fastlane`/`standard` tier evidence, the same green classes,
and independent substantiation (gate-verifiable CI tier check or an
`independent_lane` artifact's matching `{pr_tier, attested: true, basis}`);
record `authorization_tier: standard_auto`,
`merge_authorization.source: tier_policy_gh143`. Self-review never
qualifies. Heavy/sensitive/unknown tiers use `heavy_manual` with per-PR
human actor/source. Missing evidence, malformed artifacts, CI/attestation
disagreement, or `tier_dispute: true` fails closed; only
reviewer/merge-reviewer or human roles resolve a dispute; tier
authorization never fills another evidence gap.

Graded re-confirmation (GH-143) for post-authorization findings: mechanical
findings (severity ≤ `important`, no intent/path/contract change) stay
authorized — fix, independently re-review the post-fix head, record
`finding_ref`, `severity`, `mechanical`, `disposition: fixed_re_reviewed`.
Any critical or intent/path/contract-expanding fix pauses merge and voids
the authorization until human `re_authorization` (actor/source), recorded
as `disposition: paused_re_authorized`; classification counts only when it
matches reviewer/merge-reviewer `finding_classifications[]`, else fails
closed as critical/expanding.

### Safe Merge Path

Merge from a neutral cwd with explicit repo target
(`gh pr merge <n> --repo OWNER/REPO ...`); on local ownership failures
(e.g. `branch ... is checked out at ...`) fall back to
`gh api -X PUT /repos/{owner}/{repo}/pulls/{n}/merge` with an allowed
method, never deleting or moving the offending worktree. Confirm with
`gh pr view <n> --json merged,mergeCommit` before recording the outcome;
write `merge_record` (`merge_path`: `gh_pr_merge` | `api_fallback` |
`merged_by_other`, `remote_confirmed`, `merge_commit_sha`);
`merged_by_other` is a valid confirmed terminal. Post-merge: delete the
remote branch separately, record `branch_deletion_outcome`,
`git worktree prune` used checkouts, list stale/removed worktrees in the
closure report. `checks/pr_gate.py` blocks merge records without
`merge_path` or `remote_confirmed: true`.

## Boundaries

- Never dispatch gate queries and the merge command in one parallel batch;
  the gate query completes first. Reviewer-lane thread resolution and
  self-review recovery follow the reviewer-lane rules above.
- Green CI alone is not merge readiness. Never close an issue from a partial
  implementation. Never replace a maintainer-writable PR unless stale,
  unsafe, unwritable, or human-approved. Do not vendor a local threads
  skill into SpecRail.

Output: report objective/mode/tranche/remaining queue; issue-to-PR mapping and
acceptance coverage; PR/head/merge links; fresh tests, CI, review-thread,
merge-state and PR-gate evidence; open blockers; local worktree state; one
consolidated `human_decisions` list with a recommendation per item.

Rejection persistence and retry:
persist every non-`allowed` route/review/PR gate result at
`.specrail/runtime/rejections/<gate>-<issue|pr>.json`, fix the complete
`rejection_items[]` set, and pass it back with `--prior-rejection`. A
`repeat_rejection` means stop retrying and report the repeated contract
violation; gates themselves remain read-only.
