---
name: specrail-implement-queue
description: Use when implementing or draining a GitHub issue/PR queue in a SpecRail-governed repository where approved specs already exist, such as multiple numbered specs/GH packets that need one or more implementation PRs per issue. Maps issues to specs and existing PRs, supports full-queue drain requests from implx, selects single-agent or optional threads orchestration, preserves partial versus final closing semantics, and requires SpecRail verification plus PR gates before merge-readiness claims.
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
matching remote branch, stop for a human ownership decision before creating a
competing branch or PR.

## Spec Coverage Gate

Before planning implementation work, classify every open issue and linked PR:
use only the canonical `spec_status` values defined by
`checks/specrail_lib.py` as `SPEC_STATUSES`.

- `complete`: `product.md`, `tech.md`, and `tasks.md` all exist for the issue
- `needs_tasks`: product and tech specs exist, but `tasks.md` is missing
- `needs_spec`: product or tech spec is missing
- `umbrella_covered`: another complete GH spec explicitly includes the issue in
  scope, acceptance criteria, task plan, or linked work
- `exception_allowed`: dependency bump, focused CI fix, docs-only correction, or
  another explicitly justified small non-spec change

Implementation candidates are only `complete`, `umbrella_covered`, or
`exception_allowed`. For `needs_spec` and `needs_tasks`, route to the focused
SpecRail spec-writing or task-planning skill first. Do not implement from only
issue text, PR comments, or old chat context unless the user explicitly
authorizes a non-spec exception and the checkpoint records the reason.

For `queue_mode: full_queue_drain`, `needs_spec` and `needs_tasks` are
actionable planning work, not completion. If no implementation-ready tranche is
available, select the smallest spec-writing or task-planning tranche instead of
ending the queue drain. Treat them as blockers only when the user limited the
run to implementation-only work, the issue lacks enough evidence to draft a
spec, or a human gate prevents spec creation.

## Queue Planning

Build an issue-to-PR plan:

- one issue per implementation PR by default
- several PRs per issue only when the task plan or risk justifies smaller slices
- combined PRs only when the specs explicitly share one acceptance surface
- `Refs #<issue>` for partial slices
- closing keywords only for the final slice that satisfies every acceptance
  criterion

Record the plan as:

```yaml
specrail_implementation_queue:
  overall_objective:
  queue_mode: bounded_tranche | full_queue_drain
  spec_coverage:
    complete:
    needs_tasks:
    needs_spec:
    umbrella_covered:
    exception_allowed:
  current_tranche:
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
  context_budget:
    soft_stop_ratio: 0.50
    hard_stop_ratio: 0.65
    critical_stop_ratio: 0.75
  checkpoint:
    path:
    runtime_gate:
  stop_policy:
```

For broad queues, always execute as bounded tranches. If the calling skill is
`implx`, or the user otherwise asks to finish actionable issues/PRs, set
`queue_mode: full_queue_drain` unless the prompt explicitly limits scope to one
issue, one PR, the current tranche, plan-only, status-only, or review-only work.
In that mode, choose the smallest mergeable current tranche, checkpoint it, then
continue selecting new implementation, spec-writing, or task-planning tranches
until the queue is drained or every remaining item is explicitly blocked,
deferred, waiting on CI, or needs human input.

A blocked or waiting current tranche does not stop full-queue drain. After
checkpointing that tranche, refresh remote truth and look for an independent
next tranche. Stop only when every remaining issue and PR is listed in
`remaining_queue` with `spec_status`, `blocker`, and `next_action`.

If the user only asks for a broad queue without explicit full-queue drain
authorization, choose the smallest mergeable tranche and leave the rest in the
checkpoint.

## Orchestration

Use `integrations/threads.md` and an available threads skill when the queue needs
parallel lanes, disjoint writable ownership, review-thread checks, CI polling,
merge gates, or closure audit.

For GitHub issue or PR queues, merge gates, reviewer lanes, and closure audit,
native thread dispatch is required whenever native subagent capability is
available. Before implementation, review, push, comment, or merge work, record:

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

