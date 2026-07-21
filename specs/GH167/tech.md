# Tech Spec

## Linked Issue

GH-167

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":167,"complete":true,"paths":["checks/review_json_gate.py","checks/pr_review_contract.py","schemas/review_result.schema.json","review/agent_first_review.md","skills/specrail-review-pr/SKILL.md","skills/implx/SKILL.md","tests/test_review_json_gate.py","tests/test_runtime_ledger_review.py"],"spec_refs":["specs/GH167/product.md","specs/GH167/tech.md","specs/GH167/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| review round 校验 | `checks/review_json_gate.py:241` | `_validate_review_round()` 校验 `review_round`/`review_mode` 成对出现、mode ∈ `REVIEW_MODES`（`checks/review_json_gate.py:28`）；只对 `review_mode == "full"` 且 `review_round > FULL_REVIEW_ROUND_CAP`（=2，`checks/review_json_gate.py:30`）要求 `human_full_review_request`（`checks/review_json_gate.py:263`）；`resumed`/`diff_only` 仅校验 `review_round >= 2` 与 `diff_only` 的 `base_head_sha`（`checks/review_json_gate.py:276`），无任何轮数上限 | B-001/B-004 的核心改造点：新增跨模式总上限，并把 round>=2 的 full 复验纳入总上限之下 |
| review 逃生阀 | `checks/review_json_gate.py:263` | full-round>2 由 `human_full_review_request` 单轮解锁，逐轮自我复位，无一次性升级概念 | B-003：总上限升级须为一次性人工裁决，逃生阀不得复用为总上限豁免 |
| carry-forward checklist | `skills/specrail-review-pr/SKILL.md:51` | `resumed`/`diff_only` 要求 `prior_findings[]`，每条带 status（resolved/unresolved/obsolete），但未约束其体积/形态，未禁止全量正文回放 | B-006/B-007：强化为紧凑状态表且为唯一被接受的 carry 形态 |
| review 结果 schema | `schemas/review_result.schema.json:112` | 定义 `review_round`（int，min 1）、`review_mode`（enum full/resumed/diff_only）；`prior_findings`、升级记录字段未约束 | B-006/B-008/B-002：新增紧凑 `prior_findings[]` 条目形状与升级记录字段 |
| 终审合同 manifest | `checks/pr_review_contract.py:272` | `_manifest_trust_items()` 从 `review_evidence.manifest_path` 复核 `lane_roster`、`current_artifact_ids`、`artifacts` 等字段（`checks/pr_review_contract.py:305`）；无轮数/升级审计字段 | B-012：合并后 manifest 须留存轮数计数、逐轮 mode、升级记录与未闭合 finding |
| review 合同文档 | `review/agent_first_review.md:39` | 描述 `review_json_gate.py` 校验入口与 severity/inline 规则，无轮数上限/升级/diff-scoped 契约 | B-001..B-007 的文档强制点之一 |
| review-pr skill 轮数策略 | `skills/specrail-review-pr/SKILL.md:39` | "Review Rounds And Modes" 段描述 full/resumed/diff_only 与 full-round>2 门槛 | B-001/B-004/B-006 文档强制点：写入总上限、升级、diff-scoped 强制、紧凑 carry-forward |
| implx reviewer-lane 编排 | `skills/implx/SKILL.md:173` | threads/reviewer-lane 编排段描述 reviewer/merge-reviewer lane、CI waits、closure audit，无轮数上限/升级触达 | B-001/B-003 文档强制点：队列编排须知晓总上限触发人工裁决升级 |

## Proposed Design

