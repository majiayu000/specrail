# Tech Spec

## Linked Issue

GH-168

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":168,"complete":true,"paths":["checks/pr_gate.py","checks/sensitive_enforcement.py","tests/test_pr_gate.py","tests/test_sensitive_enforcement.py","skills/specrail-pr-gate/SKILL.md"],"spec_refs":["specs/GH168/product.md","specs/GH168/tech.md","specs/GH168/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| approved_spec 逐字节比对（死锁点） | `checks/sensitive_enforcement.py:411-429` | `validate_approved_spec_evidence` 对每个规格路径要求 `source_digest == merge_digest == current_base_digest == gated_digest == digest`；其中 `current_base_digest`（:411-417）为默认分支内容 hash、`gated_digest`（:419-422）为 PR head 内容 hash，任一不等在 :427 抛 `approved spec content changed since approval or hash mismatched` | spec-revision PR 的 head 规格内容按定义 ≠ 默认分支旧规格，此处必然失败——死锁根因 |
| gated_head_sha 注入点 | `checks/sensitive_enforcement.py:632-644` | `evaluate_sensitive_evidence` 在 `requires_approval` 时调用 `validate_approved_spec_evidence`，`:638-643` 传入 `gated_head_sha=evidence.get("head_sha")`（PR head） | 是「head 规格必须等于默认分支规格」约束的施加点；spec-revision route 需在此之前分流 |
| 可信路径快照 | `checks/sensitive_enforcement.py:519-573` | `sensitive_classification` 经 `classify_sensitive_changes` 复算，`matched_paths`/`matched_specs` 以可信 registry 计算为准，并用 `changed_files_count`/`changed_files_sha256`（:553-568）校验完整快照 | B-001/B-004/B-006：spec-revision 资格判定的唯一可信改动集来源 |
| requires_approval 分支 | `checks/sensitive_enforcement.py:577-649` | `computed_sensitive`/`declaration` 决定 `requires_approval`，随后强制 approved_spec 校验；:648 对 approved_spec 无 enforcement_sensitive 报错 | spec-revision route 的插入位置：在 `requires_approval` 为真时先判 spec-revision 资格再决定走哪条 route |
| pr_gate 敏感面消费点 | `checks/pr_gate.py:381-448` | `has_sensitive_evidence` 触发 `evaluate_sensitive_evidence_with_items`（:396-430），结果对象 :464-484 输出 `enforcement_sensitive`/`sensitive_classification`/`reasons`/`satisfied` | route 判定结论与审计记录（B-010）的输出承载点 |
| 生命周期状态与 human gate | `states.yaml:36-51`、`workflow.yaml:91-102` | 已有 `spec_pr_open → spec_review → spec_approved` 与 `write_spec` 的 `readiness_label`/`spec_approval` human gate | B-002：spec-revision route 复用既有生命周期，不新增状态机 |
| 标签证据采集范式 | `checks/github_approved_spec_evidence.py:95-222` | 从 GitHub label + timeline 采集 maintainer actor/时间戳，作为可信 state 来源（`state_source=label`/`state_trusted`） | B-002/B-005：spec_approval 证据采集复用同一 maintainer 信任范式 |

## Proposed Design

- `checks/sensitive_enforcement.py` 新增 `spec_revision_route_eligible(config, repo, classification) -> bool`（纯函数，形态参照既有 `classify_sensitive_changes`）：
  - 输入为已复算的可信 classification（`checks/sensitive_enforcement.py:519-573` 产出）。
  - 资格条件（B-001/B-004，全部 AND，fail-closed）：`matched_paths` 为空（零 enforcement-sensitive 代码路径）；`changed_paths` 完整集**每一项**都匹配某个 `enforcement.sensitive_registry.specs` glob 且形如 `specs/GH<linked_issue>/{product,tech,tasks}.md`；`matched_specs` 非空。任一不满足返回 False（回落 approved_spec route）。
  - 该函数只读 classification，不读 PR 自报字段（B-006）。
