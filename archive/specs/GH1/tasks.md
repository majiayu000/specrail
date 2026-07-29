# Task Plan

## Linked Issue

GitHub issue: `#1`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP1-T001` Owner: `evaluator` | Done when: action policy config is parseable and validates known routes | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH1`
- [ ] `SP1-T002` Owner: `evaluator` | Done when: route evaluation returns stable `allowed`, `warn`, `needs_human`, or `blocked` results | Verify: `uvx pytest -q`
- [ ] `SP1-T003` Owner: `docs` | Done when: agent-facing usage explains the evaluator and human gate boundaries | Verify: `rg "route_gate|needs_human|human" AGENT_USAGE.md README.md`

## 并行拆分

Evaluator work owns deterministic checks and schemas. Docs work owns agent-facing usage text.

## 验证

- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH1`
- `uvx pytest -q`

## Handoff Notes

This task plan records the historical GH1 packet for all-spec validation. It does not grant agents final approval, merge, or security authority.
