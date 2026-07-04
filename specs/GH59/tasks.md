# Task Plan

## Linked Issue

GH-59

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Add `review_source`, `lane_failures[]`, `blocked_reason`,
      `self_review_authorization` fields to
      `schemas/runtime_checkpoint.schema.json` and
      `schemas/pr_review_gate.schema.json`.
- [ ] Enforce the self-review/authorization/merged matrix in
      `checks/runtime_ledger_gate.py` and the `review_source` requirement in
      `checks/pr_gate.py`.
- [ ] Write the lane-failure protocol section in
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add fixtures (2 pass, 2 fail) and unit tests.
- [ ] Update CHANGELOG.

## Parallelization

- Lane A: `checks/runtime_ledger_gate.py` + its tests/fixtures.
- Lane B: `checks/pr_gate.py` + its tests/fixtures.
- Lane C: schemas + skill markdown + CHANGELOG.
Disjoint files; enum vocabulary agreed first (shared with GH-58).

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Unauthorized self-review-merge fixture demonstrably fails.

## Handoff Notes

Depends on the same evidence surfaces as GH-57/GH-58; if all three land
together, do one coordinated schema change. Authorization is recorded as
quoted user text — reviewers must check the quote is real, the gate only
checks presence and scope fields.
