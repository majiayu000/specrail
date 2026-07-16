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

1. B-001 implementation 开始时必须记录实际 `impl_base_sha`，并在任何编辑前保存
   GitHub PR evidence 的完整 normalized pytest node ID multiset。拆分后该 multiset
   必须逐项相同；当前 spec 基线 `3547af8` 为 42 个 `test_*` 函数和 79 个
   collected cases。若实际基线已改变该集合，必须先停止并更新 spec。
2. B-002 `tests/test_github_pr_evidence.py`、本次新增的每个同主题测试模块及共享
   support 文件必须分别严格少于 800 行；support 不得包含 `test_*` 函数，也不得
   复制 helper 或测试 payload 来规避行数门禁。
3. B-003 implementation committed diff 的允许路径闭集为
   `tests/test_github_pr_evidence.py`、
   `tests/test_github_pr_evidence_approval.py`、
   `tests/test_github_pr_evidence_cli.py`、
   `tests/github_pr_evidence_test_support.py`；任何其他路径均阻断。
4. B-004 基线文件中的全部顶层函数（当前为 42 tests + 8 helpers）的
   `ast.dump(..., include_attributes=False)` 必须与拆分后四个允许文件中的同名函数
   完全一致；测试模块引用的 production classes、functions 与 constants 必须仍与
   原模块对象 identity 相同；不得新增 module-level 或 function-level skip/xfail。
5. B-005 focused tests、全量 pytest、SpecRail workflow 校验和 whitespace 检查
   必须全部通过；全库 collected test 数必须等于实际 `impl_base_sha` 的 fresh
   基线，当前 `3547af8` 的初始证据为 553。

## 验收标准

- [ ] 四个允许文件均严格少于 800 行，且主题边界从文件名和内容可识别。
- [ ] 相对实际 `impl_base_sha`，normalized node multiset、50-function AST mapping
  与全库 collected count 完全一致。
- [ ] committed diff 仅包含 B-003 的四个路径；生产、schema、fixture、CI 和 spec
  没有 implementation diff。
- [ ] focused/full pytest、workflow checks 与 `git diff --check` 全部通过。

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
| 证据与审计完整性 | covered: B-001, B-002, B-005；node、AST、行数和 fresh tests 共同证明 |
| 取消/中断 | N/A：原子 test-only commit 可直接回滚，无持久化状态 |

## 发布说明

无用户可见行为或迁移要求；implementation PR 标记为 test-only maintainability
change，并保留独立人工 review 与 merge gate。
