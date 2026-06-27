# Task Plan

## Linked Issue

GitHub issue: `#23`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP23-T001` Owner: `review-worker` | Done when: review gate supports range and suggestion validation | Verify: `uvx pytest -q tests/test_review_json_gate.py`
- [ ] `SP23-T002` Owner: `review-worker` | Done when: schema and fixtures cover new contract | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH23`
- [ ] `SP23-T003` Owner: `coordinator` | Done when: review guide/skill mention body/range/suggestion contract | Verify: `rg "start_line|suggestion|Summary|Verdict" review skills/specrail-review-pr`

## 并行拆分

Review worker owns gate, schema, fixtures, and focused tests. Coordinator owns docs and final full-suite verification.

## 验证

- `uvx pytest -q tests/test_review_json_gate.py`
- `python3 checks/review_json_gate.py --repo . --review examples/fixtures/review-valid.json --diff examples/fixtures/pr-diff.patch --json`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH23`

## Handoff Notes

The gate remains advisory-only and must keep blocking final approval / merge authority language.
