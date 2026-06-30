---
name: implx
description: Use when the user says "implx", "use implx", "用 implx", or asks for the short SpecRail queue shortcut to process a repository's approved-spec issue/PR queue with SpecRail implementation queue planning, optional threads orchestration, per-issue implementation PRs, review-thread and CI gates, merge authorization, and closure audit.
---

# Implx

Use this skill as a short operational entrypoint. It does not replace the
focused SpecRail skills; it routes to them in the right order.

## Startup

1. Run the normal SpecRail startup:
   - read the repository `AGENTS.md`
   - read `AGENT_USAGE.md`, `workflow.yaml`, `states.yaml`, `labels.yaml`, and
     `skills/specrail-workflow/SKILL.md` when present
   - select the human-facing locale
   - identify human gates and route-gate requirements
2. Fetch current remote state before mapping a GitHub queue.
3. List open issues, open PRs, current branch, dirty files, and worktrees.
4. For broad queues, record whether the run has explicit goal or budget
   authorization. If not, write a `goal_candidate` only; do not silently create
   a Codex goal.

## Route

Use `skills/specrail-implement-queue/SKILL.md` when approved specs or open
issues need coordinated implementation PRs. For each candidate issue, require
the matching `specs/GH<issue-number>/product.md`, `tech.md`, and `tasks.md`
when present.

If approved specs are missing, stop at the appropriate SpecRail spec or task
planning route instead of implementing from assumptions.

For approved-spec queues, route to `skills/specrail-implement-queue/SKILL.md`
and follow its context budget, output firewall, runtime checkpoint, and goal-use
rules.

## Threads

When the queue needs parallel lanes, disjoint writable ownership, reviewer
lanes, CI polling, review-thread checks, merge gates, or closure audit, read
`integrations/threads.md` and use an available threads skill.

If no native threads capability is available, continue with the normal
single-agent SpecRail flow and report that no native threads were launched.

Keep ownership boundaries explicit:

- planners and reviewers are read-only
- workers own disjoint files or modules
- shared verification belongs to one coordinator
- dependent specs run serially

Keep the parent thin. Do not use old Codex session logs as queue state. Large
command output must be written to artifacts first; the parent reads only exit
codes, short tails, targeted grep results, and artifact paths.

## Implementation

For each issue slice:

1. Map existing PRs before opening replacement PRs.
2. Use one issue per implementation PR by default.
3. Use multiple PRs for one issue only when the task plan or risk justifies
   smaller slices.
4. Use `Refs #<issue>` for partial slices.
5. Use closing keywords only for the final slice that satisfies every
   acceptance criterion.
6. Route scoped implementation work through `skills/specrail-implement/SKILL.md`.
7. Implement only acceptance criteria from the linked spec and task plan.
8. Add or update tests that prove the changed behavior.

## Gates

Before reporting a PR as ready:

- run focused tests for touched behavior
- run repository deterministic checks
- run `python3 checks/check_workflow.py --repo .`
- run `python3 checks/check_workflow.py --repo . --spec-dir specs/GH<issue>`
  when the spec packet changed
- use `skills/specrail-check-impl-against-spec/SKILL.md` for spec comparison
- use `skills/specrail-pr-gate/SKILL.md` before merge-readiness claims

GitHub PR evidence must include current PR head SHA, CI/check rollup,
review-thread state from GraphQL, merge state, linked issue intent, and explicit
human merge authorization before merge.

## Boundaries

- Do not grant final approval.
- Do not merge without current PR-gate evidence and explicit authorization in
  the current conversation.
- Do not treat green CI as merge readiness without review-thread and merge-state
  truth.
- Do not close an issue from a partial implementation.
- Do not replace an existing maintainer-writable PR unless it is stale, unsafe,
  unwritable, or a human approves replacement.

## Handoff

Report a compact handoff when `implx` is active:

```yaml
implx_handoff:
  route: implement_queue
  issue_to_pr_map:
  approved_specs:
  threads:
    mode:
    lanes:
    fallback_reason:
  goal:
    enabled:
    objective:
    stop_reason:
  context_budget:
    soft_stop_ratio:
    hard_stop_ratio:
    critical_stop_ratio:
  checkpoint:
    path:
    runtime_gate:
  gates:
    route_gate:
    pr_gate:
    review_threads:
    merge_authorization:
  closure_audit:
```