- `checks/review_json_gate.py`：在 `_validate_review_round()`（`checks/review_json_gate.py:241`）之上新增/扩展：
  - 常量新增 `INDEPENDENT_REVIEW_ROUND_CAP = 3`（跨模式总上限），与既有 `FULL_REVIEW_ROUND_CAP = 2` 并存（后者仍拦 full 模式的 round>2，B-010）。
  - B-001/B-003：`review_round > INDEPENDENT_REVIEW_ROUND_CAP` 时要求 artifact 携带 `round_cap_escalation` 对象（`{escalated_by, escalation_source, unresolved_findings[]}`，`escalation_source` 须标注人工裁决来源，且不接受 `human_full_review_request` 作为其来源值）；缺失即 block。
  - B-002/B-007：`round_cap_escalation.unresolved_findings[]` 与 `prior_findings[]` 中 status=`unresolved` 的集合逐条比对；任一未闭合 finding 未随附即 block。
  - B-004：`review_round >= 2` 时 `review_mode` 必须 ∈ {`resumed`, `diff_only`}；`full` 且无 `round_cap_escalation` 即 block（把既有 full-round>2 规则收敛为"第 2 轮起 scoped 默认"）。
  - B-006/B-008：`prior_findings[]` 每条形状收敛为 `{finding_id, status, evidence_pointer}`；出现被禁字段（如 `body`/`full_text`/嵌入 artifact 正文）即 block；`status: resolved` 缺 `evidence_pointer` 即 block。
  - B-009：`review_round` 缺失但 PR 存在多份 artifact，或 round>=2 缺 `review_mode` → 按超上限/full 处理并 block。
- `schemas/review_result.schema.json`（`schemas/review_result.schema.json:112`）：`prior_findings[]` items 定为 `{finding_id: str, status: enum, evidence_pointer: str}` 且 `additionalProperties: false`；新增可选 `round_cap_escalation` 对象 schema；`review_round`/`review_mode` 约束不变（B-010）。
- `checks/pr_review_contract.py`（`checks/pr_review_contract.py:305` 的 manifest 字段列表）：B-012 追加对 `review_round`（或轮数计数）、逐轮 `review_mode`、`round_cap_escalation` 的可信 manifest 复核；未声明新字段的既有 manifest 复核逐字节不变（B-011）。
- `review/agent_first_review.md`（`review/agent_first_review.md:39`）：Output 段补充总上限、升级、diff-scoped 强制、紧凑 carry-forward 状态表契约与字段说明。
- `skills/specrail-review-pr/SKILL.md`（"Review Rounds And Modes"，`skills/specrail-review-pr/SKILL.md:39`）：改写为总上限（默认 3，跨模式）、超限一次性人工裁决升级、round>=2 强制 scoped、紧凑 `prior_findings[]` 状态表为唯一 carry 形态、`round_cap_escalation` 随附全部未闭合 finding。
- `skills/implx/SKILL.md`（reviewer-lane 编排段，`skills/implx/SKILL.md:173`）：补一句——独立审查触达总上限时切换为人工裁决升级并移交未闭合 finding，不得逐轮以逃生阀继续。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | review_json_gate 总上限校验 | `test_round_over_cap_without_escalation_blocked`（review_round=4、无 escalation → block） |
| B-002 | escalation 随附未闭合 finding | `test_escalation_must_carry_all_unresolved_findings`（漏一条 unresolved → block） |
| B-003 | escalation 须一次性人工裁决 | `test_human_full_review_request_not_valid_escalation_source`（以逃生阀充当 escalation source → block） |
| B-004 | round>=2 强制 scoped | `test_round2_full_without_escalation_blocked` + `test_round2_diff_only_allowed` |
| B-005 | diff-scoped 范围收敛 | `test_diff_only_requires_base_head_sha_and_prior_findings`（缺 base_head_sha 或 prior_findings → block） |
| B-006 | 紧凑状态表形状 | `test_prior_findings_reject_full_body_replay`（含 body/full_text 字段 → block） |
| B-007 | 未闭合 finding 不许消失 | `test_prior_unresolved_finding_missing_blocked` |
| B-008 | evidence_pointer 须具体 | `test_resolved_finding_missing_evidence_pointer_blocked` |
| B-009 | 缺字段 fail-closed | `test_missing_round_or_mode_fails_closed` |
| B-010 | round 1 与既有 full-cap 零回归 | 既有 `tests/test_review_json_gate.py` 零改动全绿 + `test_round1_any_mode_unchanged` |
| B-011 | 隔离零回归 | 既有 `tests/test_runtime_ledger_review.py`、`tests/test_review_json_gate.py` 零改动全绿 |
| B-012 | 合并后 manifest 审计字段 | `test_pr_review_contract_requires_round_audit_fields`（缺轮数/mode/escalation → block） |

