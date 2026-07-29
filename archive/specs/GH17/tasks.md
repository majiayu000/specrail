# Task Plan

## Linked Issue

GitHub issue: `#17`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP17-T001` Owner: `p1-worker` | Done when: review schema and gate exist | Verify: `uvx pytest -q tests/test_review_json_gate.py`
- [ ] `SP17-T002` Owner: `p1-worker` | Done when: review fixtures cover valid/invalid cases | Verify: `python3 checks/review_json_gate.py --repo . --review examples/fixtures/review-valid.json --diff examples/fixtures/pr-diff.patch --json`
- [ ] `SP17-T003` Owner: `coordinator` | Done when: review guide/docs mention gate | Verify: `rg "review_json_gate|review_result" README.md AGENT_USAGE.md review`

## 并行拆分

P1 worker owns gate/schema/tests/review fixtures. Coordinator owns docs.

## 验证

- `uvx pytest -q`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH17`

## Handoff Notes

Do not conflate advisory `APPROVE` with human final approval.
