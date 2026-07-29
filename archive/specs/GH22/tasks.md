# Task Plan

## Linked Issue

GitHub issue: `#22`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP22-T001` Owner: `ci-worker` | Done when: `checks/check_workflow.py` supports deterministic `--all-specs` discovery | Verify: `uvx pytest -q tests/test_evaluate.py`
- [ ] `SP22-T002` Owner: `ci-worker` | Done when: workflow-check CI uses `--all-specs` | Verify: `rg -- \"--all-specs\" .github/workflows/workflow-check.yml`
- [ ] `SP22-T003` Owner: `coordinator` | Done when: full pack validation covers all current spec packets | Verify: `python3 checks/check_workflow.py --repo . --all-specs`

## 并行拆分

CI worker owns validator, workflow, and focused tests. Coordinator owns final full-suite verification.

## 验证

- `uvx pytest -q tests/test_evaluate.py`
- `python3 checks/check_workflow.py --repo . --all-specs`

## Handoff Notes

Do not move discovery into GitHub Actions shell only; keep the deterministic behavior in the local validator.
