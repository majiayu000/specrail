# Tech Spec

## Linked Issue

GH-28

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Change |
| --- | --- | --- | --- |
| Router skill | `skills/specrail-workflow/SKILL.md` | Routes focused single-route skills | Add routing for implementation queues |
| Single implementation skill | `skills/specrail-implement/SKILL.md` | Handles one scoped issue route | Keep as the per-issue worker skill |
| PR gate skill | `skills/specrail-pr-gate/SKILL.md` | Checks merge readiness without merging | Reference from queue skill |
| Implementation review | `skills/specrail-check-impl-against-spec/SKILL.md` | Compares diff or PR to specs | Reference for reviewer lanes |
| Threads integration | `integrations/threads.md` | Defines SpecRail versus threads boundary | Add queue handoff for approved specs |
| Skill lock | `skills-lock.json` | Pins repo-distributed skills | Add the new skill hash |

## Design

Add `skills/specrail-implement-queue/SKILL.md` as a focused orchestration skill.
It should not duplicate all threads mechanics or SpecRail route details. Instead
it should:

- run SpecRail startup and route-gate checks
- map issues, specs, and existing PRs
- choose single-agent or threads orchestration
- route each issue slice through `specrail-implement`
- require `specrail-check-impl-against-spec` and `specrail-pr-gate` evidence
- preserve human final approval and merge authorization

Update `skills/specrail-workflow/SKILL.md` so agents know when to use the new
skill. Update `integrations/threads.md` with the handoff fields required when
threads is active.

## Handoff Shape

The queue skill should ask the agent to record:

```yaml
specrail_implementation_queue:
  issues:
    - issue:
      spec_dir:
      existing_prs:
      planned_prs:
      completion_mode: partial | final
  gates:
    route_gate:
    pr_gate:
    review_threads:
    merge_authorization:
  orchestration:
    mode: single_agent | threads
    lane_map:
    fallback_reason:
```

This is a handoff artifact, not a schema-stable API.

## Alternatives

- Put the workflow only in `threads`: rejected because SpecRail owns the policy
  and required artifacts.
- Put the workflow only in `integrations/threads.md`: rejected because agents
  need a discoverable focused route skill.
- Expand `specrail-implement`: rejected because single issue implementation and
  queue orchestration have different triggers and evidence needs.

## Risks

- Trigger overlap with `specrail-implement`: reduce by making the new skill
  clearly queue-focused.
- Boundary drift into automatic merge: keep final approval and merge
  authorization as explicit human gates.
- Overfitting to one consumer repo: avoid consumer-specific paths, issue
  numbers, excluded scopes, and build commands.

## Verification Plan

- Run `python3 checks/check_workflow.py --repo . --all-specs`.
- Run the test suite.
- Confirm `skills-lock.json` hash validation passes.
- Inspect the changed skills for generic wording and boundary preservation.

## Rollback

Remove `skills/specrail-implement-queue/SKILL.md`, its router reference, the
threads integration section, and its `skills-lock.json` entry. Existing focused
route skills continue to work.
