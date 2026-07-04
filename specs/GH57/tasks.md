# Task Plan

## Linked Issue

GH-57

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP57-T001` Owner: schema | Done when: `schemas/pr_review_gate.schema.json` includes gate query completion/order, head SHA, and merge marker evidence fields | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH57`
- [ ] `SP57-T002` Owner: pr_gate | Done when: `checks/pr_gate.py` enforces serial ordering, matching head SHA, and stale gate rejection with explicit violation messages | Verify: `python3 -m pytest -q tests/`
- [ ] `SP57-T003` Owner: skills | Done when: `skills/specrail-pr-gate/SKILL.md` documents serial gate ordering and `skills/specrail-implement-queue/SKILL.md` prohibits parallel gate/merge dispatch with a re-query rule | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP57-T004` Owner: tests | Done when: positive and negative fixtures cover a valid serial gate and invalid query-after-merge or head-mismatch evidence | Verify: `python3 -m pytest -q tests/`
- [ ] `SP57-T005` Owner: changelog | Done when: `CHANGELOG.md` records the new required evidence fields and migration note | Verify: inspection and workflow validation pass
- [ ] `SP57-T006` Owner: coordinator | Done when: the PR links GH-57 and contains current validation evidence for tests and workflow checks | Verify: PR body, CI, and local checks

## Parallelization

- Lane A: `checks/pr_gate.py` + tests + fixtures.
- Lane B: `schemas/pr_review_gate.schema.json`.
- Lane C: skill markdown files + CHANGELOG.
Disjoint file sets; schema/check field names agreed in tech spec first.

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Negative fixture (query postdates merge) demonstrably fails the gate.

## Handoff Notes

Field naming must match between schema, check, and skill examples; if a
monotonic ordinal is chosen over wall-clock timestamps, record the decision
here for GH-58/GH-59 evidence structures to reuse.
