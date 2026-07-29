# Product Spec

## Linked Issue

GH-124

complexity: trivial

## 用户问题

`origin/main@7ad5771` 的 `tests/test_check_workflow.py` 已达到 966 行，超过仓库
VibeGuard U-16 的 800 行硬上限。该模块同时承载 required assets、pack validation、
spec packet path trust、CLI discovery 与 auth mode policy 测试，导致定位、审查和
后续修改的所有权边界持续变差。

## 目标

- 按稳定主题拆分 workflow checker 测试，使每个相关文件严格少于 800 行。
- 保持 54 个测试函数、参数化后的 72 cases、3 个 helper、57 个顶层函数、断言强度
  和生产行为不变。
- 让 spec/path trust 测试与 asset/config/policy 测试可独立审查，同时保留共享
  bootstrap/helper 的单一来源。

## 非目标

- 不修改 `checks/`、schema、fixture、workflow、CI 或依赖。
- 不新增、删除或改变 workflow checker 行为。
- 不删除测试、不放宽断言、不新增或删除 skip/xfail，不修改 pytest 基础设施。
- 不顺带拆分其他超限文件；其他候选必须单独验证和立项。

## Behavior Invariants

1. B-001 拆分前的每个 workflow checker 测试及参数化 case，拆分后必须恰好执行
   一次；不得新增、删除、重复或遗漏 case。
2. B-002 三个允许文件必须严格少于 800 行；support 使用非 `test_` 文件名、不得
   成为 pytest 收集入口，也不得复制 helper。
3. B-003 本项只改变 workflow checker 测试的文件组织；production、schema、fixture、
   CI、spec 与其他测试资产保持不变。
4. B-004 全部既有测试和 helper 的输入、参数化值、production 调用、异常预期与断言
   必须保持不变；15 个既有平台条件式 `pytest.skip` 必须一对一保留，不得新增、
   删除或改变 skip/xfail，也不得引入 wrapper 或 silent fallback。
5. B-005 focused suite 与全库验证必须保持基线的收集数量和通过状态，SpecRail
   workflow 合同继续有效。

## 验收标准

- [ ] 三个允许文件均严格少于 800 行，且主题边界从文件名和内容可识别。
- [ ] 54 个测试函数、72 个 focused cases、3 个 helper 与 57 个顶层函数一对一保留。
- [ ] implementation 仅重组约定的 workflow checker 测试/support 文件，不改生产资产。
- [ ] focused suite 的 passed/skipped/xfailed/xpassed outcome counts 与编辑前同环境基线
  完全一致（当前平台证据为 72 passed）；全库保持 553 passed。
- [ ] 15 个既有 skip/xfail 调用的 AST 与 production symbol identity 完全一致。
- [ ] workflow、single-spec/all-spec、whitespace 与 committed-scope 验证全部通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004；缺 required files、spec artifacts 与 configured root 负例原样保留 |
| 错误与失败路径 | covered: B-004；异常类型、CLI exit code、reason 与 fail-closed 断言不变 |
| 授权/权限 | covered: B-004；auth mode、required human gate 与 path trust 负例不变 |
| 并发/竞态 | covered: B-004；symlink identity/resolve 边界完整保留，不引入共享可写状态 |
| 重试/幂等 | N/A：测试拆分不增加重试或持久化操作 |
| 非法状态转换 | covered: B-004；unknown/persisted auto auth mode 负例不变 |
| 兼容/迁移 | covered: B-001, B-003；测试语义与 production API 不变 |
| 降级/回退 | covered: B-004；缺资产、错误配置和非法路径不得变成 silent success |
| 证据与审计完整性 | covered: B-001, B-002, B-005；case、AST、行数、scope 和 fresh tests 均须闭合 |
| 取消/中断 | N/A：原子 test-only commit 可直接回滚，无数据迁移 |

## 发布说明

无用户可见行为、迁移或发布要求；implementation PR 标记为 test-only maintainability
change，并继续接受独立 review、CI 与 merge gate。
