# Task Plan

## Linked Issue

GH-166

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP166-T1` 新增 `checks/evidence_content_binding.py`：实现 base-tree-bound code hash、path+length+bytes spec hash、canonical metadata hash、v1 shape/coverage matcher。Covers: B-001 B-002 B-003 B-008。Owner: implementation lane。Depends on: none。Done when: base advance、rename/split、拼接碰撞、coverage key mismatch 全部有负例。Verify: `/usr/bin/python3 -m pytest -q tests/test_github_pr_evidence.py -k content_binding`。
- [ ] `SP166-T2` 扩展 `checks/github_evidence_common.py`/`checks/github_pr_evidence.py`：在稳定 final head/base/file/relation snapshot 计算三类 hash，为每个 check 从可信 mapping 注入 coverage；漂移整份 current snapshot 重采。Covers: B-001 B-004 B-008 B-009。Owner: implementation lane。Depends on: T1。Done when: `workflow-check` 覆盖 spec，head/base/files/relation drift 不产生 mixed snapshot。Verify: `/usr/bin/python3 -m pytest -q tests/test_github_pr_evidence.py`。
- [ ] `SP166-T3` 扩展 `schemas/pr_review_gate.schema.json`、`schemas/review_result.schema.json`、`schemas/runtime_checkpoint.schema.json` 与 schema tests：v1 字段 closed/conditional，legacy 无 provenance 仍合法，partial/unknown/mixed version 拒绝。Covers: B-007 B-008 B-010。Owner: schema lane。Depends on: T1 field contract。Done when: 三 schema 对相同 fixture 判定一致且文件均 ≤800 行。Verify: `/usr/bin/python3 -m pytest -q tests/test_specrail_schema.py tests/test_review_json_gate.py`。
- [ ] `SP166-T4` 扩展 `checks/review_result_semantics.py` 与 `checks/pr_review_contract.py`：review artifact 声明 covered categories/bindings；previous-head component 仅在全部 covered hash 匹配时复用，spec/metadata covered 变更必失效。Covers: B-003 B-005 B-006 B-011 B-013。Owner: review-contract lane。Depends on: T1 T3。Done when: current/previous-head、spec-aware、sensitive、legacy matrix 全绿且无只看 code hash 的快捷路径。Verify: `/usr/bin/python3 -m pytest -q tests/test_review_json_gate.py tests/test_pr_gate.py`。
- [ ] `SP166-T5` 更新 `checks/pr_gate.py`：每个 current head 重新采集 live gates，只复用 coverage-matched CI/review components并输出完整 reuse audit；旧 pr_gate decision 不可复用。Covers: B-004 B-006 B-012 B-014。Owner: pr-gate lane。Depends on: T2–T4。Done when: metadata/spec/component cases正确，threads/merge/auth/query freshness 始终 current-head。Verify: `/usr/bin/python3 -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py`。
- [ ] `SP166-T6` 更新 `checks/runtime_gate_rules.py`/`checks/runtime_ledger_gate.py`：previous-head review 走共享 coverage matcher；loaded pr_gate result 与 item `pr_gate.head_sha` 仍严格等于 current item head，只验证内部 reuse audit。Covers: B-011 B-012 B-013 B-014。Owner: runtime lane。Depends on: T3–T5。Done when: current wrapper+reused component allowed，old gate result/missing audit/category mismatch blocked；ledger 文件 ≤800 行。Verify: `/usr/bin/python3 -m pytest -q tests/test_runtime_gate_rules.py tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_review.py`。
- [ ] `SP166-T7` 端到端覆盖 spec-only、metadata-only、base-advance-same-patch 与 mixed change，运行 full suite/workflow/depth/size gates；不得弱化 legacy assertions。Covers: B-001..B-014。Owner: coordinator。Depends on: T1–T6。Done when: 仅真正 coverage-matched组件复用，current gate与所有实时 gate 重跑，全量绿。Verify: `/usr/bin/python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH166 --gate`。

## 并行拆分

T1 先固定 contract；T2 与 T3 可分离。T4 依赖 schema；T5 依赖 collector/review；T6 最后接 runtime。不同 lane 不共享 writable files，reviewer 只读。

## Verification

- `/usr/bin/python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH166 --gate`
- `git diff --check`

## Handoff Notes

- legacy evidence 不要求 provenance；只有 `content_binding_version: 1` opt-in。
- `workflow-check` 读取 specs，必须覆盖 `spec_files`。
- 不复用旧 `pr_gate` decision；implementation PR 用 `Closes #166` 并按 heavy/敏感授权。
