# Product Spec

## Linked Issue

GH-199

## 用户问题

implx 在 review-fix 推动 PR head 后，经常把 exact-head 证据约束解释为必须再次
执行本地全量测试。即使新 head 的 CI 已覆盖完整测试集合，协调者仍重复支付
full-suite、clippy 与确定性检查的等待成本，导致一次小修复把每 PR 的验证时间成倍
放大。

## 目标

- 明确本地全量测试、focused tests 与 current-head CI rollup 的职责边界。
- 保留 exact-head、CI 覆盖完整性和 fail-closed 证据要求。
- 将昂贵的本地 full-suite 执行预算限制为每个 PR 一次，除非已声明的失效条件发生。

## 非目标

- 不允许用 focused tests 替代缺失、失败或覆盖不完整的 CI。
- 不改变 `pr_gate` 的 current-head、review thread、merge state 或人工授权要求。
- 不为未知 CI check 猜测覆盖范围，也不修改 consumer 仓库的测试命令。

## Behavior Invariants

1. B-001 当实现仍处于迭代阶段时，执行者必须只运行与本次改动直接相关的 focused
   tests；不得在每次编辑后自动运行完整套件。
2. B-002 当 PR 首次形成 merge-candidate head 时，执行者必须运行一次本地
   full-suite 与仓库要求的确定性检查，并把该 head 记录为
   `full_test_head_sha`。
3. B-003 当 review-fix 产生新 head，且改动未触及 build/test 配置或 CI 覆盖输入时，
   执行者必须运行修复对应的 focused tests，并以新 head 的绿色 CI rollup 承担
   full-suite 证据，不得无条件重跑本地完整套件。
4. B-004 如果 current-head CI 缺失、失败、覆盖范围未知，或 review-fix 修改了
   build/test 配置，则 B-003 的复用路径失效，必须重新取得覆盖完整的本地或 hosted
   证据；不得把缺失证据表述为通过。
5. B-005 `exact-head` 只约束证据归属：每项被消费的证据必须明确绑定或经内容绑定
   证明可复用于 current head；该术语本身不得被解释为强制重新执行同一命令。
6. B-006 当 CI check 的声明覆盖类别不包含被修改的内容类别时，该 check 不得替代
   对应的本地 full-suite 证据；未知 check 必须 fail closed。
7. B-007 当 `max_full_test_runs_per_head` 预算已用尽但 B-004 要求重跑时，执行者必须
   停止并记录预算/证据冲突，不能通过删除旧记录或改写计数继续。
8. B-008 当验证中断、head 再次变化或证据采集期间发生竞态时，先前未完成的结果不得
   被升级为成功；恢复后必须针对当前事实重新取得终态证据。

## 验收标准

- [ ] queue 合同明确规定首次 merge-candidate 的一次本地 full-suite。
- [ ] review-fix head 使用 focused tests + current-head CI 的条件和失效条件均有说明。
- [ ] exact-head 被定义为证据归属而非无条件重执行。
- [ ] 缺失/失败/未知覆盖的 CI 路径继续 fail closed。
- [ ] runtime budget、CI component coverage 与 PR evidence 的现有确定性测试保持绿色。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-004 B-006 |
| 错误与失败路径 | covered: B-004 B-007 B-008 |
| 授权/权限 | N/A：本变更不改变 merge 或 review 授权 |
| 并发/竞态 | covered: B-008 |
| 重试/幂等 | covered: B-003 B-007 B-008 |
| 非法状态转换 | covered: B-007 B-008 |
| 兼容/迁移 | covered: B-005；既有 exact-head gate 保持兼容 |
| 降级/回退 | covered: B-004 B-006 |
| 证据与审计完整性 | covered: B-002 B-005 B-006 B-007 |
| 取消/中断 | covered: B-008 |

## 发布说明

这是 agent 执行合同的性能纠错，不改变产品 API。consumer 仍可要求更严格的本地验证，
但不得把缺失 CI 或未知覆盖静默当作绿色证据。
