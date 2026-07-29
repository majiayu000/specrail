# Product Spec

## Linked Issue

GH-202

## 用户问题

implx 为小型 fastlane PR 提供了协调者自评通道，但现有门禁只检查 checkpoint
自报的 `pr_tier` 与字段形状：超大 diff、受保护路径、缺失
`enforcement_sensitive` 的项目仍可能被当作 fastlane。该通道既没有由
current-head GitHub snapshot 证明 tier，也没有在 PR gate 与 runtime gate 之间
绑定同一份分类事实，导致“降低 reviewer lane 固定成本”变成可绕过独立审查的
fail-open 路径。

## 目标

- 仅让由可信 current-head evidence 证明的小型、非受保护改动使用
  `self_review_authorization.basis=fastlane_policy`。
- 让 PR evidence、`pr_gate` 结果与 runtime checkpoint 消费同一组 tier/敏感性事实。
- 保留 exact-head 本地 review artifact、CI、review threads、merge state 和人工合并
  授权等其余门禁。
- 对缺失、漂移、冲突或无法分类的证据 fail closed。

## 非目标

- 不允许 self-review 获得 `standard_auto` 合并授权。
- 不放宽 standard/heavy PR 的独立 reviewer lane 要求。
- 不把 checkpoint 自报、PR body 声明或实现者生成的 attestation 单独视为可信 tier
  证明。
- 不改变 consumer 仓库自行采用更严格 fastlane 阈值或受保护路径集合的能力。

## Behavior Invariants

1. B-001 当 `review_source=self_review` 且
   `self_review_authorization.basis=fastlane_policy` 时，PR gate 只有在 exact
   current head 的可信文件快照证明 `changed_lines <= 50`、`touched_paths` 非空且
   不含受保护路径后才可豁免 `lane_failures`。
2. B-002 当 fastlane 自评被请求时，`enforcement_sensitive` 必须由可信分类显式为
   `false`；字段缺失、`null`、`true` 或与路径分类冲突均必须阻断。
3. B-003 当 diff 超过阈值、触及 API/schema、migration、auth/security 或 CI
   workflow 等受保护路径，或无法取得完整文件快照时，系统必须拒绝
   `fastlane_policy`，不得由协调者自报覆盖分类结果。
4. B-004 PR evidence 必须记录 tier 分类所依据的 current-head SHA、变更行数、完整
   路径集合与可信来源；head 在采集前后变化时不得产出可消费的 fastlane 证据。
5. B-005 runtime checkpoint 选择 fastlane 自评时，必须逐字段复制同一 current-head
   `pr_gate` 结果中的 `pr_tier`、`pr_tier_evidence`、敏感性结论与证据绑定；任何缺失
   或不一致均阻断。
6. B-006 即使 fastlane 分类有效，self-review 仍必须提供通过
   `review_json_gate`/manifest 语义校验的 exact-head 本地 review artifact，并满足
   CI、未解决线程、clean merge state 和 linked-work 要求。
7. B-007 review 模式下 fastlane 自评只豁免 reviewer lane failure 前置；每个 PR
   仍需当前会话的人工 merge authorization，且 self-review 永远不能满足
   `standard_auto` 的独立证明要求。
8. B-008 auto 模式若由显式调用提供 standing merge authorization，也只有在
   current-head `pr_gate=allowed`、CI 绿色、线程已解决、merge state clean 且非敏感
   时才可继续；fastlane 自评本身不授予 merge 权限。
9. B-009 当分类证据、review artifact、PR head 或敏感性 registry 在验证期间漂移，
   先前结果必须失效；重试必须重新采集 current-head 事实而不是复用旧 checkpoint。
10. B-010 当 fastlane 自评流程被取消、中断或证据仅取得部分结果时，恢复后必须从
    GitHub/本地 artifact 的终态重新验证；不得把未完成采集升级为允许。

## 验收标准

- [ ] 超过 50 行、受保护路径、缺失/`null` 敏感性和自报 tier 均无法通过
  `fastlane_policy`。
- [ ] GitHub PR adapter 产生 current-head、可审计的 changed-lines/path tier
  evidence。
- [ ] `pr_gate` 仅对可信 fastlane 自评豁免 `lane_failures`，普通 self-review
  规则不变。
- [ ] runtime checkpoint 必须与 current `pr_gate` tier/敏感性结果精确一致。
- [ ] exact-head review artifact、CI、thread、merge 与 human authorization
  门禁保持有效。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001 B-002 B-003 B-005 |
| 错误与失败路径 | covered: B-002 B-003 B-004 B-009 B-010 |
| 授权/权限 | covered: B-006 B-007 B-008 |
| 并发/竞态 | covered: B-004 B-009 |
| 重试/幂等 | covered: B-009 B-010 |
| 非法状态转换 | covered: B-005 B-007 B-008 |
| 兼容/迁移 | covered: B-003；旧自报证据将 fail closed 并回退到独立 reviewer |
| 降级/回退 | covered: B-003 B-007 |
| 证据与审计完整性 | covered: B-001 B-004 B-005 B-006 B-009 |
| 取消/中断 | covered: B-010 |

## 发布说明

这是安全收紧：既有只含 checkpoint 自报字段的 `fastlane_policy` 证据将不再被接受。
执行器需重新采集 current-head PR evidence；无法证明 fastlane 时回退到普通独立
reviewer lane，不得静默继续自评。
