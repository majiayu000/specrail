# Task Plan

## Linked Issue

GH-59

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP59-T001` Owner: schemas | Done when: `schemas/runtime_checkpoint.schema.json` and `schemas/pr_review_gate.schema.json` include `review_source`, `lane_failures`, `blocked_reason`, and `self_review_authorization` evidence | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH59`
- [ ] `SP59-T002` Owner: runtime_gate | Done when: `checks/runtime_ledger_gate.py` enforces the self-review, authorization, and merged-state decision matrix | Verify: `python3 -m pytest -q tests/`
- [ ] `SP59-T003` Owner: pr_gate | Done when: `checks/pr_gate.py` requires review source evidence before treating independent review as satisfied | Verify: `python3 -m pytest -q tests/`
- [ ] `SP59-T004` Owner: queue_skill | Done when: `skills/specrail-implement-queue/SKILL.md` documents the reviewer-lane failure protocol and blocks silent self-review fallback | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP59-T005` Owner: tests | Done when: pass and fail fixtures cover blocked lane failure and unauthorized self-review merge evidence | Verify: `python3 -m pytest -q tests/`
- [ ] `SP59-T006` Owner: changelog | Done when: `CHANGELOG.md` records the new lane-failure gate contract | Verify: inspection and workflow validation pass

## Parallelization

- Lane A: `checks/runtime_ledger_gate.py` + its tests/fixtures.
- Lane B: `checks/pr_gate.py` + its tests/fixtures.
- Lane C: schemas + skill markdown + CHANGELOG.
Disjoint files; enum vocabulary agreed first (shared with GH-58).

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Unauthorized self-review-merge fixture demonstrably fails.

## Handoff Notes

Depends on the same evidence surfaces as GH-57/GH-58; if all three land
together, do one coordinated schema change. Authorization is recorded as
quoted user text — reviewers must check the quote is real, the gate only
checks presence and scope fields.
