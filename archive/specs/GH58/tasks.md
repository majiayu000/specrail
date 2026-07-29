# Task Plan

## Linked Issue

GH-58

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP58-T001` Owner: schema | Done when: `schemas/pr_review_gate.schema.json` records per-thread `resolved_by` and `resolver_role` evidence | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH58`
- [ ] `SP58-T002` Owner: pr_gate | Done when: `checks/pr_gate.py` enforces resolver ownership and outdated-unresolved review thread rules | Verify: `python3 -m pytest -q tests/`
- [ ] `SP58-T003` Owner: review_skill | Done when: `skills/specrail-review-pr/SKILL.md` documents the thread resolution ownership contract | Verify: inspection and workflow validation pass
- [ ] `SP58-T004` Owner: queue_skill | Done when: `skills/specrail-implement-queue/SKILL.md` prohibits implementer resolution of reviewer threads and links the GH-59 lane-failure route | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP58-T005` Owner: tests | Done when: fixtures and unit tests cover the valid path plus implementer-resolved, outdated-unresolved, and missing-resolver failure classes | Verify: `python3 -m pytest -q tests/`
- [ ] `SP58-T006` Owner: changelog | Done when: `CHANGELOG.md` records the new resolver evidence requirement | Verify: inspection and workflow validation pass

## Parallelization

- Lane A: `checks/pr_gate.py` + tests + fixtures.
- Lane B: schema file.
- Lane C: skill markdown + CHANGELOG.
Disjoint files; agree on `resolver_role` enum values first.

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Implementer-resolved fixture demonstrably fails the gate.

## Handoff Notes

`resolver_role` vocabulary is shared with GH-59 (lane failure) evidence;
keep the enum in one place in the schema. Coordinate with GH-57's ordering
fields if both land in the same schema release.
