# Product Spec

## Linked Issue

GH-143

## 用户问题

`auth_mode: review` 下所有 PR 一律逐 PR 请求人工合并授权（`skills/implx/SKILL.md:56`、`skills/specrail-implement-queue/SKILL.md:598`）。实际队列中大量 fastlane/standard tier 的 PR 证据完全齐备（CI rollup 绿、review threads 全部 resolved、pr_gate allowed、独立 reviewer lane verdict 干净），逐 PR 授权成为纯仪式性打断：人工回答永远是"可以合"，却阻塞队列吞吐。Owner 已在 issue #143 决策选 B（分级授权）：fastlane/standard 在证据齐备时自动授权合并，heavy/敏感面保留逐 PR 人工授权；并补充授权后新增 findings 的分级重确认规则。本 spec 只编码该已闭合决策，不重开设计辩论。

## 目标

- review 模式下引入 tier 分级合并授权：fastlane/standard tier 且全绿证据的 PR 免逐 PR 人工授权，记录 `authorization_tier: standard_auto`；heavy/敏感 tier 保留逐 PR 显式人工授权。
- 编码 owner 补充的分级重确认规则：授权后新增的机械性 findings 在原授权内修复复审合并、事后报告；critical 或扩大影响面的 findings 暂停并重新请求授权。
- 把 tier 授权语义接入既有强制点：`checks/runtime_ledger_gate.py` 的 merge_authorization 校验、`checks/pr_gate.py` 的 `_authorization_item`、两个 SKILL.md 的 auth_mode 章节。

## 非目标

- 不改变 `auth_mode: auto` 的任何语义（implx auto 的整跑站立授权、evidence gap 跳过规则不动）。
- 不新增 tier 分类体系：tier 沿用既有 `pr_tier` 字段（`skills/specrail-implement-queue/SKILL.md:86`）及其证据规则（changed-line 数、touched paths、CI tier check 为准）。
- 不弱化任何既有 gate：CI、reviewer-lane、review-thread、pr_gate、runtime ledger gate、self-review authorization、Bounded Tranche 规则全部保持。
- 不触碰 force-push、发布、跨仓库等既有硬边界。

## Behavior Invariants

1. B-001 当 `auth_mode: review`、PR 的 `pr_tier` 为 `fastlane` 或 `standard`、且全部绿色证据齐备（CI rollup passing、review threads 全部 resolved 且 unresolved_count 为 0、pr_gate decision 为 allowed、独立 reviewer lane verdict 为 clean 或 non_blocking）时，该 PR 免逐 PR 人工授权即为已授权合并；checkpoint item 应记录 `authorization_tier: standard_auto`，且 `merge_authorization.source` 指向 tier 授权策略（引用 GH-143 决策）而非当前会话人工消息。
2. B-002 当 `pr_tier` 为 `heavy`，或 PR 触及敏感面（gate 代码、enforcement、契约、授权语义、schema/迁移、安全面，含 `enforcement_sensitive: true` 的任何 item）时，review 模式应保持现状：当前会话内逐 PR 显式人工授权，tier 自动授权不适用；item 记录 `authorization_tier: heavy_manual`。
3. B-003 如果 `pr_tier` 缺失、无证据支撑（缺 changed-line 数或 touched paths 证据）或取值越界，授权判定应 fail-closed 按 `heavy` 处理，要求人工授权，不得默认取较轻 tier。
4. B-004 当 tier 分类存在争议（CI tier check 结论与自报 tier 不一致、reviewer lane 对 tier 提出异议）时，应按 `heavy` 处理并将争议列入人工决策，不得在争议未决时以 standard_auto 合并。
5. B-005 当任一绿色证据缺失或非绿（CI 未全过、存在未 resolved review thread、pr_gate decision 非 allowed、reviewer lane verdict 为 blocking 或缺失）时，standard_auto 不成立；tier 授权不得替代或补足任何证据缺口，该 PR 按既有规则等待证据或人工处理。
6. B-006 当 `checks/runtime_ledger_gate.py` 校验 merge-ready item 且其 `merge_authorization.source` 声明为 tier 授权时，gate 应额外要求：item 具有 `pr_tier` ∈ {fastlane, standard} 及其证据、`authorization_tier: standard_auto`、且 `enforcement_sensitive` 非 true；任一不满足即 blocked，错误信息指明缺失项。
7. B-007 当 `checks/pr_gate.py` 的授权项评估遇到 tier-scoped 授权证据（`authorization_tier: standard_auto` + `pr_tier` fastlane/standard 含证据 + 非敏感）时，授权项应判满足，decision 不因缺 `human_authorization` 落入 needs_human；heavy、敏感或 tier 证据缺失时仍要求 `human_authorization.actor`/`source`，行为与现状一致。
8. B-008 当授权（含 standard_auto 与人工授权）之后 bot/复审 lane 新增 findings、且全部 findings 均为机械性（严重度 ≤ important、不改变 PR 意图、不扩大 planned paths、不改变契约语义）时，应在原授权范围内修复、重新通过独立复审后直接合并，并在事后报告中逐条列明 finding 与处置；不需要重新请求授权。
9. B-009 当授权后新增 finding 中任一条为 critical，或其修复需要扩大 planned paths、改变契约语义或改变 PR 意图时，应暂停合并并重新请求人工授权；原授权对该 PR 即时失效，恢复合并以新授权为准。
10. B-010 如果新增 finding 的严重度缺失或无法判定，应按 critical 处理；如果"是否扩大影响面/改变契约语义"无法判定，应按扩大处理——重确认分级自身 fail-closed。
11. B-011 当 `auth_mode: auto` 时，本 spec 引入的 tier 授权与重确认规则不改变任何行为：auto 的站立授权、evidence-gap 跳过、self-review authorization 例外均保持现状；tier 授权仅在 review 模式生效，且在两种模式下均不弱化 reviewer-lane、ledger gate、Bounded Tranche 任何既有规则。
12. B-012 当以 standard_auto 完成一次合并时，checkpoint/报告应留存完整审计记录：`pr_tier` 与其证据、`authorization_tier`、四类绿色证据引用（CI、review_threads、pr_gate、reviewer lane）、以及（如发生）重确认 findings 的逐条处置；记录缺失时 `checks/runtime_ledger_gate.py` 应判 blocked，不得事后补授权。