If native subagents are available and `spawn_requirement: required`, spawn the
planned bounded native lanes before claiming threads were used. For PR merge
work, at least one read-only `reviewer` or `merge_reviewer` lane must be a real
native thread with recorded `agent_id_or_thread_id`, wait evidence, close
evidence, and collected output. The coordinator lane is not a reviewer thread.

If threads is unavailable, continue with the normal single-agent SpecRail flow
only after recording `fallback_mode: single_agent` and the reason; report that
no native threads were launched.

Keep ownership boundaries explicit:

- planner and reviewer lanes are read-only
- worker lanes own disjoint files or modules
- shared verification belongs to one coordinator
- dependent specs run serially

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

Do not read raw `~/.codex/sessions` logs, old parent transcripts, or broad
session JSONL as queue state. Use the checkpoint, repo-local run logs, and fresh
remote truth.

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

## Runtime Checkpoint

For long queues, create or update an optional local runtime checkpoint before:

- spawning writable lanes
- pushing or opening PRs
- waiting on CI or long local tests
- requesting merge review
- compacting, handing off, or closing the parent thread
- selecting the next tranche in a full-queue drain loop

Use `templates/tranche_checkpoint.md` as the shape and validate concrete JSON
checkpoints with:

```bash
python3 checks/runtime_ledger_gate.py --checkpoint .specrail/runtime/current.json
```

The runtime checkpoint is a local handoff layer only. GitHub issues, PRs,
labels, reviews, branches, and SpecRail spec packets remain the durable workflow
truth.

For `queue_mode: full_queue_drain`, the checkpoint must record the overall
objective, spec coverage, current tranche, completed items, remaining queue,
explicit blockers, and next resume action. `needs_spec`, `needs_tasks`,
`eligible_impl`, `waiting_ci`, and `needs_review` do not count as drained while
the checkpoint status is `complete`; they require a next action or a non-drain
handoff status. Resume from the checkpoint plus fresh remote truth; do not
recover queue state from old parent transcripts.

## Goal Use

Codex Goal can control the current tranche only when the user explicitly asks
for goal-controlled work, gives a token or time budget, or explicitly frames the
run as long-running goal work. Otherwise record a `goal_candidate` in the
checkpoint but do not silently create a goal.

Goal never replaces the runtime checkpoint, GitHub truth, or SpecRail gates.

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

Before a PR is considered ready:

- run focused tests for touched behavior
- run repository deterministic checks
- run `python3 checks/check_workflow.py --repo .`
- run `python3 checks/check_workflow.py --repo . --spec-dir specs/GH<issue>`
  when the spec packet changed
- use `skills/specrail-check-impl-against-spec/SKILL.md` to compare the PR or
  diff to the linked specs
- use `skills/specrail-pr-gate/SKILL.md` before reporting merge readiness

For GitHub PRs, current evidence must include:

- PR head SHA
- CI/check rollup
- review decision when available
- independent reviewer or merge-reviewer lane evidence
- native reviewer thread evidence when native subagents are available
- GraphQL review-thread state
- per-thread resolver identity and resolver lane role
- gate-query completion timestamp and gate-query head SHA from the serial
  `pr_gate.py` run
- merge state
- linked issue or closing reference intent
- explicit human merge authorization before merge

The runtime checkpoint must not mark a PR item `complete`, `merged`,
`merge_ready`, or `ready_to_merge` unless `checks/runtime_ledger_gate.py` accepts
the checkpoint. When the gate is evaluating a merged or merge-ready PR, local
`pr_gate.evidence` must exist and either be an allowed PR gate result JSON or a
raw PR evidence JSON that re-evaluates to `allowed`.

## Boundaries

- Do not grant final approval.
- Do not merge without explicit human authorization and current PR-gate evidence.
- Do not dispatch review-thread/pr_gate queries and the merge command in the
  same parallel tool batch or parallel lane; the gate query must complete first.
- Do not let an implementation lane or orchestrator resolve reviewer-lane
  review threads. If the reviewer lane is unavailable, route through the GH-59
  reviewer-lane failure path or a human decision.
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
- local dirty or stale worktree state
