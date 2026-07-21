# Product Spec

## Linked Issue

GH-167

## 用户问题

单个 PR 的独立审查轮数没有跨模式的总上限，且每轮 carry-forward 仍以全量 finding/artifact 回放为准。现有护栏（GH-61 已落地，`status: legacy`）只覆盖一个侧面：`review_mode` = full/resumed/diff_only，且仅对 **full 模式**在 `review_round > 2` 时要求引用 `human_full_review_request`（`checks/review_json_gate.py:30`、`checks/review_json_gate.py:263`）。但 `resumed`/`diff_only` 轮次除 `review_round >= 2` 之外没有任何轮数上限（`checks/review_json_gate.py:276`），且 `human_full_review_request` 是每轮自我复位的逃生阀而非一次性升级——只要逐轮引用即可无限继续，reviewer 因此可以逐轮追加新治理要求而没有任何机制在第 N 轮强制"该停了吗"。2026-07-21 remem#907（spec-only PR，仅 3 个 markdown 文件）实测跑了 9 轮独立审查、累计 24 个 finding、每轮 5→8 分钟递增、reviewer 逐轮追加新要求不收敛，token 呈二次曲线。本 spec 编码 issue #167 决策：跨模式轮数封顶 + 第 2 轮起 diff-scoped 强制 + 紧凑 carry-forward 状态表，且保留"finding 不许口头消失"不变式。

## 目标

- 引入**跨模式的独立审查轮数总上限**（默认 3，跨 full/resumed/diff_only 统计），超限后强制升级人工裁决，替代逐轮自我复位的逃生阀。
- 把 diff-scoped 复审从"可选模式"提升为"第 2 轮起的强制规则"：`review_round >= 2` 只核验上轮 finding 的关闭证据 + 自上轮 review head 以来的新增 diff，禁止全量历史重新逐条复验。
- 把 carry-forward 收敛成**紧凑状态表**：`prior_findings[]` 每条仅 `{finding_id, status, evidence_pointer}`，禁止全量 finding 正文/artifact 回放；强化为唯一被接受的 carry 形态。
- 把上述语义接入既有强制点：`checks/review_json_gate.py` 的 round 校验、`checks/pr_review_contract.py` 的终审 manifest 字段、`schemas/review_result.schema.json`、`review/agent_first_review.md`、`skills/specrail-review-pr/SKILL.md` 与 `skills/implx/SKILL.md` 的轮数策略。

## 非目标

- 不移除或弱化 GH-61 已落地的 `review_mode` 体系与 full 模式 `FULL_REVIEW_ROUND_CAP = 2` 校验（`checks/review_json_gate.py:263`）；本 spec 的总上限是叠加在其上的更宽约束。
- 不改变 `auth_mode: auto`/`review` 的合并授权语义、reviewer-lane 线程解决归属（`skills/specrail-review-pr/SKILL.md:56`）或任何其它 gate。
- 不解决 GH-61 管辖的 lane 复用 / 全量历史注入问题（本 spec 管轮数上限、每轮范围、carry-forward 形态；两者互补）。
- 不触碰 force-push、发布、跨仓库等既有硬边界。
- 不引入 per-repo 可调上限体系：默认上限固定，歧义一律 fail-closed。

## Behavior Invariants

1. B-001 WHEN 同一 PR 的 `review_round` 超过跨模式总上限（默认 3，统计 full/resumed/diff_only 全部模式）AND 该审查 artifact 未携带人工裁决升级记录时，`checks/review_json_gate.py` 应判违规（block）。该总上限独立于 `review_mode`，与既有仅约束 full 模式的 `FULL_REVIEW_ROUND_CAP` 不同。
2. B-002 WHEN 达到总上限触发升级时，升级记录必须随附**全部未闭合 finding**（每条以紧凑状态表条目呈现）；任一上轮未闭合 finding 未出现在升级记录中即违规（保留"finding 不许口头消失"）。
3. B-003 升级记录必须是**一次性人工裁决**（授权 maintainer 写入），不得由每轮自我复位的 `human_full_review_request` 逃生阀充当；同一 PR 反复引用 `human_full_review_request` 不构成对总上限的豁免。
4. B-004 WHEN 同一 PR 的 `review_round >= 2` 时，`review_mode` 必须为 `diff_only` 或 `resumed`（scoped）；`review_round >= 2` 仍以 `full` 模式对整个 PR 重新逐条复验且无人工裁决升级即违规（把既有 full-round-2 规则收敛为"第 2 轮起 scoped 为默认"并纳入总上限之下）。
5. B-005 WHEN `review_mode` 为 `diff_only` 或 `resumed`（`review_round >= 2`）时，本轮核验范围只包含 (a) 上轮 finding 的关闭证据与 (b) 自 `base_head_sha` 以来的新增 diff；对已在 carry-forward 表中记录的 finding 从零全量重新复验属越界。
6. B-006 carry-forward 必须是紧凑状态表：`prior_findings[]` 每条为 `{finding_id, status ∈ {resolved|unresolved|obsolete}, evidence_pointer}`；回放上轮 review 正文、逐条粘贴全量 finding 文本或嵌入历史 artifact 全文属违规。
7. B-007 上轮每一条未闭合（`unresolved`）finding 必须在本轮 carry-forward 状态表中以显式 status 出现；上轮 `unresolved` finding 在本轮状态表中静默缺失即违规（"finding 不许口头消失"的逐轮强制）。
8. B-008 `evidence_pointer` 必须是具体引用（review thread id / comment id / artifact id / commit SHA），不得是自由散文；`status: resolved` 的 finding 缺失或空 `evidence_pointer` 即 block（审计完整性）。
9. B-009 分级 fail-closed：如果 `review_round` 缺失/不可解析而同一 PR 已存在多份审查 artifact，或 `review_round >= 2` 时 `review_mode` 缺失，应按"超上限/full"处理并 block；总上限取值缺省固定为 3，取值歧义不得默认取更宽松上限。
10. B-010 兼容：`review_round == 1`（任意模式）与未携带新字段的既有单轮流程行为不变（round 1 artifact 零改动通过）；既有 full 模式 `FULL_REVIEW_ROUND_CAP = 2` 的判定被本总上限包含而非弱化。
11. B-011 隔离：本 spec 的总上限与 diff-scoped 规则只作用于独立审查轮次判定，不改变 `auth_mode` auto/review 合并授权、reviewer-lane 线程解决归属、pr_gate/runtime ledger 的任何既有判定。
12. B-012 审计：WHEN PR 在经历封顶/升级的审查后合并时，`checks/pr_review_contract.py` 消费的 review manifest 必须留存：轮数计数、逐轮 `review_mode`、升级记录（若发生）及其随附的未闭合 finding；缺失时终审合同判据不完整应 block，不得事后补记。