## Data Flow

review 结果 JSON（新增可选字段：`round_cap_escalation`；`prior_findings[]` 收敛为 `{finding_id, status, evidence_pointer}`）→ `checks/review_json_gate.py` 只读校验（against diff）→ satisfied/reasons。终审阶段 review manifest（新增轮数计数、逐轮 `review_mode`、`round_cap_escalation`）→ `checks/pr_review_contract.py` 可信复核 → satisfied/missing/reasons。未声明新字段的 round 1 / 既有 artifact 走既有路径，输出零变化。无持久化、无网络调用。

## Alternatives Considered

- 沿用现有 `human_full_review_request` 逐轮解锁、不设总上限：被否。逃生阀每轮自我复位，reviewer 逐轮追加要求不收敛，正是 remem#907 九轮的直接成因。
- 只封 full 模式轮数（提高 `FULL_REVIEW_ROUND_CAP`）：被否。resumed/diff_only 轮次同样无上限，且 remem#907 的成本二次增长来自 carry-forward 全量回放而非单一模式。
- carry-forward 不约束形态、只靠约定：被否。约定不可机检，全量 finding 正文回放是 token 二次曲线的根因，须以 schema `additionalProperties: false` + gate 机检强制紧凑状态表。
- 把轮数上限做成 per-repo 可配置：被否（本 spec 非目标）。默认固定、歧义 fail-closed 更简单可审计；未来如需配置另开 spec。

## Risks

- Security: 升级路径要求授权 maintainer 一次性人工裁决（B-003），拒绝以逃生阀绕过；未闭合 finding 强制随附（B-002）避免封顶时静默丢弃质量信号。本 spec 与实现 PR 自身按既有 review 模式逐 PR 人工授权合并。
- Compatibility: 新字段全部可选，round 1 与未声明新字段的既有 artifact 输出逐字节不变（B-010/B-011 回归护住）；既有 full-round>2 校验被总上限包含而非移除。
- Correctness: 总上限与 diff-scoped 强制可能拦下"合理的第 4 轮全量复审"——此时须走一次性人工裁决升级（B-001），把决定权交人而非自动继续，符合"finding 不许口头消失"的设计意图。
- Performance: 纯本地字段校验，可忽略。
- Maintenance: 上限常量（`INDEPENDENT_REVIEW_ROUND_CAP`）与 SKILL.md 文档单一来源对齐；`prior_findings[]` 闭集 schema 使形态漂移暴露为校验错误而非静默放行。
- File size (U-16): `checks/review_json_gate.py` 现约 300 行，新增校验后须 `wc -l` 复核；若逼近 800 行硬上限，把 round 校验拆入独立辅助模块（参照 `checks/runtime_gate_rules.py` 的拆分模式）。

## Test Plan

- [ ] Unit tests: `tests/test_review_json_gate.py` 新增总上限/升级/diff-scoped/紧凑 carry-forward 用例（B-001..B-009）。
- [ ] Integration tests: 既有 `tests/test_review_json_gate.py`、`tests/test_runtime_ledger_review.py` 全套零改动全绿（B-010/B-011）；`checks/pr_review_contract.py` manifest 审计用例（B-012）。
- [ ] Manual verification: 构造 round=4 无升级 fixture 与 round=2 diff_only + 紧凑状态表 fixture，各跑一次 `checks/review_json_gate.py` CLI 确认 decision 与错误信息可定位。

## Rollback Plan

回滚删除 `checks/review_json_gate.py` 的总上限/升级/紧凑 carry-forward 校验分支、`checks/pr_review_contract.py` 的轮数审计字段、schema 的 `round_cap_escalation` 与 `prior_findings[]` 闭集约束，以及三处文档段落即可；新字段全部可选、未写入任何持久状态，未声明的 round 1 / 既有 artifact 在回滚前后行为一致，无数据迁移。