## Acceptance Criteria

- [ ] review 模式下 fastlane/standard + 全绿证据的 PR 可零人工提问合并，checkpoint 记录 `authorization_tier: standard_auto`，有测试覆盖
- [ ] heavy/敏感 PR 在 review 模式仍被 ledger gate 与 pr_gate 要求人工授权；tier 缺失/歧义/争议 fail-closed 按 heavy，有测试覆盖
- [ ] 授权后机械性 findings 走"修复+复审+合并+事后报告"，critical/扩面 findings 触发暂停重授权，两条路径均写入 SKILL.md 并有 gate 侧校验
- [ ] `python3 checks/check_workflow.py --repo .` 与既有 pr_gate/runtime_ledger_gate 测试零改动全绿（B-007/B-011 兼容回归）

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-003 B-010（pr_tier 缺失或无证据 fail-closed 按 heavy；finding 严重度缺失按 critical） |
| Error / failure paths | covered: B-005 B-006（任一证据非绿即 standard_auto 不成立；gate 校验不满足即 blocked 并指明缺失项） |
| Authorization / permission | covered: B-001 B-002 B-007（tier 决定授权路径；heavy/敏感保留人工授权；pr_gate 授权项识别 tier-scoped 来源） |
| Concurrency / race | N/A: 授权判定为对既有串行 gate 证据的本地只读评估，沿用"gate query 先于 merge、不并行"的既有规则，无新增共享可变状态 |
| Retry / idempotency | covered: B-006 B-007（gate 对同一 checkpoint/evidence 重复评估结论一致，授权判定只读幂等，无跨进程状态） |
| Illegal state transitions | covered: B-002 B-006（heavy 或敏感 item 携带 standard_auto 是非法状态，ledger gate 判 blocked；争议未决即合并被 B-004 阻断） |
| Compatibility / migration | covered: B-007 B-011（既有 human_authorization 路径与 auto 模式语义零回归；tier 字段为既有 pr_tier，无迁移） |
| Degradation / fallback | covered: B-003 B-004 B-010（一切歧义显式降级到 heavy/critical 侧，降级可见于记录，不存在静默取轻） |
| Evidence / audit integrity | covered: B-001 B-012（standard_auto 合并必须留存 tier 证据、authorization_tier、四类绿色证据引用与重确认处置，缺失即 blocked） |
| Cancellation / interruption | covered: B-009（critical/扩面 finding 即时中止原授权并暂停合并；恢复以重新授权为准） |

## Rollout Notes

先合本 spec PR（授权语义变更本身按 heavy 流程走，owner 决策已注明），实现 PR 同样按 heavy 逐 PR 人工授权合并。实现顺序：先 checks 侧（ledger gate + pr_gate）带测试落地，再更新两个 SKILL.md 的 auth_mode 章节；SKILL.md 生效前 checks 侧新逻辑仅在证据声明 tier 授权时触发，未声明时零行为变化，可安全分步合入。
