# Tech Spec

## Linked Issue

GH-166

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":166,"complete":true,"paths":["checks/github_pr_evidence.py","checks/github_evidence_common.py","checks/pr_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","tests/test_github_pr_evidence.py","tests/test_pr_gate.py","tests/test_runtime_gate_rules.py","tests/test_runtime_ledger_gate.py"],"spec_refs":["specs/GH166/product.md","specs/GH166/tech.md","specs/GH166/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| PR 证据采集 | `checks/github_pr_evidence.py:291` | `head_sha = _require_string(pr_payload, "headRefOid")`；证据 dict 写入 `head_sha`（:301）与 `gate_query_head_sha`（:311），均为整体 head，无内容类别拆分 | B-001 的采集改造点：需在此并行计算 `code_diff_hash`/`spec_files_hash`/`pr_metadata_hash` 并写入证据 |
| PR snapshot 一致性 | `checks/github_pr_evidence.py:325` | `pr_snapshot.get("head_sha") != head_sha` 即抛错「complete PR file snapshot is required」 | B-010/B-011：敏感面 snapshot 复用需以 `spec_files_hash`/`code_diff_hash` 一致为条件，而非仅 head_sha |
| 采集期 head 漂移 | `checks/github_pr_evidence.py:512` | `head_sha_before != head_sha_after` 直接抛错「PR head changed while collecting gate evidence; rerun」，无部分复用 | B-011 的核心改造点：head 漂移时按变化类别重采，未变化类别 hash 保留并对齐最终 head |
| 证据公共辅助 | `checks/github_evidence_common.py` | 承载 `_require_string` 等证据规范化辅助与共享 EvidenceError | 新增 content-hash 计算辅助与「脚本注入来源标记」校验（B-007/B-008）宜集中于此，供采集与 gate 复用 |
| pr_gate head 证据项 | `checks/pr_gate.py:325` | `if _non_empty_string(evidence.get("head_sha")): satisfied.append(...)`（:326），否则 missing（:328-329）；head_sha 作单一整体键 | B-005/B-007：证据项需识别类别 hash 与注入来源标记，纯 metadata 变化不作废 CI/review |
| terminal review head 一致性 | `checks/runtime_gate_rules.py:210` `_validate_terminal_review_summary`，`:221` `if review.get("head_sha") != head_sha:` | terminal review 的 head_sha 必须逐字等于 item head_sha，否则整条 review 失效 | B-009 的核心改造点：`code_diff_hash` 一致时判定 review 仍有效，缺失/变化时回退现状严格校验 |
| ledger gate merge-ready 证据 | `checks/runtime_ledger_gate.py` merge-ready 校验块 | merge-ready item 强制 CI 绿、review 通过、review_threads 干净、pr_gate 复评、merge_state clean，全部隐含绑定同一 head | B-002/B-003/B-012：类别复用判定与审计字段（三类 hash + 原绑定来源）在此叠加，不重复造证据检查 |

## 设计方案

- `checks/github_evidence_common.py` 新增内容 hash 与注入校验辅助：
  - `compute_content_hashes(pr_payload, diff_text, spec_files) -> {code_diff_hash, spec_files_hash, pr_metadata_hash}`：`code_diff_hash` 取规范化 diff（去除时间戳/上下文噪声后的 patch 文本）的 SHA-256；`spec_files_hash` 取 spec packet 下受版本管理 markdown 内容拼接的 SHA-256；`pr_metadata_hash` 取 body/title 归一化后的 SHA-256。
  - `require_injected_sha(evidence, field, label)`：校验机械 SHA 字段携带脚本注入来源标记（约定证据侧字段 `sha_provenance: {field: "git_rev_parse"}` 或等价标记）；缺失来源标记 → EvidenceError（B-007）。注入 SHA 与 live head 不一致 → EvidenceError（B-008）。
