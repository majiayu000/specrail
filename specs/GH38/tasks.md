# Task Plan

## Linked Issue

GH-38

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP38-T001` Owner: checks | Done when: `SPEC_STATUSES` 只在 `checks/specrail_lib.py` 定义一次且 `checks/runtime_ledger_gate.py` 从该处导入,gate 行为不变 | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`
- [ ] `SP38-T002` Owner: tests | Done when: schema `spec_status.enum` 与 `SPEC_STATUSES` 的一致性测试存在,单侧修改会失败 | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k schema`
- [ ] `SP38-T003` Owner: skills | Done when: `implx` 与 `specrail-implement-queue` 的 spec_status 段改为引用规范定义,`skills-lock.json` 哈希同步 | Verify: `python3 checks/check_workflow.py --repo .`
- [ ] `SP38-T004` Owner: templates | Done when: 两份 `tranche_checkpoint.md` 模板引用规范定义且 en/zh parity 保持 | Verify: `python3 checks/check_workflow.py --repo .`

## 并行拆分

- Checks lane: `checks/specrail_lib.py`、`checks/runtime_ledger_gate.py`、
  `tests/test_runtime_ledger_gate.py`。
- Docs lane: `skills/implx/SKILL.md`、
  `skills/specrail-implement-queue/SKILL.md`、
  `templates/tranche_checkpoint.md`、`templates/zh-CN/tranche_checkpoint.md`、
  `skills-lock.json`。
- 两条 lane 文件不重叠,可并行;lockfile 由 Docs lane 独占。

## 验证

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`

## Handoff Notes

- 与 GH-40(schema 强制)相关但独立:本任务只对账 enum,不做实例校验。
- 与 GH-42(implx 收缩)在技能文档上有触碰面,若并行执行需先合本任务,
  GH-42 基于收敛后的引用改写。
