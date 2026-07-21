# Product Spec

## Linked Issue

GH-168

## 用户问题

`pr_gate` 的 approved-spec 强制链（`checks/pr_gate.py:396-430` → `checks/sensitive_enforcement.py:632-644` → `validate_approved_spec_evidence`）要求「批准规格在默认分支上的内容 hash」与「PR head 上的内容 hash」逐字节相等（`checks/sensitive_enforcement.py:423-429`）。修改 enforcement-sensitive 规格的 PR 自己就是规格变更：其 head 上的规格内容按定义不同于默认分支的旧规格内容，`gated_digest != current_base_digest` 必然成立 → fail-closed 拒绝。这是确定性 bootstrap 死锁：要修改批准规格必须先有一份与默认分支逐字节相同的批准规格，而这正是本 PR 要做的事。2026-07-21 两次实测复现（remem#907 04:35 UTC 靠人工判断绕过、破坏审计链；remem#909 09:54 UTC 被 fail-closed 固化拒绝、队列被迫绕行，#909 与依赖它的 #908 收尾悬置）。任何采用该 gate 的仓库每次修订治理规格都会复现。本 spec 只编码「给 spec-revision PR 一条合法生命周期路线」这一决策，不重开 approved_spec 设计辩论。

## 目标

- `pr_gate` 显式识别「PR 本身就是 enforcement-sensitive 规格变更」的生命周期路线（spec-revision route），改走 spec-lifecycle 检查 + 人工批准通道，不再对其套用要求「head 规格 == 默认分支规格」的 `approved_spec` 逐字节比对。
- 新路线仍 **fail-closed**：无合法 spec-approval 证据即 blocked，不引入任何静默豁免、不放宽既有任何 gate。
- 明确 spec-revision route 与 approved_spec route 的**互斥边界**，并加**反滥用约束**，防止实现 PR 伪装成 spec-revision PR 绕过 approved_spec 门禁。

## 非目标

- 不改变 `approved_spec` 校验对**实现 PR**（触及 enforcement-sensitive 代码路径）的任何语义：实现 PR 仍走 `validate_approved_spec_evidence` 全量比对。
- 不改变 `auth_mode: auto` / `review` 的合并授权语义（GH-143 tier 授权、逐 PR 人工授权不动）。
- 不新增状态机：spec-revision route 复用 `states.yaml` 已有的 `spec_pr_open → spec_review → spec_approved` 生命周期与 `spec_approval` human gate。
- 不弱化 CI、reviewer-lane、review-thread、runtime ledger gate、Bounded Tranche 任何既有规则。
- 不触碰 force-push、发布、跨仓库、permission-change 等既有硬边界。

## Behavior Invariants

1. B-001 当一个 PR 的完整改动文件集**全部**落在 spec packet markdown artifacts（`specs/GH<issue>/product.md`、`tech.md`、`tasks.md`，且命中 `enforcement.sensitive_registry.specs`）之内、**且不含任何** enforcement-sensitive 代码路径（`enforcement.sensitive_registry.paths` 零命中、`matched_paths` 为空）时，`pr_gate` 应将其判定为 spec-revision PR，走 spec-revision route，不调用 approved_spec 逐字节比对。
2. B-002 spec-revision route 的证据要求（fail-closed）：linked issue 处于规格生命周期状态（`spec_review` 或 `spec_approved`，以 maintainer 标签为信任来源）、且携带 maintainer 人工 `spec_approval` 证据（actor + timezone-aware 时间戳 + 来源，语义等价于既有 approved_spec 的 `maintainer_actor`/`approved_at` 可审计锚点）；任一缺失即 blocked，不得放行。
3. B-003 spec-revision route 与 approved_spec route **互斥且穷尽**：一个 enforcement-sensitive PR 恰好命中其一。判定顺序为先按 B-001 检测 spec-revision 资格；不满足资格（改动含任一非 spec-artifact 文件或任一 enforcement-sensitive 代码路径）的 enforcement-sensitive PR 一律回落 approved_spec route，行为与现状逐字节相同。
4. B-004 反滥用（fail-closed）：只要 PR 改动集包含任一不在 spec packet markdown artifacts 白名单内的文件（含 gate 代码、测试、schema、非 markdown 文件、或非本 issue packet 下的 markdown），spec-revision route **不成立**，PR 落回 approved_spec route。实现 PR 无法通过夹带 spec 文件来选择 spec-revision route 绕过 approved_spec 比对。
5. B-005 spec-revision route 的 `spec_approval` 证据必须来自 maintainer（等同既有 human gate 的信任来源），agent 自报的批准不作数；证据缺 actor/时间戳/来源、时间戳非 timezone-aware、或来源不可审计时，按 blocked 处理（重确认自身 fail-closed）。
6. B-006 spec-revision route 判定所依据的「改动文件集」必须来自与 approved_spec route 同源的可信路径快照（`sensitive_classification` 的 `changed_paths` + `changed_files_count`/`changed_files_sha256` 一致性校验，见 `checks/sensitive_enforcement.py:553-568`），不得凭 PR 自报的松散字段；快照与声明不一致时 blocked。
7. B-007 当 `enforcement.sensitive_registry` 未配置（paths 与 specs 均空）时，本 spec 不改变任何行为：无敏感面即无 approved_spec 强制，也就无 spec-revision route，`pr_gate` 输出逐字节不变。
8. B-008 spec-revision route 不放宽 approved_spec route 之外的任何 gate：CI rollup、review threads、reviewer-lane verdict、merge_state、GH-143 合并授权（tier / 人工）在两条路线下同等强制；spec-revision route 仅替换「approved_spec 逐字节比对」这一环，其余判定链不变。
9. B-009 spec-revision route 与 approved_spec route 的判定对同一 evidence 只读、幂等、无网络、无持久化；重复评估结论一致。
10. B-010 审计完整性：以 spec-revision route 放行时，`pr_gate` 结果对象应留存可审计记录（判定为 spec-revision route、依据的规格 artifact 路径集、maintainer spec_approval 的 actor/时间戳/来源），使「这次为何免 approved_spec 比对」可 grep 审计；记录缺失即 blocked。

