# Product Spec

## Linked Issue

GH-117

complexity: trivial

## 用户问题

`origin/main@3547af8` 的 `tests/test_github_pr_evidence.py` 已增长到 1281 行，
超过仓库 VibeGuard U-16 的 800 行硬上限。该文件同时覆盖 approved-spec label
timeline、PR file snapshot、evidence/review-thread normalization、partial issue
relation、CLI fake-gh 与 query snapshot race，导致定位、评审和后续修改的冲突成本
持续升高。

## 目标

- 按稳定主题边界拆分 GitHub PR evidence 测试，使每个相关文件严格少于 800 行。
- 保持拆分前的测试函数、参数化案例、断言强度和生产行为不变。
- 让 approval/snapshot、evidence/review relation 与 CLI/query lifecycle 后续可独立评审。

## 非目标

- 不修改 `checks/github_pr_evidence.py`、`checks/github_pr_snapshot.py`、
  `checks/github_approved_spec_evidence.py` 或其他生产代码。
- 不新增、删除或改变 PR evidence、review-thread 或 PR gate 行为。
- 不删除测试、不放宽断言、不添加 skip/xfail，不修改 fixture/schema/CI。
- 不顺带拆分其他超大测试文件；每个候选必须单独验证和立项。

## Behavior Invariants

1. B-001 拆分前存在的每个 GitHub PR evidence 测试及其参数化案例，拆分后都必须
   恰好执行一次；不得新增、删除、重复或遗漏案例。
2. B-002 每个相关测试模块与共享 support 文件必须分别严格少于 800 行；support
   不得成为测试收集入口，也不得复制 helper 或测试 payload。
3. B-003 本项只改变 GitHub PR evidence 测试的组织结构；production、schema、fixture、
   CI、spec 和其他测试均保持不变。
4. B-004 每个既有测试和 helper 的输入、参数化值、production 调用、异常预期与断言
   必须保持不变；不得把任何路径改成 skip、xfail、wrapper 或 silent fallback。
5. B-005 拆分后的 focused suite 与全库验证必须保持基线的收集数量和通过状态，且
   SpecRail workflow 合同继续有效。

## 验收标准

- [ ] 四个允许文件均严格少于 800 行，且主题边界从文件名和内容可识别。
- [ ] 42 个测试函数、79 个参数化后 cases 与 8 个 helper 一对一保留，输入、调用和
  断言没有变化。
- [ ] implementation 仅重组约定的 GitHub PR evidence 测试/support 文件，其他资产无改动。
- [ ] focused/full suite 与 SpecRail workflow validation 全部通过，全库保持实现开始时
  确认的 collection 基线（当前证据为 553 cases）。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004；既有 malformed/missing payload 负例原样保留 |
| 错误与失败路径 | covered: B-004；异常类型、message match 与 fail-closed 断言不变 |
| 授权/权限 | covered: B-004；approval、resolver role、human authorization 负例不变 |
| 并发/竞态 | covered: B-001, B-004；query snapshot drift 案例完整保留 |
| 重试/幂等 | covered: B-001, B-004；pagination 与 double-snapshot 案例完整保留 |
| 非法状态转换 | covered: B-004；partial/closing relation 与 issue state 负例不变 |
| 兼容/迁移 | covered: B-001, B-003；测试契约与 production API 不变 |
| 降级/回退 | covered: B-004；缺证据路径不得变成 silent success |
| 证据与审计完整性 | covered: B-001, B-002, B-005；全部案例、文件边界和 fresh tests 均须保留 |
| 取消/中断 | N/A：原子 test-only commit 可直接回滚，无持久化状态 |

## 发布说明

无用户可见行为或迁移要求；implementation PR 标记为 test-only maintainability
change，并保留独立人工 review 与 merge gate。
