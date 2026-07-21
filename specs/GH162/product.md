# Product Spec

## Linked Issue

GH-162

## 用户问题

SpecRail 目前只记录 `review_source` 的独立性，却不记录 review 在本地 reviewer
lane 还是托管服务中执行。真实运行已经把 GitHub `@codex review` 产生的 hosted
review 当成主要审查证据，而本地 `codex review` 从未执行。用户允许 hosted review
作为补充，但要求主要 review 必须来自绑定当前 head 的本地独立 reviewer。

## 目标

- 将“是否独立”与“在哪里执行”拆成两个可审计维度。
- 主要 review 只接受本地 CLI 或 native reviewer lane 的 exact-head artifact。
- hosted review 可保留为补充信息，但不能单独满足 merge gate。
- 同时收紧 PR gate 和 implx runtime ledger，避免两条门禁语义分叉。

## 非目标

- 不禁用 GitHub `@codex review` 或其他 hosted review 服务。
- 不改变 human final review、merge authorization 或现有 self-review 例外。
- 不验证具体模型、厂商或 reviewer 输出质量。

## Behavior Invariants

1. B-001 每个用于主要 merge review 的 terminal artifact 必须记录
   `review_execution`，取值为闭集 `{local, hosted}`；缺失、空值或越界值必须
   fail closed。
2. B-002 当 `review_source: independent_lane` 用于主要 review 时，只有
   `review_execution: local` 可满足 gate；`hosted` 必须被判为 supplemental-only
   并阻断 merge readiness。
3. B-003 本地主要 review artifact 必须继续绑定 PR、当前 40 位 head SHA、lane、
   producer、开始/完成时间及 terminal verdict；execution provenance 不得替代任何
   既有 exact-head 证据。
4. B-004 当前 head 有多个 terminal artifact 时，其 `review_execution` 必须一致；
   local/hosted 冲突不得任取其一或静默降级。
5. B-005 GitHub `@codex review` 等 hosted review 可以被请求、展示和报告，但状态
   文案必须明确为 supplemental cloud/hosted review，不得称为 local/primary review。
6. B-006 `review_source: self_review` 仍须满足现有 lane failure 与专用授权规则，且
   其 `review_execution` 必须为 `local`；本变更不得扩展 self-review 能力。
7. B-007 PR evidence adapter 必须从可信 review manifest 派生
   `review_execution`，调用者不得只靠手工顶层字段把 hosted review 提升为 local。
8. B-008 implx runtime ledger 与 offline `pr_gate` 必须执行同一规则：主要
   independent review 缺少 local execution evidence 时均阻断。
9. B-009 兼容策略为 fail closed：旧 artifact 缺少 `review_execution` 时可被 schema
   读取用于诊断，但不能满足新的主要 review gate；不得默认推断为 local。
10. B-010 hosted review 阻断或缺失 provenance 后重跑 gate 必须得到稳定、可操作的
    原因；补充有效 exact-head local artifact 后才可恢复。

## 验收标准

- [ ] hosted independent artifact 在 review semantic gate、PR gate 和 runtime ledger
      三条路径均不能充当主要 review。
- [ ] exact-head local independent artifact 在其他证据完整时继续通过。
- [ ] 文档明确区分本地 `codex review` 与 GitHub `@codex review`。
- [ ] 全量测试与 SpecRail pack checks 通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001 B-009 |
| 错误与失败路径 | covered: B-002 B-004 B-010 |
| 授权/权限 | covered: B-006 B-008 |
| 并发/竞态 | covered: B-003 B-004（多 artifact/current-head 一致性） |
| 重试/幂等 | covered: B-010 |
| 非法状态转换 | covered: B-002 B-007（supplemental 不得提升为 primary） |
| 兼容/迁移 | covered: B-009 |
| 降级/回退 | covered: B-005 B-006（hosted 只补充，self-review 不放宽） |
| 证据与审计完整性 | covered: B-001 B-003 B-004 B-007 B-008 |
| 取消/中断 | N/A：所有 gate 均为只读离线评估，重跑不改变远端状态。 |

## 发布说明

这是 fail-closed workflow contract 变更。采用旧 review artifact 的消费者需要在主要
review artifact 中补充 `review_execution: local`；hosted review 可继续使用，但不再
计算为主要 review。
