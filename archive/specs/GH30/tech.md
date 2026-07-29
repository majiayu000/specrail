# Tech Spec

## Linked Issue

GH-30

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Change |
| --- | --- | --- | --- |
| Shortcut skill | `skills/implx/SKILL.md` | No repo-distributed shortcut exists | Add a thin entrypoint for `implx` prompts |
| Queue skill | `skills/specrail-implement-queue/SKILL.md` | Owns approved-spec queue planning and gates | Reference as the primary queue workflow |
| Threads integration | `integrations/threads.md` | Defines SpecRail versus threads boundary | Reference when queue orchestration is needed |
| Router skill | `skills/specrail-workflow/SKILL.md` | Routes focused SpecRail skills | Add `implx` shortcut routing note |
| Skill lock | `skills-lock.json` | Pins repo-distributed skills | Add `implx` and refresh changed hashes |

## Design

Add `skills/implx/SKILL.md` as a concise shortcut skill. The skill should:

- trigger on `implx`, `use implx`, `用 implx`, and similar requests
- run normal SpecRail startup before queue work
- route approved-spec queues to `skills/specrail-implement-queue/SKILL.md`
- load `integrations/threads.md` and an available threads skill when queue
  orchestration or merge gates are needed
- keep per-issue implementation under the existing implementation flow
- require PR-gate and closure-audit evidence before merge-readiness claims
- preserve explicit human merge authorization as a hard gate

This is a shortcut entrypoint, not a new state machine, CLI, script, or schema.

## Handoff Shape

Agents should report a compact handoff when `implx` is active:

```yaml
implx_handoff:
  route: implement_queue
  issue_to_pr_map:
  approved_specs:
  threads:
    mode:
    lanes:
    fallback_reason:
  gates:
    route_gate:
    pr_gate:
    review_threads:
    merge_authorization:
  closure_audit:
```

The block is a handoff artifact, not a schema-stable API.

## Alternatives

- Expand `specrail-implement-queue` trigger metadata only: rejected because the
  user wants a distinct operational shortcut.
- Put `implx` in a local personal skill only: rejected because the user asked to
  place it in the SpecRail repository.
- Add scripts for queue execution: rejected because this change should preserve
  human-gated agent workflow rather than automating GitHub writes.

## Risks

- Trigger overlap: reduce by describing `implx` as an explicit shortcut, while
  keeping `specrail-implement-queue` as the generic queue skill.
- Boundary drift into automatic merge: state that merge still requires current
  PR-gate evidence and explicit human authorization.
- Overfitting: avoid user-specific paths, issue ranges, repo names, and product
  exclusions.

## Verification Plan

- Run `python3 checks/check_workflow.py --repo . --all-specs`.
- Run the Python test suite.
- Run skill validation for `skills/implx`.
- Inspect skill text for generic wording and human-gate preservation.

## Rollback

Remove `skills/implx/SKILL.md`, its router note, its lockfile entry, and the
GH-30 spec packet. Existing SpecRail queue workflows continue to work.
