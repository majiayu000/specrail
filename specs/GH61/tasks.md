# Task Plan

## Linked Issue

GH-61

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Add `review_round`, `review_mode`, `base_head_sha`,
      `prior_findings[]`, `human_full_review_request` to
      `schemas/review_result.schema.json`.
- [ ] Implement round-sequence and mode-cap enforcement in
      `checks/review_json_gate.py`.
- [ ] Document modes + findings-checklist format in
      `skills/specrail-review-pr/SKILL.md`.
- [ ] Document lane input scope and resume-first preference in
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add resume note to `integrations/threads.md`.
- [ ] Add fixtures (2 pass, 2 fail) and unit tests; update CHANGELOG.

## Parallelization

- Lane A: `checks/review_json_gate.py` + tests + fixtures.
- Lane B: schema file.
- Lane C: two skill files + threads doc + CHANGELOG.
Disjoint files; mode enum agreed first.

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Round-3 full-review fixture demonstrably fails.

## Handoff Notes

Related to #55 (duplicate-work gate): both target duplicate effort; keep the
grouping key (PR number + head SHA) consistent with whatever #55's spec
chooses for PR identity. Full-round cap default is 2; human request is the
only escape hatch.
