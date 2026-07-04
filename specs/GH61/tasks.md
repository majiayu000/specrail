# Task Plan

## Linked Issue

GH-61

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP61-T001` Owner: schema | Done when: `schemas/review_result.schema.json` includes `review_round`, `review_mode`, `base_head_sha`, `prior_findings`, and `human_full_review_request` fields | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH61`
- [ ] `SP61-T002` Owner: review_gate | Done when: `checks/review_json_gate.py` enforces review round sequence and full-review mode caps | Verify: `python3 -m pytest -q tests/`
- [ ] `SP61-T003` Owner: review_skill | Done when: `skills/specrail-review-pr/SKILL.md` documents review modes and findings-checklist format | Verify: inspection and workflow validation pass
- [ ] `SP61-T004` Owner: queue_skill | Done when: `skills/specrail-implement-queue/SKILL.md` documents bounded lane input scope and resume-first preference | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP61-T005` Owner: threads_doc | Done when: `integrations/threads.md` records the reviewer-lane resume note | Verify: inspection and workflow validation pass
- [ ] `SP61-T006` Owner: tests_changelog | Done when: pass and fail fixtures, unit tests, and `CHANGELOG.md` cover resumed, diff-only, and over-cap full review modes | Verify: `python3 -m pytest -q tests/`

## Parallelization

- Lane A: `checks/review_json_gate.py` + tests + fixtures.
- Lane B: schema file.
- Lane C: two skill files + threads doc + CHANGELOG.
Disjoint files; mode enum agreed first.

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Round-3 full-review fixture demonstrably fails.

## Handoff Notes

Related to #55 (duplicate-work gate): both target duplicate effort; keep the
grouping key (PR number + head SHA) consistent with whatever #55's spec
chooses for PR identity. Full-round cap default is 2; human request is the
only escape hatch.
