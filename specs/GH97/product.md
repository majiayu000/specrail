# Product Spec

## Linked Issue

GH-97

## 用户问题

SpecRail 当前可以收集 PR head、CI、GitHub review thread 和一个调用方提供的
`review_source`，但不能证明独立 reviewer lane 已在同一个 final head 上完成，也不能证明
审查发生在 merge gate 和 merge dispatch 之前。review artifact 只表达
`APPROVE|REJECT`，head 更新后旧 findings 可能从证据链中消失，已解决 thread 也缺少足以
判断 resolver 是否有权清除阻塞项的身份信息。

对 `enforcement_sensitive` 变更，这会让未完成或失败的审查、旧 head 审查、调用方伪造的
source，甚至 implementer 自行解决的 actionable thread 被误当作可合并证据。外部 merge
绕过本地 gate 后，SpecRail 也没有稳定的 machine-readable violation 与 follow-up contract。

## 目标

- 用 schema-valid、exact-head 的终态 review artifact 代替裸 `review_source` 字符串。
- 对 `enforcement_sensitive` 分类、approved spec 和敏感 registry 冲突实行 fail-closed。
- 在 head 更新时完整保留旧 findings 的状态与关闭证据。
- 验证 actionable thread resolver 的身份、角色和必要的 re-review evidence。
- 分离 pre-merge gate 与 post-dispatch closure audit，并固定同-head 时间顺序。
- 为外部违规 merge 输出可持久化到下游队列的稳定 `required_follow_up` payload。

## 非目标

- 不授予 agent 最终批准、合并、release、security decision 或权限管理权。
- 不在 SpecRail 中直接创建、重开或关闭下游仓库 issue。
- 不把本地/advisory gate 描述为 GitHub server-side protection。
- 不让旧 review artifact 静默兼容新的 merge-ready 路径。
- 不把 `enforcement_sensitive` registry 写死为 remem 专属路径；consumer 提供 registry。

## Behavior Invariants

1. `B-001`：参与 merge-ready 的独立审查必须来自可读取且通过 schema/semantic gate 的
   review artifact，并绑定 current head、独立 reviewer lane、开始/完成时间、终态和显式
   clean/non-blocking verdict；裸 `review_source` 不构成独立审查证据。
2. `B-002`：pending、failed、cancelled、superseded、empty、`changes_requested`、任何
   blocking verdict，或 current-head artifact 中任一 blocking/actionable finding 都阻止
   merge-ready；GitHub thread rollup clean 不能覆盖 artifact finding。
3. `B-003`：新 head 的 artifact 必须完整携带上一有效 head 的每个 finding：稳定 ID、来源
   head、`resolved|unresolved|obsolete` 状态；`resolved|obsolete` 必须带非空关闭证据，
   `unresolved` 继续阻止。遗漏、重复、冲突或无关闭证据均 fail closed。
4. `B-004`：resolved actionable reviewer/human thread 必须保留 resolver identity 和可验证
   role。只有原 reviewer、带 current-head re-review evidence 的 successor reviewer lane，
   或获授权 human maintainer 能清除阻塞；implementer、orchestrator、coordinator、unknown、
   缺失 resolver 或无 re-review evidence 的 successor 均阻止。
5. `B-005`：consumer 可配置 machine-readable sensitive registry；gate 必须从受信任、
   规范化且受仓库边界约束的 changed paths/spec refs 自行计算 registry 命中，不能信任调用方
   裸 boolean。registry 命中但 `enforcement_sensitive` 缺失/为 false、声明 true 却没有
   approved spec，或声明与 registry 冲突时，route/PR gate 必须阻止；非敏感或 true +
   approved spec 的一致证据可继续。
6. `B-006`：pre-merge gate 必须验证
   `review_completed_at <= gate_started_at <= gate_completed_at`，且 review、CI、thread 和 gate
   绑定同一 final head。它不得要求尚未发生的 merge dispatch evidence。
7. `B-007`：dispatch 后的 merge wrapper/closure audit 必须验证
   `gate_completed_at < merge_dispatched_at <= merged_at` 和同一 final head。外部 merge 缺失
   完整链时返回 schema-valid violation 与 `required_follow_up`，不得报告合规闭环。
8. `B-008`：`required_follow_up` 至少包含稳定 violation code、repository、PR number、final
   head SHA 和 deterministic idempotency key；SpecRail 只输出 payload，不声称下游 issue 已创建。
9. `B-009`：self-review 只有在同一 PR/head 有可验证 reviewer-lane failure、独立人类 scoped
   authorization 且 human final review 仍被要求时才可作为恢复证据；否则 fail closed。
10. `B-010`：artifact/registry/API 输入不可读、格式错误、字段未知或证据不完整时返回明确
    blocked/error，不静默降级为旧行为。

## 验收标准

- [ ] review schema、review JSON gate、GitHub evidence 和 PR gate 共同实现 `B-001` 至 `B-004`。
- [ ] route/PR evidence schema 和 gate 实现 `B-005`，包含缺失、冲突、无 approved spec 的负例。
- [ ] pre-merge 正例不需要未来 dispatch；gate-before-review、head mismatch 负例阻止。
- [ ] executable closure audit 实现 `B-007`、`B-008`，dispatch-before-gate 和 external merge
      缺链负例输出稳定 follow-up payload。
- [ ] self-review fixtures 证明缺 lane failure、缺同-head授权或缺 human final review 均阻止。
- [ ] `python3 -m pytest`、focused tests 和 `python3 checks/check_workflow.py --repo .` 通过。

## 边界情况

- review artifact 文件不存在、不可读、非 object、schema 不匹配或 head 不匹配。
- reviewer lane 取消、崩溃、零输出，或多个 lane 同时对 current head 产生终态结果。
- 新 head artifact 遗漏旧 finding，或把同一 finding 同时标记为两个状态。
- GitHub thread outdated 但未解决；resolved thread 没有 resolver，或 resolver role map 不可信。
- gate 查询期间 PR head 变化；closure audit 发现 merge head 与 gate head 不同。
- consumer 没有 sensitive registry；只有显式声明 true 时才按敏感路径处理，不能猜测路径。

## 发布说明

这是 fail-closed 的 evidence contract 升级。旧 review artifact 可保留作历史审计，但不能用于
新的 merge-ready 判定。同步到 consumer 前必须先在 SpecRail main 上通过验证；本 issue 不
发布 release。
