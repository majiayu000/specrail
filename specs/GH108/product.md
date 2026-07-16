# Product Spec

## Linked Issue

GH-108

complexity: trivial

## 用户问题

`origin/main@f3251fe` 的 `tests/test_runtime_ledger_gate.py` 已增长到 1063 行，
超过仓库 VibeGuard U-16 的 800 行硬上限。该文件同时承载 runtime checkpoint
基础契约、敏感证据、full-queue、review/lane failure、budget/tranche 等多个主题，
使定位、评审和后续并行改动的冲突成本持续升高。

## 目标

- 按稳定主题边界拆分 runtime ledger 测试，使每个相关测试模块都低于 800 行。
- 保持拆分前的测试函数、参数化案例、断言强度和生产行为不变。
- 让后续 runtime ledger 变更可以在较小、职责清晰的测试模块中评审。

## 非目标

- 不修改 `checks/runtime_ledger_gate.py`、`checks/runtime_gate_rules.py` 或其他生产代码。
- 不新增、删除或改变 runtime checkpoint 行为。
- 不删除测试、不放宽断言、不修改 fixture/schema/CI 门禁。
- 不顺带拆分其他超大测试文件；每个候选必须单独验证和立项。

## Behavior Invariants

1. B-001 拆分后的 runtime ledger 测试必须保留基线中的全部 66 个
   `test_*` 函数及其参数化案例；`pytest --collect-only` 的收集总数保持 73，
   仅允许 node ID 的模块路径前缀因文件拆分而变化。
2. B-002 `tests/test_runtime_ledger_gate.py` 及本次新增的每个 runtime ledger
   测试模块必须严格少于 800 行；共享 helper 不得通过复制测试数据来换取行数下降。
3. B-003 implementation diff 不得修改 `checks/`、`schemas/`、
   `examples/fixtures/`、`.github/workflows/` 或既有 spec packet；生产行为、fixture
   内容与 CI 命令保持不变。
4. B-004 每个既有测试的断言语义和参数集合必须保持等价；禁止删除断言、放宽
   期望值、增加跳过标记或把失败路径改成静默成功。
5. B-005 拆分后，runtime ledger focused tests、全量 pytest、SpecRail workflow
   校验和 whitespace 检查必须全部通过，且测试总数不得低于基线 421。

## 验收标准

- [ ] 所有相关测试模块均低于 800 行，且主题边界在文件名和内容中可识别。
- [ ] 基线 66 个测试函数、73 个 collected cases、421 个全量测试均被保留。
- [ ] 生产代码、schema、fixture、CI 和其他 spec packet 没有改动。
- [ ] focused tests、全量 pytest、workflow checks 与 `git diff --check` 全部通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004；既有缺失字段负例必须原样保留 |
| 错误与失败路径 | covered: B-004；禁止弱化 blocked/error 断言 |
| 授权/权限 | covered: B-003, B-004；既有 merge/self-review 授权负例不变 |
| 并发/竞态 | N/A：纯测试文件重组，不引入并发状态 |
| 重试/幂等 | covered: B-001, B-004；既有 lane retry 案例完整保留 |
| 非法状态转换 | covered: B-001, B-004；既有非法状态测试完整保留 |
| 兼容/迁移 | covered: B-001, B-003；测试契约与生产接口不变 |
| 降级/回退 | covered: B-004；既有失败与降级判定不得变成成功 |
| 证据与审计完整性 | covered: B-001, B-002, B-005；以收集清单、行数和 fresh test 输出证明 |
| 取消/中断 | N/A：原子测试文件重组可通过丢弃 implementation commit 回滚 |

## 发布说明

无用户可见行为和迁移要求；implementation PR 应标记为 test-only maintainability
change，并保留独立人工 review 与 merge gate。
