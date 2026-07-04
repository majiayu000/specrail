# Task Plan

## Linked Issue

GH-58

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Add per-thread `resolved_by` / `resolver_role` fields to
      `schemas/pr_review_gate.schema.json`.
- [ ] Enforce resolver-ownership and outdated-unresolved rules in
      `checks/pr_gate.py`.
- [ ] Add "Thread resolution ownership" section to
      `skills/specrail-review-pr/SKILL.md`.
- [ ] Add implementer resolve prohibition (and GH-59 routing note) to
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add fixtures and unit tests (pass + 3 failure classes).
- [ ] Update CHANGELOG.

## Parallelization

- Lane A: `checks/pr_gate.py` + tests + fixtures.
- Lane B: schema file.
- Lane C: skill markdown + CHANGELOG.
Disjoint files; agree on `resolver_role` enum values first.

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Implementer-resolved fixture demonstrably fails the gate.

## Handoff Notes

`resolver_role` vocabulary is shared with GH-59 (lane failure) evidence;
keep the enum in one place in the schema. Coordinate with GH-57's ordering
fields if both land in the same schema release.
