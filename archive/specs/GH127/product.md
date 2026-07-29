# Product Spec

## Linked Issue

GH-127

complexity: trivial

## 用户问题

`origin/main@bf86866` 的 `tests/test_pr_gate.py` 为 887 行，超过 VibeGuard U-16
的 800 行硬上限。AST 审计同时发现
`test_pr_gate_blocks_missing_review_source` 在第 396、617 行重复定义；模块导入时后者
覆盖前者，导致源码有 52 个 test 定义但仅 51 个唯一 test 名进入实际 collection。

## 目标

- 按 support、sensitive/core 与 terminal review/merge record 边界拆分测试，使三个允许
  文件均严格少于 800 行。
- 删除当前从未被收集的第 396 行遮蔽定义，保留第 617 行当前实际运行的同名定义。
- 保持 51 个实际测试函数、3 个 helper、参数化后的 69 cases、断言强度和生产行为不变。
- 拆分后所有 54 个保留函数名唯一且函数 AST 与基线精确一致。

## 非目标

- 不修改 `checks/pr_gate.py` 或其他生产代码。
- 不新增、删除或改变实际收集的 PR gate case。
- 不放宽断言，不新增 skip/xfail，不修改 fixture、schema、workflow、CI 或依赖。
- 不顺带处理其他文件。

## Behavior Invariants

1. B-001 编辑前的 69 个 normalized pytest nodes 在编辑后必须恰好各出现一次。
2. B-002 三个允许文件均严格少于 800 行；support 不以 `test_` 开头、无可收集测试，
   3 个 helper 保持单一来源。
3. B-003 基线两个同名定义中，仅删除第 396 行、当前未被 Python namespace 和 pytest
   暴露的早期定义；第 617 行当前运行定义及其他 54 个函数 AST 必须原样保留。
4. B-004 production/module 绑定、参数化、异常预期、断言与 0 个 skip/xfail 保持不变；
   禁止 wrapper、`pytestmark` 或 silent fallback。
5. B-005 focused outcomes、全库 553-case collection/执行与 SpecRail workflow 保持通过；
   committed scope 精确限制为三个测试/support 路径。

## 验收标准

- [ ] 三个允许文件均严格少于 800 行且主题边界清晰。
- [ ] 51 test functions、3 helpers、54 unique functions 与 69 focused cases 闭合。
- [ ] 基线遮蔽定义删除证明、54-function AST parity 与 production identity 通过。
- [ ] focused outcome 与编辑前同环境一致（当前平台 69 passed），全库保持 553 passed。
- [ ] single/all-spec workflow、scope、protected paths 与 whitespace 全绿。

## 边界情况清单

| 类别 | 判定 |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004；缺 evidence/review source/ordering 字段负例原样保留 |
| 错误与失败路径 | covered: B-004；blocked/needs_human/reason/missing 断言不变 |
| 授权/权限 | covered: B-004；human authorization、self-review 与 resolver ownership 用例不变 |
| 并发/竞态 | covered: B-004；gate/query/merge 时序与 head identity 用例不变 |
| 重试/幂等 | covered: B-004；independent retry 与 successor re-review 用例不变 |
| 非法状态转换 | covered: B-004；pending CI、unresolved thread、unknown merge path 负例不变 |
| 兼容/迁移 | covered: B-001, B-003；实际 pytest collection 与 production API 不变 |
| 降级/回退 | covered: B-004；缺证据不得 silent success |
| 证据与审计完整性 | covered: B-001 至 B-005；nodes、AST、identity、scope、fresh tests 闭合 |
| 取消/中断 | N/A：test-only commit 可整体 revert，无数据迁移 |

## 发布说明

无用户可见行为、迁移或发布要求；implementation 为 test-only maintainability change。
