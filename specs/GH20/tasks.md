# Task Plan

## Linked Issue

GitHub issue: `#20`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP20-T001` Owner: `p0-worker` | Done when: issue fixtures exist | Verify: `uvx pytest -q tests/test_github_issue_evidence.py`
- [ ] `SP20-T002` Owner: `p1-worker` | Done when: review fixtures exist | Verify: `uvx pytest -q tests/test_review_json_gate.py`
- [ ] `SP20-T003` Owner: `coordinator` | Done when: PR gate tests read PR fixtures | Verify: `uvx pytest -q tests/test_pr_gate.py`
- [ ] `SP20-T004` Owner: `coordinator` | Done when: docs explain fixture corpus | Verify: `rg "examples/fixtures" README.md docs/ADOPTION_MATRIX.md`

## 并行拆分

P0/P1 workers own their fixture families. Coordinator owns PR fixtures and docs.

## 验证

- `uvx pytest -q`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH20`

## Handoff Notes

Fixtures are benchmark inputs, not claims about current GitHub state.
