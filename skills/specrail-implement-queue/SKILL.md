---
name: specrail-implement-queue
description: Use when implementing a GitHub issue queue in a SpecRail-governed repository where approved specs already exist, such as multiple numbered specs/GH packets that need one or more implementation PRs per issue. Maps issues to specs and existing PRs, selects single-agent or optional threads orchestration, preserves partial versus final closing semantics, and requires SpecRail verification plus PR gates before merge-readiness claims.
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
   - `specs/GH<issue-number>/tasks.md` when present
5. Map existing PRs before creating replacement PRs.

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
  issues:
    - issue:
      spec_dir:
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
```

## Orchestration

Use `integrations/threads.md` and an available threads skill when the queue needs
parallel lanes, disjoint writable ownership, review-thread checks, CI polling,
merge gates, or closure audit.

If threads is unavailable, continue with the normal single-agent SpecRail flow
and report that no native threads were launched.

Keep ownership boundaries explicit:

- planner and reviewer lanes are read-only
- worker lanes own disjoint files or modules
- shared verification belongs to one coordinator
- dependent specs run serially

## Implementation

For each issue slice:

1. Use `skills/specrail-implement/SKILL.md` for the scoped implementation.
2. Search before adding files, public APIs, workflow assets, schemas, templates,
   or policies.
3. Implement only acceptance criteria from the linked spec and task plan.
4. Add or update tests that prove the changed behavior.
5. Keep machine IDs, paths, commands, states, routes, and JSON keys in English.
6. Keep human-facing text in the selected locale.

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
- GraphQL review-thread state
- merge state
- linked issue or closing reference intent
- explicit human merge authorization before merge

## Boundaries

- Do not grant final approval.
- Do not merge without explicit human authorization and current PR-gate evidence.
- Do not treat green CI as merge readiness without review-thread and merge-state
  truth.
- Do not close an issue from a partial implementation.
- Do not replace an existing maintainer-writable PR unless it is stale, unsafe,
  unwritable, or a human approves replacement.
- Do not vendor a local threads skill into SpecRail.

## Output

Report:

- issue-to-PR mapping
- PR links, head SHAs, and merge commits when merged
- acceptance criteria covered or remaining
- tests and deterministic checks run
- review-thread, CI, merge-state, and PR-gate evidence
- issues still open and why
- local dirty or stale worktree state
