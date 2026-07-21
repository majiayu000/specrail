# Task Plan

## Linked Issue

GH-167

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP167-T1` `schemas/review_result.schema.json` 扩展：`prior_findings[]` items 收敛为 `{finding_id, status(enum resolved/unresolved/obsolete), evidence_pointer}` 且 `additionalProperties: false`；新增可选 `round_cap_escalation`（`{escalated_by, escalation_source, unresolved_findings[]}`）；`review_round`/`review_mode` 约束不变；既有 review artifact 样例零改动通过。Covers: B-006 B-008 B-002. Owner: agent. Done when: schema 校验通过且既有样例零改动. Verify: `python3 checks/check_workflow.py --repo .`
- [ ] `SP167-T2` `checks/review_json_gate.py` 新增 `INDEPENDENT_REVIEW_ROUND_CAP = 3` 并扩展 `_validate_review_round()`：round>cap 无 `round_cap_escalation` → block；escalation 须一次性人工裁决来源（拒绝 `human_full_review_request` 充当）；`unresolved_findings[]` 与 `prior_findings[]` 中 unresolved 集合逐条比对，漏一条即 block；round>=2 强制 `review_mode` ∈ {resumed, diff_only}，full 无 escalation 即 block；`prior_findings[]` 出现被禁全量正文字段或 resolved 缺 `evidence_pointer` 即 block。配套单元用例覆盖全部拒绝分支。Covers: B-001 B-002 B-003 B-004 B-006 B-007 B-008. Owner: agent. Done when: 全部拒绝分支有用例且全绿. Verify: `python3 -m pytest -q tests/test_review_json_gate.py`
- [ ] `SP167-T3` `checks/review_json_gate.py` diff-scoped 范围与 fail-closed：`diff_only`（round>=2）须有 `base_head_sha` 与 `prior_findings[]`；`review_round` 缺失但 PR 多 artifact、或 round>=2 缺 `review_mode` → 按超上限/full 处理并 block；round 1 与未声明新字段 artifact 零回归。Covers: B-005 B-009 B-010. Owner: agent. Done when: fail-closed 用例全绿且既有用例零改动全绿. Verify: `python3 -m pytest -q tests/test_review_json_gate.py`
- [ ] `SP167-T4` `checks/pr_review_contract.py` 终审 manifest 审计字段：`_manifest_trust_items()` 复核列表追加轮数计数、逐轮 `review_mode`、`round_cap_escalation`；缺失即 block；未声明新字段的既有 manifest 复核零变化。Covers: B-011 B-012. Owner: agent. Done when: 审计用例全绿且既有 pr_review_contract/runtime_ledger_review 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_runtime_ledger_review.py`
- [ ] `SP167-T5` 文档同步：`review/agent_first_review.md`（Output 段补总上限/升级/diff-scoped/紧凑 carry-forward 契约）、`skills/specrail-review-pr/SKILL.md`（"Review Rounds And Modes" 改写为跨模式总上限 + 一次性人工裁决升级 + round>=2 强制 scoped + 紧凑状态表唯一 carry 形态）、`skills/implx/SKILL.md`（reviewer-lane 编排段补总上限触发人工裁决升级并移交未闭合 finding）。Covers: B-001 B-003 B-004 B-006. Owner: agent. Done when: 三处文档含总上限与紧凑 carry-forward 约定且 workflow 校验通过. Verify: `grep -lE "round_cap_escalation|总上限|INDEPENDENT_REVIEW_ROUND_CAP" review/agent_first_review.md skills/specrail-review-pr/SKILL.md skills/implx/SKILL.md | wc -l | grep -qx 3 && python3 checks/check_workflow.py --repo .`
- [ ] `SP167-T6` 端到端回归演练：构造 round=4 无升级 fixture（block）、带 escalation + 全部未闭合 finding fixture（allowed）、round=2 diff_only + 紧凑状态表 fixture（allowed）、全量正文回放 fixture（block），各跑 `checks/review_json_gate.py` CLI 确认 decision 与错误信息可定位。Covers: B-001 B-002 B-004 B-006 B-007. Owner: agent. Done when: 演练脚本化为测试或记录于 PR 描述附命令输出. Verify: `python3 -m pytest -q tests/test_review_json_gate.py tests/test_runtime_ledger_review.py`

## Parallelization

T1 先行（字段名以 T1 落定为准）；T2、T3 依赖 T1 且同改 `checks/review_json_gate.py`，须串行同一 owner；T4 只改 `checks/pr_review_contract.py`，可与 T2/T3 并行；T5 只改文档，依赖 T1-T4 字段名后执行；T6 依赖 T2/T3/T4。

## Verification

- `python3 -m pytest -q tests/test_review_json_gate.py tests/test_runtime_ledger_review.py`
- `python3 checks/check_workflow.py --repo .`

## Handoff Notes

- 本实现属审查合同语义变更，`pr_tier: heavy`：实现 PR 按既有 review 模式逐 PR 人工授权合并。
- `INDEPENDENT_REVIEW_ROUND_CAP = 3` 与 SKILL.md 文档单一来源对齐；改上限须先改文档再同步常量。
- 与 GH-61 互补：GH-61 管 lane 复用/全量历史注入，本 spec 管轮数上限 + 每轮范围 + carry-forward 形态；勿把两者的字段混用。
- 硬约束：round 1 与未声明新字段的既有 artifact 零回归（B-010/B-011），实现以既有测试零改动为准绳。
