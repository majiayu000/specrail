# Product Spec

## Linked Issue

GH-168

## 用户问题

`pr_gate` 的 approved-spec 强制链要求默认分支上的批准规格与 PR head 上的规格逐字节相等。规格修订 PR 的 head 内容按定义不同于默认分支旧内容，因此 `gated_digest != current_base_digest` 必然 fail closed；要合并新规格，规格必须先已在默认分支，形成确定性 bootstrap 死锁。2026-07-21 在 remem#907 与 remem#909 两次复现：前者只能人工绕过，后者被 gate 固化阻塞。本 spec 只定义一条可审计、exact-head-bound 的 spec-revision 生命周期路线，不重开 approved_spec 对实现 PR 的设计。

## 目标

- 机械识别「只修改 linked issue 自身 spec packet」的 spec-revision PR，并用独立、fail-closed 的 exact-head human approval 证据替代不可能满足的 default-base byte equality。
- 保持 spec-revision 与 approved_spec route 互斥；任何混合改动、非 linked issue 规格或歧义都回落 approved_spec 或 blocked。
- 让 GitHub evidence collector、PR evidence schema、`pr_gate` 与 runtime ledger 对同一 route/approval/head contract 完全一致。

## 非目标

- 不改变实现 PR 或混合 PR 的 approved_spec 逐字节校验。
- 不把 `spec_review`、进入 review 的标签事件或 agent 自报当成批准。
- 不改变 CI、reviewer lane、review threads、merge state、GH-143 授权与人工 merge gate。
- 不新增生命周期状态；复用 `spec_pr_open → spec_review → spec_approved`，但只有 `spec_approved` 是批准终态。

## Behavior Invariants

1. B-001 当 PR 的可信完整改动集非空、全部属于 linked issue 的 `specs/GH<issue>/{product,tech,tasks}.md` 允许集、全部命中 `enforcement.sensitive_registry.specs`，且 `matched_paths` 为空时，gate 才可判定 `sensitive_route=spec_revision`。
2. B-002 spec-revision route 必须同时验证 linked issue 的可信生命周期状态恰为 `spec_approved`，以及一个与进入 review 不可混淆的 maintainer approval event；`spec_review` 永远不能授权合并。
3. B-003 spec-revision 与 approved_spec route 互斥且穷尽：不满足 B-001 的 enforcement-sensitive PR 一律保持现有 approved_spec route，既有 byte-for-byte 行为不变。
4. B-004 改动包含 gate 代码、测试、schema、非 markdown、其它 issue packet 或任何白名单外文件时，spec-revision 资格失败；夹带 spec 文件不能让实现 PR绕过 approved_spec。
5. B-005 `spec_approval` 必须来自 maintainer 的 GitHub `APPROVED` PR review，包含非空 actor、timezone-aware 时间戳、可审计 URL/source 与 `commit_oid`；label、PR body、agent 字段或不可信来源不能替代该事件。
6. B-006 route 判定只消费与 gate query 同一 head 下重新抓取的可信 file snapshot，并校验 `changed_files_count`/`changed_files_sha256`；不得信任调用方自报路径。
7. B-007 `spec_approval.commit_oid` 必须等于 gated `head_sha`，并携带由该 head 上按规范化路径排序的 spec artifact 内容计算出的 `spec_artifacts_sha256`；head 或 digest 任一不匹配即 blocked，防止批准后 push 复用旧 approval。
8. B-008 GitHub evidence collector 必须自己采集 linked issue 的 `spec_approved` label timeline、maintainer 权限与 exact-head `APPROVED` review，输出完整 `spec_approval`；手写 fixture 可通过但 live collector 缺字段的状态不算完成。
9. B-009 PR evidence schema 必须允许 enforcement-sensitive evidence 恰好携带与 `sensitive_route` 匹配的 `approved_spec` 或 `spec_approval`，拒绝两者同时存在、route/字段错配、partial object 与未知字段。
10. B-010 runtime checkpoint 对 enforcement-sensitive item 必须 route-aware：`approved_spec` route 继续要求 `approved_spec_evidence`；`spec_revision` route 改为要求 exact-head `spec_approval_evidence`，并复用 B-002/B-005/B-007 校验，不能因缺 legacy approved_spec 而误拒绝。
11. B-011 spec-revision route 不放宽其它 gate；CI、local independent review、threads、merge state、授权和 query/head freshness 与 approved_spec route 同等强制。
12. B-012 gate 结果必须记录 `sensitive_route`、linked issue、artifact paths、approval actor/time/source/URL、approved head 与 artifact digest；审计字段缺失或与已验证输入不一致即 blocked。

## Acceptance Criteria

- [ ] 只修改 linked issue spec packet 的 PR，在 issue 为 `spec_approved` 且存在 exact-head maintainer `APPROVED` review 时走 `spec_revision` 并通过敏感证据环节（B-001 B-002 B-005 B-007）。
- [ ] `spec_review`、旧 head approval、digest mismatch、agent/body/label 自报 approval、非 linked issue packet 与 mixed diff 均 fail closed 或回落 approved_spec，并有负例（B-002..B-007）。
- [ ] live `github_pr_evidence.py`、`pr_review_gate.schema.json`、`pr_gate` 与 runtime ledger 对同一 `spec_approval` contract 端到端通过；缺任一 adapter/schema/runtime 段都由测试阻止（B-008 B-009 B-010）。
- [ ] 其它 CI/review/thread/merge/auth gate 与非敏感输入行为保持不变，全量回归通过（B-003 B-011 B-012）。

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 B-002 B-005 B-009 B-010（空 changed set、缺 lifecycle/approval/schema/checkpoint evidence 均 fail closed） |
| Error / failure paths | covered: B-006 B-007 B-008 B-012（snapshot、head、digest、collector、audit mismatch 均给出 blocking reason） |
| Authorization / permission | covered: B-002 B-005（仅 maintainer exact-head APPROVED review；`spec_review`/agent/label/body 不授权） |
| Concurrency / race | covered: B-006 B-007（approval 绑定 commit 与 artifact digest；gate 前后 head/file snapshot 漂移要求重采） |
| Retry / idempotency | covered: B-006 B-012（同一 immutable evidence 只读幂等；head 变化必须重采，不复用旧 approval） |
| Illegal state transitions | covered: B-002 B-003 B-009（`spec_review` 不可充当终态，两 route 不可并存或错配） |
| Compatibility / migration | covered: B-003 B-009 B-010 B-011（approved_spec 与非敏感路径保持现状；新增字段只在显式 route 下强制） |
| Degradation / fallback | covered: B-003 B-004（资格不成立回落 approved_spec；证据歧义 blocked，不静默放行） |
| Evidence / audit integrity | covered: B-005..B-010 B-012（live collector、schema、head/digest、runtime 与结果审计端到端绑定） |
| Cancellation / interruption | N/A：单次只读 gate 无中间持久状态；未完成采集只能 blocked 后重跑 |

## Rollout Notes

本 spec PR 自身发生在 spec-revision route 实现之前，不得引用未来 route 给自己放行；仍需当前 gate 可验证的逐 PR 人工授权。实现必须先打通 collector→schema→gate→runtime 全链，再更新 skill 文档。任何阶段都不得只让手写 fixture 绿而让 live evidence 缺字段。
