# Task Plan

## Linked Issue

GitHub issue: `#24`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP24-T001` Owner: `issue-worker` | Done when: issue adapter emits `state_source` and `state_trusted` | Verify: `uvx pytest -q tests/test_github_issue_evidence.py`
- [ ] `SP24-T002` Owner: `issue-worker` | Done when: route gate treats body hint as human-gated evidence | Verify: `uvx pytest -q tests/test_github_issue_evidence.py`
- [ ] `SP24-T003` Owner: `coordinator` | Done when: docs describe trusted label vs untrusted body hint | Verify: `rg "state_source|state_trusted|body hint" README.md AGENT_USAGE.md PLAN.md`

## 并行拆分

Issue worker owns adapter, schema, issue fixtures, route gate, and focused tests. Coordinator owns docs and final full-suite verification.

## 验证

- `uvx pytest -q tests/test_github_issue_evidence.py`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH24`

## Handoff Notes

Body hints remain useful evidence, but they cannot replace maintainer readiness labels for human-gated routes.