- `checks/sensitive_enforcement.py` 新增 `validate_spec_revision_evidence(evidence, *, repository, issue)`（形态参照 `validate_approved_spec_evidence`，但**不做** default-base 逐字节比对）：
  - 要求 `spec_approval` 对象：`maintainer_actor`（非空字符串）、`approved_at`（timezone-aware ISO-8601，复用 `_timestamp`/`_aware_timestamp`）、`state_source == "label"`、`state_trusted is True`、`lifecycle_state ∈ {spec_review, spec_approved}`（B-002/B-005）。
  - 字段缺失/类型错/时间戳非 aware/来源不可审计 → 抛 `SpecRailError`（fail-closed，B-005）。
  - 明确不接受 approved_spec 字段与 spec_approval 混用（互斥，B-003）。
- `checks/sensitive_enforcement.py` `evaluate_sensitive_evidence`（`:577-649`）分流（B-003）：在 `requires_approval` 为真、且 `spec_revision_route_eligible(...)` 为真时，调用 `validate_spec_revision_evidence` 而非 `validate_approved_spec_evidence`；satisfied 追加 `spec-revision route: lifecycle spec_approval revalidated`。资格为假时保持现状调用 `validate_approved_spec_evidence`（含 `gated_head_sha=head_sha`），逐字节行为不变。两条 route 互斥穷尽。
- `checks/pr_gate.py`（`:381-484`）：透传 route 判定结论；结果对象新增 `sensitive_route ∈ {approved_spec, spec_revision}` 与 spec-revision route 的审计记录（依据 artifact 路径集、maintainer actor/时间戳/来源），满足 B-010；未触发敏感面时字段缺省，输出与现状一致（B-007）。
- 合并授权与其余 gate 不变（B-008）：spec-revision route 只替换 approved_spec 逐字节比对一环，CI/review/threads/reviewer-lane/merge_state/GH-143 授权链原样保留。
- `skills/specrail-pr-gate/SKILL.md`：补充 spec-revision route 的证据要求与互斥/反滥用说明，避免文档与 gate 语义漂移。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | `spec_revision_route_eligible` 正向资格 | `test_spec_revision_route_detected_for_spec_only_pr` |
| B-002 | `validate_spec_revision_evidence` 生命周期 + spec_approval | `test_spec_revision_requires_lifecycle_and_spec_approval` |
| B-003 | `evaluate_sensitive_evidence` 互斥分流 | `test_spec_revision_and_approved_spec_mutually_exclusive` |
| B-004 | 夹带非 spec-artifact / 代码路径回落 | `test_mixed_diff_falls_back_to_approved_spec`（含 gate 代码、测试、非本 issue markdown 三个 fixture 均走 approved_spec 且逐字节行为不变） |
| B-005 | spec_approval fail-closed | `test_spec_revision_missing_or_agent_approval_blocked` |
| B-006 | 依赖可信路径快照 | `test_spec_revision_ignores_self_reported_paths`（快照与声明不一致 → blocked） |
| B-007 | registry 未配置零回归 | 既有 `tests/test_pr_gate.py` / `tests/test_sensitive_enforcement.py` 零改动全绿 |
| B-008 | 其余 gate 不放宽 | `test_spec_revision_still_enforces_ci_review_merge_state`（逐类抹掉 CI/threads/reviewer/merge_state 均 blocked） |
| B-009 | 只读幂等 | `test_spec_revision_evaluation_idempotent` |
| B-010 | 审计记录强制 | `test_spec_revision_route_records_audit_or_blocked`（审计字段缺失 → blocked） |

## Data Flow

PR evidence JSON（新增可选 `spec_approval: {maintainer_actor, approved_at, state_source, state_trusted, lifecycle_state}`）+ 既有可信 `sensitive_classification` 快照 → `pr_gate.py` → `evaluate_sensitive_evidence`：按可信 classification 判 spec-revision 资格 → 走 `validate_spec_revision_evidence`（生命周期 + maintainer 批准，无逐字节比对）或回落 `validate_approved_spec_evidence`（逐字节比对，现状）→ decision + reasons/satisfied + `sensitive_route` 审计记录。未声明 `spec_approval` 且非 spec-revision 资格的输入走既有路径，输出逐字节不变。无持久化、无网络调用。

