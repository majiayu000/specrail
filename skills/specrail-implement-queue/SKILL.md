---
name: specrail-implement-queue
description: Use ONLY when explicitly delegated by the implx skill or when the user names this skill (specrail-implement-queue) directly. Do not self-activate from descriptive language about optimizing a repository, finishing issues, draining work, or making many PRs — without an explicit implx or by-name invocation, follow the repository's AGENTS.md conventions as a normal agent instead. When invoked, implements or drains a GitHub issue/PR queue in a SpecRail-governed repository where approved specs already exist: maps issues to specs and existing PRs, supports full-queue drain requests from implx, selects single-agent or optional threads orchestration, preserves partial versus final closing semantics, and requires SpecRail verification plus PR gates before merge-readiness claims.
---

# SpecRail Implement Queue

Use this skill for approved-spec implementation queues. For one small issue,
route to `skills/specrail-implement/SKILL.md` instead.

## Startup

1. Run the SpecRail workflow startup:
   - read `AGENTS.md`, `AGENT_USAGE.md`, `workflow.yaml`, `states.yaml`,
     `labels.yaml`, and `skills/specrail-workflow/SKILL.md` when present
   - select the locale
   - identify the `implement` route and human gates
2. Fetch current remote state before mapping the queue.
3. List open issues, open PRs, local branch, dirty files, and worktrees.
   Apply queue skip labels before anything else enters the queue: any issue or
   PR carrying a label in `QUEUE_SKIP_LABELS` (default: `parked`) is excluded
   from the actionable queue, and so is any open PR whose linked issue carries
   a skip label. Draft PRs are also excluded. Skipped items are reported once
   in `human_decisions` and never re-entered within the run, including after
   compaction re-fetches. A skip label always wins over `ready_to_implement`
   or any other actionable state label on the same item.
4. For each candidate issue, read:
   - the GitHub issue
   - `specs/GH<issue-number>/product.md`
   - `specs/GH<issue-number>/tech.md`
   - `specs/GH<issue-number>/tasks.md`
5. Map existing PRs before creating replacement PRs.
6. Collect duplicate-work evidence before opening an implementation lane:

```sh
python3 checks/github_duplicate_evidence.py --github-repo <owner/repo> --issue <issue-number> --json > duplicate-work-evidence.json
python3 checks/route_gate.py --repo . --route implement --issue <issue-number> --state ready_to_implement --duplicate-evidence duplicate-work-evidence.json --json
```

If duplicate evidence is missing, the implementation route needs human input.
If it shows an open PR for the issue, the route is blocked. If it shows only a
matching remote branch, an ownership decision is needed before creating a
competing branch or PR: in `auth_mode: review`, stop and ask; in
`auth_mode: auto`, skip the issue, record it in `human_decisions`, and keep
draining the rest of the queue.

## Spec Coverage Gate

Before planning implementation work, classify every open issue and linked PR:
use only the canonical `spec_status` values defined by
`checks/specrail_lib.py` as `SPEC_STATUSES`.

- `complete`: `product.md`, `tech.md`, and `tasks.md` all exist for the issue,
  and `product.md` does not declare `status: legacy` in its Linked Issue
  section (GH142). A legacy-marked packet is NOT `complete` even when all
  three files exist.
- `needs_tasks`: product and tech specs exist, but `tasks.md` is missing
- `needs_spec`: product or tech spec is missing, or the packet is marked
  `status: legacy` — legacy packets route to `needs_spec` (rewrite the spec so
  it passes the depth gate; the rewrite is the only way to shed the marker)
- `umbrella_covered`: another complete GH spec explicitly includes the issue in
  scope, acceptance criteria, task plan, or linked work
- `exception_allowed`: dependency bump, focused CI fix, docs-only correction, or
  another explicitly justified small non-spec change

