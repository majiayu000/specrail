# Task Plan

## Linked Issue

GitHub issue: `#16`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP16-T001` Owner: `p0-worker` | Done when: `checks/github_issue_evidence.py` outputs route evidence | Verify: `uvx pytest -q tests/test_github_issue_evidence.py`
- [ ] `SP16-T002` Owner: `p0-worker` | Done when: issue evidence schema and fixtures exist | Verify: `python3 checks/check_workflow.py --repo .`
- [ ] `SP16-T003` Owner: `coordinator` | Done when: README/AGENT_USAGE/PLAN/skill mention issue adapter boundary | Verify: `rg "github_issue_evidence" README.md AGENT_USAGE.md PLAN.md skills`

## 并行拆分

P0 worker owns adapter/schema/tests/issue fixtures. Coordinator owns shared docs.

## 验证

- `uvx pytest -q`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH16`

## Handoff Notes

Adapter must never write remote GitHub state.