## Alternatives Considered

- 方案 A（现状，issue 内被否）：对所有 enforcement-sensitive PR 一律 approved_spec 逐字节比对。被否：对 spec-revision PR 形成确定性死锁，唯一出口是人工绕过（破坏 fail-closed 审计）或冻结治理规格。
- 放宽 approved_spec 允许 head ≠ base（对 spec-revision 跳过逐字节比对但仍走同一函数）：被否。会侵蚀实现 PR 的逐字节保证，且难以静态区分「该跳过」与「被滥用跳过」；显式分流 route + 白名单资格更可审计。
- 用 label（如 `spec_revision`）自声明 route：被否。自声明可被实现 PR 伪造；route 资格必须由可信路径快照机械推导（B-001/B-004/B-006），标签仅作生命周期状态的 maintainer 信任来源，不作 route 选择依据。
- 允许 PR 混合 spec 与实现改动并走 spec-revision route：被否。混合改动使 approved_spec 逐字节保证可被夹带绕过；B-004 要求改动集纯 spec-artifact 才有资格。

## Risks

- Security: 新增的是一条**更严格来源**的人工批准通道，非放宽面。spec-revision route 资格由可信 registry 快照机械推导，maintainer 批准为唯一放行依据，全程 fail-closed；实现 PR 无法通过夹带 spec 文件选择该 route（B-004）。本 spec/实现 PR 自身仍按人工授权合并。
- 反滥用边界: 唯一风险是「纯 spec-artifact PR 修改规格以削弱未来 gate」——这是任何规格演进固有的，由既有 maintainer `spec_approval` human gate + reviewer lane 把关，与本 spec 无关；本 spec 不新增该面风险。
- Compatibility: `spec_approval` 字段可选、`sensitive_route` 为新增输出；未声明且非 spec-revision 资格的输入两个函数输出逐字节不变（B-007/B-008 回归护住）。
- Performance: 纯本地字段与路径集校验，可忽略。
- Maintenance: route 资格白名单（spec packet markdown artifacts）与 `enforcement.sensitive_registry.specs` 单一来源对齐；registry 漂移会使资格判定收紧（fail-closed）而非静默放行。
- File size (U-16): `checks/sensitive_enforcement.py` 现约 682 行，新增两函数后须 `wc -l` 复核；逼近 800 行硬上限时把 spec-revision route 逻辑拆入独立模块。

## Test Plan

- [ ] Unit tests: `tests/test_sensitive_enforcement.py` 新增 spec-revision route 资格与证据用例（B-001..B-006、B-009、B-010）；`tests/test_pr_gate.py` 新增 route 分流与回落用例（B-003 B-004 B-008）。
- [ ] Integration tests: 既有 `tests/test_pr_gate.py`、sensitive_enforcement 全套用例零改动全绿（B-007 B-008）。
- [ ] Manual verification: 构造 spec-only enforcement-sensitive PR fixture（带 maintainer spec_approval）跑 `pr_gate` CLI 确认 allowed/needs_human 且 `sensitive_route=spec_revision`；构造夹带 gate 代码的 fixture 确认回落 approved_spec 并 blocked（无 head==base 证据）。

## Rollback Plan

回滚删除 `spec_revision_route_eligible`、`validate_spec_revision_evidence` 与 `evaluate_sensitive_evidence` 的分流分支及 `pr_gate.py` 的 `sensitive_route` 输出即可；`spec_approval` 字段与 `sensitive_route` 输出全部可选、未写入任何持久状态，未声明 spec-revision 证据的 checkpoint/evidence 在回滚前后逐字节一致，无数据迁移。回滚后死锁复现，属预期（回到现状）。
