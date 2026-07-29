# Tech Spec

## Linked Issue

GH-38

## Product Spec

`specs/GH38/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| gate | `checks/runtime_ledger_gate.py` | 顶部定义 `SPEC_STATUSES` 字面量集合 | 应改为从 `specrail_lib` 导入 |
| lib | `checks/specrail_lib.py` | 无 spec_status 概念 | 规范常量的落点 |
| schema | `schemas/runtime_checkpoint.schema.json` | `spec_status.enum` 独立维护 | 一致性测试的对照面 |
| skills | `skills/implx/SKILL.md`、`skills/specrail-implement-queue/SKILL.md` | 各自复述五个状态的完整语义 | 改为引用规范定义 |
| templates | `templates/tranche_checkpoint.md`、`templates/zh-CN/tranche_checkpoint.md` | 各自列出枚举 | 与 lock/parity 校验联动 |
| tests | `tests/test_runtime_ledger_gate.py` | 覆盖 gate 行为 | 新增一致性测试的落点 |

## 设计方案

1. 在 `checks/specrail_lib.py` 新增模块级常量
   `SPEC_STATUSES = frozenset({...})`(五个现值),紧邻现有决策枚举。
2. `checks/runtime_ledger_gate.py` 删除本地字面量,改为
   `from specrail_lib import SPEC_STATUSES`(保持该文件现有的 import 方式,
   与其他 gate 脚本一致)。
3. 新增测试 `test_spec_status_schema_matches_lib`:用 `json.load` 读取
   schema,定位 `spec_status` 的 `enum`,断言
   `set(enum) == set(SPEC_STATUSES)`;schema 缺字段时断言失败并输出路径。
4. 两个技能文档与两份模板:把完整枚举语义收敛为一句"规范定义见
   `checks/specrail_lib.py` 的 `SPEC_STATUSES`"加简表;同步
   `skills-lock.json` 哈希。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `specrail_lib.py` + `runtime_ledger_gate.py` | `pytest -q tests/test_runtime_ledger_gate.py` |
| P2 | 新一致性测试 | `pytest -q tests/test_runtime_ledger_gate.py -k schema_matches` |
| P3 | skills + templates + lockfile | `python3 checks/check_workflow.py --repo .` |
| P4 | gate 负例路径 | 现有 invalid spec_status 测试用例 |

## 数据流

无运行时数据流变化。输入(checkpoint JSON)与输出(决策 JSON)格式不变;
仅常量定义位置移动与新增只读测试。

## 备选方案

- 让 gate 在运行时读取 schema 的 enum 作为真源:被否——gate 需要在
  schema 缺失/损坏时仍能独立决策,且运行时耦合比测试期对账更脆弱。
- 用代码生成从常量渲染 schema:被否——引入生成步骤,超出问题规模
  (过度设计)。

## 风险

- Security: 无新增面;不引入依赖。
- Compatibility: checkpoint 格式与 gate 决策不变;唯一风险是技能文档
  措辞变化影响 agent 理解,通过保留简表缓解。
- Performance: 无影响。
- Maintenance: 净收益;重复定义从 6 处降为 1 处代码 + 1 处 schema
  (由测试对账)+ 文档引用。

## 测试计划

- [ ] Unit tests: schema-enum 一致性测试;现有 gate 套件回归。
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`。
- [ ] Manual verification: 构造未知 `spec_status` 的 checkpoint,确认仍
      `blocked` 且报错信息含该值。

## 回滚方案

单 commit 回滚即可:恢复 gate 内字面量、删除一致性测试、还原文档与
lockfile。无数据迁移。
