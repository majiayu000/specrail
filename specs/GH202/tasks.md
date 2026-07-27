# Task Plan

## Linked Issue

GH-202

## Spec Packet

- Product: `specs/GH202/product.md`
- Tech: `specs/GH202/tech.md`

## 实现任务

- [ ] `SP202-T1` Owner: tier-classifier; Dependencies: approved spec; Covers: B-001 B-002 B-003；Done when: shared classifier 强制 `changed_lines <= 50`、非空完整路径、受保护路径阻断和显式 `enforcement_sensitive=false`，缺失/非法值 fail closed；Verify: `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_pr_gate.py`。
- [ ] `SP202-T2` Owner: github-evidence; Dependencies: SP202-T1; Covers: B-003 B-004 B-009 B-010；Done when: paginated exact-head PR snapshot 汇总 additions/deletions 与完整路径，fastlane evidence 绑定 source/head/snapshot，竞态和部分数据报错；Verify: `.venv/bin/python -m pytest -q tests/test_github_pr_evidence.py tests/test_github_pr_evidence_approval.py tests/test_github_pr_content_binding.py`。
- [ ] `SP202-T3` Owner: pr-gate; Dependencies: SP202-T1 SP202-T2; Covers: B-001 B-002 B-006 B-007 B-008；Done when: `pr_gate` 只对可信 `fastlane_policy` 豁免 lane failure，普通 self-review、terminal artifact、CI/thread/merge/human gates 保持不变；Verify: `.venv/bin/python -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py tests/test_review_result_semantics.py tests/test_runtime_ledger_authorization.py`。
- [ ] `SP202-T4` Owner: runtime-binding; Dependencies: SP202-T3; Covers: B-005 B-007 B-008 B-009 B-010；Done when: runtime item 精确复制 current `pr_gate` tier/敏感性/binding 并二次分类，旧 head、缺失或不一致阻断；Verify: `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_gate_rules.py`。
- [ ] `SP202-T5` Owner: schemas-contract; Dependencies: SP202-T2 SP202-T3 SP202-T4; Covers: B-001 B-002 B-004 B-005 B-006 B-007；Done when: PR/runtime schemas 与 queue/implx/threads 对 basis、可信 tier evidence 和剩余门禁使用相同封闭合同，Skill lock 已刷新；Verify: `.venv/bin/python -m pytest -q tests/test_specrail_schema.py && .venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH202`。
- [ ] `SP202-T6` Owner: regression; Dependencies: SP202-T1 SP202-T2 SP202-T3 SP202-T4 SP202-T5; Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010；Done when: fail-open 复现、focused tests、packet/depth、all workflow 与 full suite 全绿；Verify: `.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH202 --gate && .venv/bin/python checks/check_workflow.py --repo . --all-specs && .venv/bin/python -m pytest -q && git diff --check`。

## 并行拆分

classifier、schemas 与两个 gate 是共享安全边界，按 T1→T5 串行修改；GitHub adapter
可在 classifier API 固定后独立实现，但本次由单一 integration owner 收口。最终只读
reviewer 使用 exact diff，不修改任何文件。

## 验证

```sh
.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_gate_rules.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py tests/test_github_pr_evidence.py tests/test_github_pr_evidence_approval.py tests/test_github_pr_content_binding.py tests/test_review_result_semantics.py tests/test_runtime_ledger_authorization.py tests/test_specrail_schema.py
.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH202
.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH202 --gate
git diff --check
```

## Handoff Notes

- 已复现旧门禁接受 `changed_lines=100000`、缺失敏感性字段的 fastlane 自评；这是必须
  保留的回归用例。
- 不得用 self-authored tier attestation 解锁 `standard_auto`。
- PR #205 的最终合并仍要求 fresh exact-head reviewer artifact 和
  `pr_gate=allowed`。
