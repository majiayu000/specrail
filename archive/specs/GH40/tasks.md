# Task Plan

## Linked Issue

GH-40

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP40-T001` Owner: checks | Done when: `specrail_lib.validate_instance` 支持 `type`/`required`/`properties`/`items`/`enum`/`additionalProperties`,不支持特性显式抛 `SpecRailError` | Verify: `python3 -m pytest -q tests/ -k validate_instance`
- [ ] `SP40-T002` Owner: schema | Done when: `runtime_checkpoint.schema.json` 的 required/properties 与 gate 结构要求一致(语义规则除外) | Verify: 删除 `resume_prompt` 负例使 schema 与 gate 同时拒绝
- [ ] `SP40-T003` Owner: tests | Done when: 合法 checkpoint 样例集全量通过实例校验,非法样例集与合法样例集在测试中显式区分 | Verify: `python3 -m pytest -q tests/ -k schema_instance`
- [ ] `SP40-T004` Owner: docs | Done when: SPEC.md 含唯一"契约权威"小节,README 链接,CHANGELOG 注明 schema 升级 | Verify: `python3 checks/check_workflow.py --repo .`

## 并行拆分

- Lib lane: `checks/specrail_lib.py` 与校验器单测(独立测试文件或
  `tests/test_specrail_lib.py`)。
- Schema lane: `schemas/runtime_checkpoint.schema.json` +
  `tests/test_runtime_ledger_gate.py` 中的实例校验测试。
- Docs lane: `SPEC.md`、`README.md`、`CHANGELOG.md`。
- Schema lane 依赖 Lib lane 的校验器签名,先合 Lib lane 或串行执行;
  Docs lane 完全独立。

## 验证

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`

## Handoff Notes

- 决策已定:走强制路线(理由见 tech.md 备选方案),不再两头模糊。
- 与 GH-38 的一致性测试互补:GH-38 对账 enum,本任务对账整体结构;
  实现时避免重复断言同一 enum。
- 校验器刻意不进 gate 运行时路径——这是设计约束,不是遗漏。