Implementation candidates are only `complete`, `umbrella_covered`, or
`exception_allowed`. For `needs_spec` and `needs_tasks`, route to the focused
SpecRail spec-writing or task-planning skill first. Do not implement from only
issue text, PR comments, or old chat context unless the user explicitly
authorizes a non-spec exception and the checkpoint records the reason.

### Done-When Gate

Spec coverage is not enough: an implementation candidate must also have a
decidable completion criterion before it enters an auto queue. Check the
issue body (and its spec packet) for at least one of:

- an enumerated checklist of concrete items (finite N, checkable off)
- explicit acceptance criteria that a reviewer can evaluate as pass/fail
- a verification command whose success closes the issue

Issues without any of these classify as `needs_scope`. Open-ended phrasing
is a strong signal: "backlog", "precision gaps", "edge cases as discovered",
"continuous improvement", 补齐, 持续优化. These issues can regenerate work
indefinitely — an agent that loses working memory to compaction will re-derive
"there is still more to do" every round and never converge.

Routing for `needs_scope`:

- `auth_mode: auto`: never implement. Skip the issue, record it in
  `human_decisions` with the reason `no decidable done-when`, and keep
  draining. Do not auto-apply readiness labels to `needs_scope` issues.
- `auth_mode: review`: ask the human to either scope the issue into an
  enumerated checklist or park it before any implementation lane opens.

Scoping the issue (rewriting it into a finite checklist) is itself valid
queue work in `full_queue_drain`, like `needs_spec` — but the rewritten
checklist is a human gate in both auth modes: auto may draft it, never
self-approve it.

Spec-drafting authorization depends on `auth_mode`:

- `auth_mode: auto`: drafting the missing spec or task packet and then
  implementing from it is authorized only when the current user message
  explicitly selected `implx auto` / `implx 自动`. Draft, self-check with the
  spec-writing skill's own gates, and continue to implementation in the same
  run, subject to the Spec/Impl Mix Gate. Escalate to `human_decisions` only
  for architecture-level rewrites or specs the issue lacks evidence to draft.
- `auth_mode: review`: draft the spec, then wait for human confirmation
  before implementing from it.

Readiness labels in auto mode: when `auth_mode: auto` and an issue's
`spec_status` is `complete` or `umbrella_covered`, a missing readiness
label (for example `ready_to_implement`) is not a blocker. Add the label,
record `readiness_label_source: auto_drain` in the queue artifact, list
every auto-applied label in the report, and continue routing. Issues with
`needs_spec` or `needs_tasks` must never receive an auto readiness label —
this includes `status: legacy` packets, which classify as `needs_spec` even
when all three spec files exist. Auto readiness labeling must never apply to
a legacy-marked packet. In `auth_mode: review`, readiness labels remain a
human gate.

For `queue_mode: full_queue_drain`, `needs_spec` and `needs_tasks` are
actionable planning work, not completion. If no implementation-ready tranche is
available, select the smallest spec-writing or task-planning tranche instead of
ending the queue drain. Treat them as blockers only when the user limited the
run to implementation-only work, the issue lacks enough evidence to draft a
spec, or a human gate prevents spec creation.

## PR Tier Lanes

Classify every implementation candidate into a `pr_tier` before planning PRs.
The tier selects both PR shape and verification profile:

- `heavy`: architecture changes, schema or migration changes, security
  surfaces, cross-module rewrites, or anything the spec marks high risk.
  Keep the full two-PR flow: separate spec PR first, then implementation.
- `standard`: normal feature or fix work. Ship ONE `mixed_impl` PR carrying
  the spec packet (or spec delta) and the implementation together. Do not
  open a separate spec-only PR first.
- `fastlane`: small low-risk changes — roughly ≤50 changed lines and no
  protected paths (API schema, migrations, auth or security code, CI
  workflow definitions). One PR; when the repository's gates accept the
  `exception_allowed` class, the spec content may live in the PR
  description; otherwise include the minimal spec delta in the same PR.

Verification profiles:

| Tier | Required | Not required by default |
| --- | --- | --- |
| `fastlane` | focused tests, repository-required CI, one independent exact-head review, clean merge state | structured review manifest, hosted review, GraphQL thread collection, `pr_gate`, runtime checkpoint |
| `standard` | focused/relevant tests, repository-required CI, one independent exact-head review, linked-spec comparison, `pr_gate` | hosted review, runtime checkpoint outside a long-run milestone |
| `heavy` | full repository verification plus every standard gate, structured review manifest, thread evidence, and milestone checkpoint | none |

Rules:

- Record `pr_tier` with its evidence (changed-line count, touched paths) on
  the PR evidence. Where the repository ships a CI tier check, that
  check is the enforcing authority — never self-declare `fastlane`
  against it.
- When in doubt between two tiers, pick the heavier one.
- A protected path or enforcement-sensitive change is always `heavy`.
- A missing or disputed tier fails closed to `heavy`.
- Do not collect evidence excluded by the selected profile merely because a
  heavier profile supports it.
- The tier selects verification depth only. In `auth_mode: review`, every tier
  still requires explicit per-PR human merge authorization.

## Queue Planning

Build an issue-to-PR plan:

- one issue per implementation PR by default
- for `standard` and `fastlane` tiers, spec content travels in the same
  `mixed_impl` PR per PR Tier Lanes; separate spec PRs are a `heavy`-tier
  pattern
- several PRs per issue only when the task plan or risk justifies smaller slices
- combined PRs only when the specs explicitly share one acceptance surface
- `Refs #<issue>` for partial slices
- closing keywords only for the final slice that satisfies every acceptance
  criterion

When gating a partial slice, pass that expected issue to the read-only evidence
adapter with `--issue <issue>`. This verifies the live open issue and keeps any
other bounded closing references auditable without treating the partial target
as final or authorizing its closure.

Deprecation windows in auto mode: when a queue item requires a deprecation
or removal window and the user did not specify a starting version, default
to the next minor release after the current latest release, record
`deprecation_default: true` with the chosen version in the PR handoff
and in the PR description, and continue. The removal itself stays subject
to the existing gates; the user can veto the default afterwards.

Record the plan as:

```yaml
specrail_implementation_queue:
  overall_objective:
  queue_mode: bounded_tranche | full_queue_drain
  auth_mode: auto | review
  spec_coverage:
    complete:
    needs_tasks:
    needs_spec:
    umbrella_covered:
    exception_allowed:
  milestone:
  remaining_queue:
  issues:
    - issue:
      spec_dir:
      spec_status: complete | needs_tasks | needs_spec | umbrella_covered | exception_allowed
      spec_status_reason:
      acceptance_criteria:
      existing_prs:
      planned_prs:
      completion_mode: partial | final
      verification:
  gates:
    route_gate:
    pr_gate:
    review_threads:
    merge_authorization:
  checkpoint:
    path:
  stop_policy:
```

If `auth_mode` is not provided by the calling skill, default to
`auth_mode: review`. Never promote a run to auto mode from persisted repository
configuration; auto requires the explicit current-message invocation above.

For broad queues, use milestone phases rather than lane-sized tranches. If the calling skill is
`implx`, or the user otherwise asks to finish actionable issues/PRs, set
`queue_mode: full_queue_drain` unless the prompt explicitly limits scope to one
issue, one PR, the current tranche, plan-only, status-only, or review-only work.
In that mode, complete initial review across the selected queue before repairs,
then continue selecting implementation, spec-writing, or task-planning work
until the queue is drained or every remaining item is explicitly blocked,
deferred, waiting on CI, or needs human input.

A blocked or waiting item does not stop full-queue drain. Refresh remote truth
and look for an independent next item. Stop only when every remaining issue and PR is listed in
`remaining_queue` with `spec_status`, `blocker`, and `next_action`.

If the user only asks for a broad queue without explicit full-queue drain
authorization, choose the smallest mergeable scope and report the rest.

## Spec/Impl Mix Gate

Classify every PR the run creates as `pr_kind` in the queue artifact:

- `spec`: only spec packets, docs, or planning artifacts
- `impl`: production code or tests
- `mixed_impl`: any PR that contains production code, even alongside specs

Rules:

- More than 3 consecutive `spec` PRs is a blocking violation unless the user
  explicitly confirmed a spec-only phase.
- Items without a `pr_kind` (blocked items, non-PR work) do not reset the
  streak; only `impl`/`mixed_impl` PRs do.
- Count PR kinds directly from the current queue artifact; do not mirror the
  counters into the milestone checkpoint.
- Never present spec PR counts as implementation progress in reports.

## Orchestration

Use `integrations/threads.md` and an available threads skill for parallel lanes,
disjoint ownership, review/CI/merge gates, or closure audit. For GitHub queues,
native dispatch is required when available. Before implementation, review,
push, comment, or merge, record:

```yaml
thread_dispatch_gate:
  explicit_thread_request:
  native_subagents:
  spawn_requirement:
  fallback_mode:
  planned_native_threads:
  native_thread_evidence:
    spawned_agents:
  no_spawn_reason:
```

When `spawn_requirement: required`, dispatch the planned bounded native lanes.
PR merge work needs a real read-only `reviewer`/`merge_reviewer` thread with
`agent_id_or_thread_id`, wait/close evidence, and output; the coordinator is not
that reviewer.

If threads is unavailable, record `fallback_mode: single_agent` and its reason,
use the normal SpecRail flow, and report that no native threads launched.

Keep ownership boundaries explicit:

- planner/reviewer lanes are read-only and use low effort when configurable
- worker lanes own disjoint files or modules
- shared verification belongs to one coordinator
- dependent specs run serially
- builds/tests run only in the lane's worktree; never use the primary checkout
  during other sessions or run two build/test commands in one worktree

## Bounded Review Contract

Use the canonical contract in
`skills/specrail-review-pr/SKILL.md#review-rounds-and-modes`. The queue owns
batch ordering only; it must not copy or override review-round semantics.

For a tranche containing existing PRs:

1. Complete one full review of every PR before starting any repair.
2. For `heavy` PRs, or when the user explicitly requests hosted review, collect
   hosted feedback once in a fixed 15-minute window. Fastlane and standard PRs
   skip this wait by default. Feedback arriving after the window is deferred
   unless it identifies a security or data-loss risk; never restart the window.
3. Apply at most one repair per PR, then run one diff-only re-review.
4. If the re-review is not merge-ready, move the PR to `human_decisions`.
   Do not spend a third automatic review round.
5. After the first three PRs reach terminal review state, stop the remaining
   queue when none is merge-ready. Report elapsed time, observed cost per PR,
   estimated remaining cost, and the shared blockers before continuing.

## Reviewer Lane Execution

Give the reviewer only the exact diff, linked spec packet, and compact carry, never
coordinator history. Resume/message it first; otherwise dispatch the next bounded
`diff_only` lane. One bounded wait plus one stop request precedes `zero_output`.
Record every usage-limit, crash, zero-output, or early-close in `lane_failures[]`
with lane id, kind, optional `other` detail, and marker; report and downgrade to
`blocked`/`needs_human` with `blocked_reason: reviewer_lane_failure`. Recover via
a different local lane or authorized local `self_review` recording actor, source,
quoted scope, and marker; generic authorization cannot substitute.
Only two distinct recorded lane failures let `implx auto` authorize scoped
self-review; one requires retry, review mode has no exception, and gates enforce it.

## Context Budget

For long queues, record a parent context budget before spawning lanes:

- default soft stop: 50% of the active context window
- default hard stop: 65% of the active context window
- default critical stop: 75% of the active context window

These are defaults, not universal limits. If the runtime exposes a different
budget or the user provides one, record the override.

