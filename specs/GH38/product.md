# Product Spec

## Linked Issue

GH-38

## 用户问题

`spec_status` 的五个枚举值(`complete`、`needs_tasks`、`needs_spec`、
`umbrella_covered`、`exception_allowed`)在 6 个文件中重复定义:gate 脚本、
JSON schema、两份 tranche checkpoint 模板、`implx` 与
`specrail-implement-queue` 两个技能文档。没有单一真源。任何词表调整都要
手工同步 6 处;schema 与 gate 之间没有一致性校验,可能静默分歧,导致
agent 依据 schema 认为合法的 checkpoint 被 gate 阻断,或反之。

## 目标

- `spec_status` 枚举在代码中只有一个规范定义位置。
- schema 中的 enum 与规范定义之间有自动化一致性校验,漂移即测试失败。
- 技能文档与模板引用规范定义,不再各自复述完整枚举语义。

## 非目标

- 不改变任何枚举值的语义。
- 不新增或删除枚举值。
- 不引入第三方 schema 校验依赖。
- 不改变 runtime ledger gate 的阻断行为。

## Behavior Invariants

1. `checks/specrail_lib.py` 暴露唯一的 `SPEC_STATUSES` 常量;
   `checks/runtime_ledger_gate.py` 导入该常量,gate 对合法与非法
   `spec_status` 值的判定行为与现状完全一致。
2. 存在一条确定性测试:读取 `schemas/runtime_checkpoint.schema.json` 中
   `spec_status` 的 enum,断言其集合与 `SPEC_STATUSES` 相等;任何一侧
   单独修改都会使测试失败。
3. `skills/implx/SKILL.md`、`skills/specrail-implement-queue/SKILL.md`、
   两份 `tranche_checkpoint.md` 模板中的 spec_status 说明指向规范定义
   位置;文档中列出的值与 `SPEC_STATUSES` 保持一致。
4. 对包含未知 `spec_status` 值的 checkpoint,gate 仍返回 `blocked`,
   错误信息不劣于现状。

## 验收标准

- [ ] `grep -rn "umbrella_covered" checks/` 只命中导入或引用
      `specrail_lib` 规范常量的位置,不再有第二处枚举字面量定义。
- [ ] schema-enum 一致性测试存在并通过。
- [ ] `python3 -m pytest -q tests/test_runtime_ledger_gate.py` 通过。
- [ ] `python3 checks/check_workflow.py --repo .` 与 `--all-specs` 通过。

## 边界情况

- schema 文件缺失或 enum 字段缺失时,一致性测试必须失败并给出可读原因,
  而不是跳过。
- `skills-lock.json` 记录了技能文件哈希:技能文档修改后必须同步更新
  lockfile,否则 `check_workflow` 会失败——这是预期护栏,不是回归。

## 发布说明

纯内部重构与测试加固,无对外行为变化,无迁移要求。checkpoint 文件格式
不变,已有 `.specrail/runtime/*.json` 无需修改。