- `checks/github_pr_evidence.py`：
  - 在 `head_sha` 采集处（:291-311）调用 `compute_content_hashes`，把三类 hash 写入证据 dict（新增可选键 `content_hashes: {code_diff_hash, spec_files_hash, pr_metadata_hash}`）；同时写入 `sha_provenance` 标记 head_sha/gate_query_head_sha 的注入来源（B-001/B-007）。
  - snapshot 一致性（:325）与 head 漂移（:512）分支改为：先比对相关类别 hash，未变化类别复用既有 snapshot/证据，仅对变化类别重采（B-011）；任一相关类别 hash 缺失 → 回退现状严格重采（fail-closed，B-006）。
- `checks/pr_gate.py`：证据项（:325）扩展——当 evidence 声明 `content_hashes` 且携带 `reuse_binding`（记录各证据类别原绑定 hash）时，按类别复用判定 CI/review 证据是否仍有效（B-002/B-003/B-005）；`pr_metadata_hash` 单独变化不作废任何 CI/review 项。机械 SHA 字段经 `require_injected_sha` 校验（B-007/B-008）。未声明 `content_hashes` 时走现状整体 head_sha 路径，输出零变化（兼容回归）。
- `checks/runtime_gate_rules.py`：`_validate_terminal_review_summary`（:210）在 head_sha 比对（:221）前插入类别判定——若 item 与 review 均携带 `content_hashes.code_diff_hash` 且逐字一致，则视为代码类内容未变、review 仍有效，跳过 head_sha 逐字相等要求；否则维持现状 `review.get("head_sha") != head_sha` 严格校验（B-009，fail-closed）。敏感面（B-010）：`enforcement_sensitive` item 的复用额外要求 `spec_files_hash`/`code_diff_hash` 全部一致，任一缺失/变化即要求重绑，不弱于 GH-97 现状。
- `checks/runtime_ledger_gate.py`：merge-ready 证据校验块在类别复用成立时，强制审计字段（B-012）：`content_hashes` 三类齐全、各复用证据的 `reuse_binding.original_hash` 与来源、机械 SHA 的 `sha_provenance` 标记；任一缺失 → error（blocked）。类别复用不替代任何绿色证据检查，只判定既有证据能否跨 head 复用。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | `github_pr_evidence.py` 采集三类 hash | `test_evidence_records_content_hashes`（断言证据 dict 含 code_diff/spec_files/pr_metadata hash 与 sha_provenance） |
| B-002 | code_diff_hash 一致复用 CI/代码审查 | `test_same_code_diff_hash_reuses_ci_evidence`（新 head 同 code_diff_hash，CI 证据判仍有效） |
| B-003 | spec_files_hash 一致复用规格审查 | `test_same_spec_files_hash_reuses_review`（新 head 同 spec_files_hash，规格证据判仍有效） |
| B-004 | 仅变化类别需重取 | `test_only_changed_category_requires_recapture`（改 code 不改 spec，仅 code 类重取） |
| B-005 | 纯 metadata 变化不作废 | `test_metadata_only_change_preserves_ci_and_review`（仅 pr_metadata_hash 变，CI/review 全保留） |
| B-006 | hash 缺失/无法比对 fail-closed | `test_missing_content_hash_fails_closed`（缺 hash → 按已变化全量重取） |
| B-007 | 机械 SHA 需注入来源标记 | `test_handwritten_sha_without_provenance_rejected` |
| B-008 | 注入 SHA 与 live head 不一致拒绝 | `test_injected_sha_mismatch_rejected` |
| B-009 | terminal review 按 code_diff_hash 复用 | `python3 -m pytest -q tests/test_runtime_gate_rules.py -k terminal` + `test_terminal_review_reused_on_same_code_diff_hash` + `test_terminal_review_strict_when_hash_missing` |
| B-010 | 敏感面复用不弱于 #97 | `test_sensitive_reuse_requires_all_related_hashes_match`（任一相关 hash 变即重绑） |
| B-011 | 采集期 head 漂移按类别重采 | `test_head_drift_recaptures_changed_category_only`（最终三类 hash 对齐同一 head，禁混绑） |
| B-012 | 类别复用审计字段强制 | `test_reuse_missing_audit_fields_blocked`（逐一抹掉 content_hashes/reuse_binding/sha_provenance） |