At soft stop, do not spawn new lanes or broaden scope. At hard stop, finish the
current critical step, write the runtime checkpoint, and hand off to a fresh
parent thread. At critical stop, only write checkpoint and resume instructions.
For `queue_mode: full_queue_drain`, a hard-stop handoff preserves the full queue
objective and records the next actionable tranche; it does not redefine success
as completing only the current tranche.

### Milestone Hard Stop

Do not create a tranche for every lane wave or fixed number of items. A long
queue has four checkpoint milestones only: startup, initial review complete,
repair/re-review complete, and closure or handoff.

Use the runtime's own context and time limits directly. At soft stop, do not
spawn new work. At hard stop, finish the current atomic action, write one
milestone checkpoint, and hand off. Do not copy token counters, tool-call
counters, CI state, review state, or GitHub state into that checkpoint.

Before reopening an issue, use fresh GitHub and Git history. If the same issue
has already consumed two unsuccessful repair/re-review cycles, route it to
`human_decisions`; do not create another automatic tranche.

## Output Firewall

Large output commands are allowed only when raw stdout and stderr go to artifact
files. The coordinator may read exit code, a short tail, targeted grep output,
and the artifact path.

Default rules:

- no raw `gh run view --log` output in parent context
- no raw full `cargo test` or full workspace test output in parent context
- no broad `rg` or `git grep` across `.codex`, `.claude`, `target`,
  `node_modules`, session JSONL, or log files
- parent stdout tail target: 150 lines or less
- subagent final output target: 150 lines or less

Prefer artifact paths such as `artifacts/logs/<tranche>/cargo-test.log` and
summaries such as `artifacts/logs/<tranche>/ci-summary.md`.

## Turn Batching

Every model turn re-sends the whole conversation history, so turn count is a
first-order cost: a 3000-turn session at a 200K-token context costs an order
of magnitude more than the same work in 300 turns. Batch aggressively:

- Collect evidence in one scripted call: consecutive read-only steps (git
  queries, gate scripts, `gh` views, file reads) run as a single script whose
  raw output goes to an artifact, not as one tool call each.
- Combine edit-verify micro-loops: apply a patch set, then run the focused
  check, in as few calls as the tooling allows — never one turn per file.
- Target under 500 turns for a single-PR session. Crossing 1000 turns without
  a merged outcome is a stall signal: checkpoint, reassess the plan, and
  prefer a fresh scoped session over grinding forward.
- Never spend a turn on a no-op: empty polls, re-checking status that was
  verified earlier in the same turn, or re-reading unchanged files.

## Waiting Discipline