## Acceptance Criteria

- [ ] enforcement-sensitive 且改动集全为本 issue spec artifacts 的 PR，携带 maintainer spec_approval + 生命周期状态证据时经 spec-revision route 放行，不触发 approved_spec 逐字节比对，有测试覆盖（B-001 B-002 B-010）
- [ ] 改动集夹带任一非 spec-artifact 文件或任一 enforcement-sensitive 代码路径的 PR 一律回落 approved_spec route，行为与现状逐字节相同，有测试覆盖（B-003 B-004）
- [ ] spec-revision route 缺 spec_approval / 生命周期状态 / 证据字段非法时 fail-closed blocked，有测试覆盖（B-002 B-005 B-006）
- [ ] `python3 checks/check_workflow.py --repo .` 与既有 `tests/test_pr_gate.py` / sensitive_enforcement 测试零改动全绿（B-007 B-008 兼容回归）

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-002 B-005 B-006（缺 spec_approval / 生命周期状态 / 快照字段一律 fail-closed blocked） |
| Error / failure paths | covered: B-005 B-006（证据字段非法、快照与声明不一致即 blocked，错误信息指明缺失项） |
| Authorization / permission | covered: B-002 B-005（spec_approval 必须 maintainer，agent 自报不作数，信任来源等同既有 human gate） |
| Concurrency / race | N/A: 判定为对既有串行 gate 证据的本地只读评估，沿用 gate query 先于 merge、不并行的既有规则，无新增共享可变状态 |
| Retry / idempotency | covered: B-009（同一 evidence 重复评估结论一致，只读幂等，无跨进程状态） |
| Illegal state transitions | covered: B-003 B-004（enforcement-sensitive PR 恰走其一；不满足 spec-revision 资格却声明该 route 为非法态，回落 approved_spec 或 blocked） |
| Compatibility / migration | covered: B-007 B-008（registry 未配置或非 spec-revision PR 时行为逐字节不变；无迁移，spec-revision 证据字段为新增分支） |
| Degradation / fallback | covered: B-003 B-004 B-005（一切歧义显式降级到 approved_spec route 或 blocked，不存在静默放行） |
| Evidence / audit integrity | covered: B-006 B-010（判定依据可信路径快照；放行留存 route/artifact/maintainer 审计记录，缺失即 blocked） |
| Cancellation / interruption | N/A: 无长事务、无中途状态；单次 gate 评估要么 allowed/needs_human 要么 blocked，无可中断的中间态 |

## Rollout Notes

本 spec PR 自身即 enforcement-sensitive 规格变更，正是本 issue 描述的死锁场景：在实现 PR 落地前，本 spec PR 及后续实现 PR 仍需 maintainer 逐 PR 人工批准合并（记录人工授权），不得引用尚未存在的 spec-revision route 给自己放行。实现顺序：先在 `checks/` 侧落地 spec-revision route 判定 + 证据校验并带测试，未声明新证据字段的输入零行为变化（B-007 护住），再更新相关 SKILL.md 说明该生命周期路线；分步合入安全。
