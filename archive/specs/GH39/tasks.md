# Task Plan

## Linked Issue

GH-39

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP39-T001` Owner: checks | Done when: `RUNTIME_STATE_MAPPING` 常量存在,覆盖 gate 全部状态集合,每个状态映射到 `states.yaml` 状态列表或标记 `runtime_only` | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k mapping`
- [ ] `SP39-T002` Owner: tests | Done when: 哨兵测试双向核对映射键集合与 gate 状态集合,并验证映射目标在 `states.yaml` 中存在 | Verify: 临时添加未声明状态可复现失败
- [ ] `SP39-T003` Owner: docs | Done when: schema `state` 字段 description 与两份 `tranche_checkpoint.md` 模板声明 runtime 词表定位 | Verify: `python3 checks/check_workflow.py --repo .`
- [ ] `SP39-T004` Owner: checks | Done when: gate 对既有 fixtures 的决策输出与主分支一致 | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`

## 并行拆分

- Checks lane: `checks/runtime_ledger_gate.py`、
  `tests/test_runtime_ledger_gate.py`。
- Docs lane: `schemas/runtime_checkpoint.schema.json`、
  `templates/tranche_checkpoint.md`、`templates/zh-CN/tranche_checkpoint.md`。
- 文件不重叠,可并行。

## 验证

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`

## Handoff Notes

- 依赖决策:映射常量落点跟随 GH-38(若 `SPEC_STATUSES` 进
  `specrail_lib`,映射同去;否则留在 gate 文件顶部)。建议先合 GH-38。
- tech.md 中的映射表是方向示例,实现时需逐状态核对语义并在 PR 描述中
  说明每个非显然映射的理由。
