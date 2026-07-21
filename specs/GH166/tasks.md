# Task Plan

## Linked Issue

GH-166

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP166-T1` `checks/github_evidence_common.py` 新增内容 hash 与注入校验辅助：`compute_content_hashes(pr_payload, diff_text, spec_files) -> {code_diff_hash, spec_files_hash, pr_metadata_hash}`（各类别 SHA-256，diff 规范化去噪、spec markdown 内容拼接、body/title 归一化）；`require_injected_sha(evidence, field, label)` 校验机械 SHA 字段携带 `sha_provenance` 注入来源标记，缺失或与 live head 不一致即 EvidenceError。配套单元用例。Covers: B-001 B-007 B-008。Owner: agent. Done when: 三类 hash 稳定可复算且注入校验覆盖缺失/不一致分支、用例全绿. Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py -k hash`
- [ ] `SP166-T2` `checks/github_pr_evidence.py` 采集接线：在 `head_sha` 采集处（:291-311）调用 `compute_content_hashes` 写入可选 `content_hashes`，并写入 `sha_provenance` 标记 head_sha/gate_query_head_sha 注入来源；snapshot 一致性（:325）与 head 漂移（:512）分支改为按相关类别 hash 判定复用、仅对变化类别重采，任一相关类别 hash 缺失 fail-closed 回退现状全量重采；未声明 content_hashes 的输入走现状路径零变化。Covers: B-001 B-006 B-011。Owner: agent. Done when: 类别复用/漂移重采用例全绿且既有 github_pr_evidence 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py`
- [ ] `SP166-T3` `checks/pr_gate.py` 证据项（:325）扩展：evidence 声明 `content_hashes` + `reuse_binding` 时按类别复用判定 CI/review 证据有效性（B-002/B-004），`pr_metadata_hash` 单独变化不作废任何 CI/review 项（B-005）；机械 SHA 经 `require_injected_sha` 校验；未声明 content_hashes 走现状整体 head_sha 路径零变化。Covers: B-002 B-004 B-005 B-007。Owner: agent. Done when: 类别复用用例通过且既有 pr_gate 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_pr_gate.py`
- [ ] `SP166-T4` `checks/runtime_gate_rules.py` `_validate_terminal_review_summary`（:210）改造：head_sha 比对（:221）前插入 `code_diff_hash` 一致判定——一致则 review 仍有效跳过 head_sha 逐字要求，缺失/变化回退现状严格校验（fail-closed）；`enforcement_sensitive` item 额外要求相关 hash（spec_files/code_diff）全部一致方可复用，不弱于 GH-97。Covers: B-009 B-010。Owner: agent. Done when: terminal review 复用用例与敏感面严格用例全绿、既有用例零改动. Verify: `python3 -m pytest -q tests/test_runtime_gate_rules.py -k terminal`
- [ ] `SP166-T5` `checks/runtime_ledger_gate.py` merge-ready 证据校验块接线：类别复用成立时强制审计字段（`content_hashes` 三类齐全、各 `reuse_binding.original_hash` 与来源、机械 SHA 的 `sha_provenance`），任一缺失 → error(blocked)；类别复用不替代任何绿色证据检查。Covers: B-003 B-012。Owner: agent. Done when: 审计字段缺失 fixture blocked、spec_files_hash 复用 fixture allowed、既有用例零改动全绿. Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`
- [ ] `SP166-T6` 端到端回归与审计演练：构造「仅改 spec markdown 新 head」与「仅改 PR body 新 head」两个 fixture，各跑一次采集 + 四个 gate CLI，确认未变化类别 CI/review 证据判复用、decision 不变；再构造「code_diff_hash 变化」fixture 确认该类别被要求重取。Covers: B-002 B-003 B-004 B-005 B-006。Owner: agent. Done when: 演练脚本化为测试或记录于 PR 描述附命令输出. Verify: `python3 checks/check_workflow.py --repo .`

## 并行拆分

T1 先行（定义 hash 计算与字段名）；T2 依赖 T1；T3/T4/T5 各改独立 checks 文件，字段名以 T1 落定后可并行，各自不重叠文件所有权（`checks/pr_gate.py` / `checks/runtime_gate_rules.py` / `checks/runtime_ledger_gate.py`）；T6 依赖 T2-T5。

## 验证

- `python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_pr_gate.py tests/test_runtime_gate_rules.py tests/test_runtime_ledger_gate.py`
- `python3 checks/check_workflow.py --repo .`

## Handoff Notes

- 本实现触及 gate/enforcement 证据语义，`pr_tier: heavy`/敏感：实现 PR 逐 PR 人工授权合并，不得用类别复用给自己的证据松绑。
- 三类 hash 计算口径集中在 `github_evidence_common.py` 单一来源，勿在各 gate 各算，避免绑定漂移。
- 兼容硬约束（B-009/B-010）：未声明 content_hashes 的既有 checkpoint/evidence 必须输出逐字节不变，以既有四个 gate 测试零改动为准绳。
- fail-closed 是本 spec 的安全底线：hash 缺失/无法比对一律按「已变化」，敏感面复用不弱于 GH-97。