## 数据流

证据采集：`gh` PR payload + diff 文本 + spec packet markdown → `compute_content_hashes` 产出三类 content hash + `sha_provenance` 注入标记 → 写入 evidence JSON（新增可选 `content_hashes` / `reuse_binding` / `sha_provenance`）。gate 评估：`pr_gate.py` / `runtime_gate_rules.py` / `runtime_ledger_gate.py` 只读比对新 head 各类别 hash 与既有证据原绑定 hash → 判定各类别证据可否复用 → decision + errors/rejection_items。未声明新字段的输入走现状整体 head_sha 路径，输出逐字节不变。无持久化、无网络调用、无跨仓库缓存。

## 备选方案

- 保持 exact-head 全量绑定（现状）：被否。实测 markdown-only PR 触发 6–8 遍全量 CI，成本模型不可持续（issue #166 实测证据）。
- 只按「代码 vs 非代码」二分绑定：被否。规格文件审查与代码审查是不同证据类别，二分无法让「改 spec 不改 code」复用代码 CI，粒度仍粗。
- 用单一「归一化 tree hash」替代 head SHA：被否。tree hash 仍是整体粒度，无法区分证据类别；且无法承载「PR body 变化不作废证据」（body 不入 tree）。
- 机械 SHA 仅约定命名不强制来源标记：被否。手写打错正是实测浪费源（2 次），无来源标记则无法在检查侧拒绝手填，达不到根除目的。

## 风险

- Security: 类别复用可能被伪造 hash 绕过（谎报 code_diff_hash 未变以跳过 CI）。缓解：hash 由采集侧 `compute_content_hashes` 从 live payload/diff 计算，证据侧的 `reuse_binding.original_hash` 必须能对应到既有已通过证据；敏感面（B-010）额外要求全部相关 hash 一致且不弱于 GH-97；一切歧义 fail-closed 回退全量取证。本实现 PR 触及 gate/enforcement 证据语义，按 heavy/敏感流程逐 PR 人工授权合并。
- Compatibility: 新增 `content_hashes`/`reuse_binding`/`sha_provenance` 全部可选；未声明时四个 gate 输出逐字节不变（B-009/B-010 兼容回归护住），下游宽松读取，无迁移。
- Performance: hash 为本地 SHA-256 计算，规格 markdown 与 diff 体量小，可忽略；换取的是避免 markdown-only PR 的 6–8 遍全量 CI。
- Maintenance: 三类 hash 的计算口径集中在 `github_evidence_common.py` 单一来源，避免各 gate 各算导致漂移；类别名单为闭集，新增类别会在校验处暴露而非静默放行。
- File size (U-16): `checks/github_pr_evidence.py`、`checks/runtime_ledger_gate.py` 已较大，新增辅助优先放 `checks/github_evidence_common.py`；实现后各文件 `wc -l` 复核，逼近 800 行硬上限即拆分。

## 测试计划

- [ ] Unit tests: `tests/test_github_pr_evidence.py`（B-001/B-006/B-007/B-008/B-011）、`tests/test_pr_gate.py`（B-002/B-004/B-005）、`tests/test_runtime_gate_rules.py`（B-009）、`tests/test_runtime_ledger_gate.py`（B-003/B-010/B-012）新增类别复用用例。
- [ ] Integration tests: 既有四个 gate 全套用例零改动全绿（未声明 content_hashes 的兼容回归）。
- [ ] Manual verification: 构造「仅改 spec markdown 新 head」与「仅改 PR body 新 head」两个 fixture，各跑一次采集 + gate CLI，确认 CI/review 证据判定复用、decision 不变。

## 回滚方案

回滚删除四个 checks 文件中的类别复用分支与 `github_evidence_common.py` 的 hash/注入辅助即可；新增字段全部可选、未写入任何持久状态，未声明 content_hashes 的 checkpoint/evidence 在回滚前后行为一致，无数据迁移。
