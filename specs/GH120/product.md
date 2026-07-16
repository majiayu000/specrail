# Product Spec

## Linked Issue

GH-120

complexity: trivial

## 用户问题

`origin/main@a899c558` 的 `tests/test_route_gate.py` 已达到 1023 行，超过仓库
VibeGuard U-16 的 800 行硬上限。该文件把 sensitive enforcement、approved spec、
artifact path、readiness state 与 duplicate work 等测试集中在一个模块中，导致后续
定位、审查和并行所有权的成本持续升高。

## 目标

- 按稳定主题边界拆分 route gate 测试，使每个相关文件严格少于 800 行。
- 保持 31 个测试函数、参数化后的 37 cases、5 个 helper、断言强度和生产行为不变。
- 让 sensitive/approved-spec 测试与通用 route/readiness/duplicate-work 测试可独立审查。

## 非目标

- 不修改 `checks/route_gate.py` 或其他生产代码。
- 不新增、删除或改变 route gate、sensitive enforcement、artifact 或 duplicate-work 行为。
- 不删除测试、不放宽断言、不添加 skip/xfail，不修改 fixture、schema、CI 或依赖。
- 不顺带拆分其他超限测试文件；其他候选必须单独验证和立项。

## Behavior Invariants

1. B-001 拆分前的每个 route gate 测试及参数化 case，拆分后必须恰好执行一次；
   不得新增、删除、重复或遗漏 case。
2. B-002 每个相关测试模块与共享 support 文件必须严格少于 800 行；support 使用
   非 `test_` 文件名、不得成为 pytest 收集入口，也不得复制 helper。
3. B-003 本项只改变 route gate 测试的文件组织；production、schema、fixture、CI、
   spec 与其他测试资产保持不变。
4. B-004 全部既有测试和 helper 的输入、参数化值、production 调用、异常预期与断言
   必须保持不变；不得引入 wrapper、skip、xfail 或 silent fallback。
5. B-005 focused suite 与全库验证必须保持基线的收集数量和通过状态，SpecRail
   workflow 合同继续有效。

## 验收标准

- [ ] 三个允许文件均严格少于 800 行，且主题边界从文件名和内容可识别。
- [ ] 31 个测试函数、37 个 focused cases、5 个 helper 与 36 个顶层函数一对一保留。
- [ ] implementation 仅重组约定的 route gate 测试/support 文件，不改生产资产。
- [ ] focused suite 为 37 passed，无 skip/xfail/xpass；全库保持 553 passed。
- [ ] workflow、single-spec/all-spec、whitespace 与 committed-scope 验证全部通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004；空 path、缺 artifact/duplicate evidence 负例原样保留 |
| 错误与失败路径 | covered: B-004；异常类型、reason 与 fail-closed 断言不变 |
| 授权/权限 | covered: B-004；approved spec、trusted state 和 forged evidence 负例不变 |
| 并发/竞态 | covered: B-001, B-004；base/head identity 与 spec incorporation 时序用例完整保留 |
| 重试/幂等 | N/A：测试拆分不增加重试或持久化操作 |
| 非法状态转换 | covered: B-004；unknown/untrusted readiness state 负例不变 |
| 兼容/迁移 | covered: B-001, B-003；测试语义与 production API 不变 |
| 降级/回退 | covered: B-004；缺证据路径不得变成 silent success |
| 证据与审计完整性 | covered: B-001, B-002, B-005；case、AST、行数、scope 和 fresh tests 均须闭合 |
| 取消/中断 | N/A：原子 test-only commit 可直接回滚，无数据迁移 |

## 发布说明

无用户可见行为、迁移或发布要求；implementation PR 标记为 test-only maintainability
change，并继续接受独立 review、CI 与 merge gate。