Waiting happens inside a single blocking tool call, never by looping the model.
Every model turn re-sends the full history, so poll loops — repeated
`write_stdin` with empty input against a background process, or
`for i in 1..N; do gh pr view ...; sleep; done` — burn tokens proportional to
history size times poll count while doing no work (openai/codex#13733). Replace
each poll loop with one blocking wait:

- CI on a PR: `gh pr checks <n> --repo OWNER/REPO --watch --fail-fast` blocks in
  one call until every check settles. For a specific run:
  `gh run watch <run-id> --repo OWNER/REPO --exit-status`.
- Long local checks (`cargo test`, `cargo clippy`, deterministic checks): run
  them in the foreground to completion with an adequate command timeout and raw
  output redirected to an artifact per the Output Firewall. Do not launch them
  as a background process and then poll `write_stdin` for output.
- Reviewer / merge-reviewer lanes: keep the existing bounded-wait rule (one
  bounded wait plus one stop-and-return; see Reviewer Lane Failures). That
  bounded wait is a single blocking wait on the lane, not a poll loop.
- When a wait must happen through `exec_command` / `wait` sessions, request the
  maximum yield each time: set `yield_time_ms` to the configured
  `background_terminal_max_timeout` (never the 30s habit), and if a task needs
  multiple waits, grow the yield exponentially between them. Thirty-second
  slices against a multi-minute check are poll loops with extra steps.

Test layering, to avoid re-paying a full-suite wait on every fix round:

- During iteration, run only the focused tests for the touched behavior.
- Run the full suite plus clippy plus deterministic checks once, immediately
  before claiming PR-ready — not after each individual fix.

## Runtime Checkpoint

For long queues, create or update the optional local resume cursor only at:

- startup
- completion of all initial PR reviews
- completion of the single repair/re-review phase
- closure, handoff, or a hard context stop

Use `templates/tranche_checkpoint.md` as the shape and validate concrete JSON
checkpoints with:

```bash
python3 checks/runtime_ledger_gate.py --checkpoint .specrail/runtime/current.json
```

The checkpoint records only run identity, scope, current milestone, completed,
pending and blocked work references, artifact paths, and the resume action. It
must not contain head SHA, CI, review, thread, merge, authorization, PR-gate,
branch, worktree, budget, Goal, or agent telemetry fields. Refresh those from
their authorities after resuming.

## Goal Use

When the runtime exposes Goal and `auth_mode: auto` uses
`queue_mode: full_queue_drain`, the Goal may carry the whole-run objective.
Do not mirror Goal state or budgets into the checkpoint.

- Queue empty, or every remaining item is in `human_decisions`: mark the
  goal complete and emit the final report. Never mark the goal complete
  while actionable queue items remain.
- Token budget exhausted: write one handoff milestone and stop.
- User interrupt follows native Codex behavior.

## Implementation

For each issue slice:

1. Use `skills/specrail-implement/SKILL.md` for the scoped implementation.
2. Search before adding files, public APIs, workflow assets, schemas, templates,
   or policies.
3. Run duplicate-work evidence collection and the implementation route gate
   before creating a new implementation PR.
4. Implement only acceptance criteria from the linked spec and task plan.
5. Add or update tests that prove the changed behavior.
6. Keep machine IDs, paths, commands, states, routes, and JSON keys in English.
7. Keep human-facing text in the selected locale.

## Review And Verification

Before readiness, run the verification profile selected under PR Tier Lanes.
`standard` and `heavy` compare the diff with linked specs via
`skills/specrail-check-impl-against-spec/SKILL.md` and use
`skills/specrail-pr-gate/SKILL.md`. `fastlane` does not invoke those gates.
All tiers still run checks explicitly required by the consumer repository.

For `standard` and `heavy` GitHub PRs, current evidence must include:

- PR head, CI/check rollup, review decision, merge state, and linked issue/closing intent
- independent reviewer evidence and native reviewer-thread evidence when
  available; terminal `review_execution: local` (hosted review is supplemental)
- `review_source`, `lane_failures[]` (empty when none), and required
  `self_review_authorization`
- GraphQL threads plus each resolver's identity/lane role
- serial `pr_gate.py` query timestamp and head SHA
- `pr_tier`, changed-line/path evidence, and merge authorization for the
  selected `auth_mode`

When a milestone checkpoint is present, it must not mark a `standard` or
`heavy` PR item `complete`, `merged`, `merge_ready`, or `ready_to_merge` unless
`checks/runtime_ledger_gate.py` accepts it. Fastlane readiness remains remote
truth and is summarized at the next milestone; do not create a checkpoint only
to duplicate that state.

### Merge Authorization

`auth_mode: auto`:

- The current user message must explicitly say `implx auto` / `implx 自动`.
  That invocation is the standing merge authorization for the run. Do not ask
  per-PR merge questions.
- Merge when the selected profile's current evidence is green. Fastlane needs
  CI, one independent exact-head review, and clean merge state. Standard and
  heavy additionally need their declared PR/thread gates. Any required evidence
  gap means skip the PR, record the gap in
  `remaining_queue`, and keep draining.
- Use closing keywords on final slices; after merge, close issues whose
  acceptance criteria are fully merged. Merged-but-open issues found during
  closure audit are closed with a comment linking the merged PRs.
- Human-gate items (duplicate-ownership conflicts, maintainer waivers, probe
  or time-window gates, conflicting review feedback, destructive or
  irreversible actions) never block the queue: skip, continue, and report them
  once in a final `human_decisions` list with a recommended action each.
- Auto mode does not weaken the selected profile, self-review authorization,
  or the Milestone Hard Stop. Standing merge authorization is not
  self-review authorization.

`auth_mode: review`:

- Every PR requires explicit human merge authorization in the current
  conversation after its selected verification profile is green.
- `pr_tier` changes verification depth only and never grants merge authority.
- Findings that change intent, paths, contracts, or security-sensitive behavior
  invalidate prior authorization and require a new human authorization after
  repair and re-review.

### Safe Merge Path

Merging must survive branches that are checked out in local worktrees and
must never report an outcome without remote confirmation:

1. Run the merge from a neutral cwd with an explicit repo target
   (`gh pr merge <n> --repo OWNER/REPO ...`).
2. On local ownership failures (for example `branch ... is checked out at
   ...` or a worktree lock; the class is "local ownership failure", the
   messages are examples), fall back to
   `gh api -X PUT /repos/{owner}/{repo}/pulls/{n}/merge` using a merge
   method the repo allows (query merge settings first). Do not delete or
   move the offending worktree — it may belong to another live session.
3. Always confirm the outcome with a remote query
   (`gh pr view <n> --json merged,mergeCommit`) before recording success or
   failure, and write the result into the gate evidence as `merge_record`
   (`merge_path`: `gh_pr_merge` | `api_fallback` | `merged_by_other`,
   `remote_confirmed`, `merge_commit_sha`). A PR merged by someone else is a
   valid confirmed terminal (`merged_by_other`).
4. Post-merge: delete the remote branch as a separate step and record
   `branch_deletion_outcome`; run `git worktree prune` in each local
   checkout the tranche used and list stale or removed worktrees in the
   closure report.

`checks/pr_gate.py` blocks merge records without `merge_path` or without
`remote_confirmed: true`.

## Boundaries

- In `auth_mode: auto`, merge only on complete current evidence; evidence gaps
  mean skip and report, not ask.
- In `auth_mode: review`, do not merge without current PR-gate evidence and
  explicit per-PR human authorization in the current conversation.
- Do not dispatch review-thread/pr_gate queries and the merge command in the
  same parallel tool batch or parallel lane; the gate query must complete first.
- Reviewer-lane thread resolution and self-review recovery must follow Reviewer
  Lane Execution; implementation/coordinator roles cannot resolve those threads.
- Do not treat green CI as merge readiness without review-thread and merge-state
  truth.
- Do not close an issue from a partial implementation.
- Do not replace an existing maintainer-writable PR unless it is stale, unsafe,
  unwritable, or a human approves replacement.
- Do not vendor a local threads skill into SpecRail.

## Output

Report:

- overall objective, queue mode, current tranche, and remaining queue
- issue-to-PR mapping
- PR links, head SHAs, and merge commits when merged
- acceptance criteria covered or remaining
- tests and deterministic checks run
- review-thread, CI, merge-state, and PR-gate evidence
- issues still open and why
- `human_decisions`: the consolidated list of items needing a human choice,
  each with a recommended action (auto mode reports this once at the end
  instead of asking mid-run)
- local dirty or stale worktree state

## Rejection Persistence And Retry

When a gate command in this skill (`checks/route_gate.py`,
`checks/review_json_gate.py`, or `checks/pr_gate.py`) rejects with a decision
other than `allowed`, the caller persists the gate's JSON output to
`.specrail/runtime/rejections/<gate>-<issue|pr>.json` (create the directory if
missing). This write is orchestrator behavior; the gate itself stays
read-only. Use the `rejection_items[]` list to fix every defect in a single
round instead of guessing one item per retry.

On the next retry of the same gate for the same issue or PR, pass
`--prior-rejection .specrail/runtime/rejections/<gate>-<issue|pr>.json`. If
the new output contains a `repeat_rejection` section, the same item was
rejected verbatim twice: stop retrying and report the contract violation to a
human instead of starting another round.