## Acceptance Criteria

- [ ] 同一 PR 超过默认总上限（3）且无人工裁决升级记录的独立审查被 `checks/review_json_gate.py` 拒绝，带升级记录且随附全部未闭合 finding 的通过，有测试覆盖（B-001/B-002/B-003）
- [ ] `review_round >= 2` 强制 `diff_only`/`resumed` 且核验范围收敛为"上轮 finding 关闭证据 + 新增 diff"，round>=2 全量复验被拒，有测试覆盖（B-004/B-005）
- [ ] carry-forward 必须为紧凑状态表（`{finding_id, status, evidence_pointer}`），全量正文/artifact 回放被拒，上轮未闭合 finding 静默缺失被拒，有测试覆盖（B-006/B-007/B-008）
- [ ] `review/agent_first_review.md`、`skills/specrail-review-pr/SKILL.md`、`skills/implx/SKILL.md` 写入轮数上限/升级/diff-scoped/紧凑 carry-forward 契约；`python3 checks/check_workflow.py --repo .` 与既有 `tests/` 零改动全绿（B-010/B-011）

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-009（`review_round`/`review_mode` 缺失时 fail-closed 按超上限/full 处理并 block） |
| Error / failure paths | covered: B-001 B-004（超上限无升级、round>=2 全量复验无升级均 block 并指明违规项） |
| Authorization / permission | covered: B-003（升级必须为授权 maintainer 一次性人工裁决，逃生阀不得复用为豁免） |
| Concurrency / race | N/A: 轮数判定为对既有串行 review artifact 的本地只读评估，沿用现有"每 PR 顺序审查"规则，无新增共享可变状态 |
| Retry / idempotency | covered: B-001 B-006（gate 对同一 artifact 集合重复评估结论一致；紧凑状态表使 carry-forward 幂等，无跨进程状态） |
| Illegal state transitions | covered: B-004 B-003（round>=2 携带 full 且无升级、以逃生阀替代人工裁决升级均为非法状态被拦） |
| Compatibility / migration | covered: B-010 B-011（round 1 与无新字段流程零回归；既有 full-round-2 校验被包含不弱化；无迁移，新字段可选） |
| Degradation / fallback | covered: B-002 B-007 B-009（一切歧义显式降级到 block/超上限侧；未闭合 finding 一律随附，不存在静默丢弃） |
| Evidence / audit integrity | covered: B-008 B-012（`evidence_pointer` 须具体引用；合并后 manifest 须留存轮数/模式/升级与未闭合 finding，缺失即 block） |
| Cancellation / interruption | covered: B-002（封顶升级即中止自动审查循环并把全部未闭合 finding 移交人工裁决，恢复以人工决策为准） |

## Rollout Notes

新字段（升级记录、紧凑 `prior_findings[]` 状态表约束）全部可选：未声明时 round 1 与既有单轮 artifact 行为逐字节不变，可安全分步合入。实现顺序：先 `schemas/review_result.schema.json` 与 `checks/review_json_gate.py` 带测试落地总上限 + diff-scoped + 紧凑 carry-forward 校验，再扩展 `checks/pr_review_contract.py` 的 manifest 审计字段，最后同步三处文档（`review/agent_first_review.md`、`skills/specrail-review-pr/SKILL.md`、`skills/implx/SKILL.md`）。本 spec PR 与实现 PR 均按既有 review 模式逐 PR 人工授权合并。
