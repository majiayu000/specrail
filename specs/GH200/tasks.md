# Task Plan

## Linked Issue

GH-200

## Spec Packet

- Product: `specs/GH200/product.md`
- Tech: `specs/GH200/tech.md`

## 实现任务

- [ ] `SP200-T1` Owner: orchestration-contract; Dependencies: approved spec; Covers: B-001 B-002 B-006；Done when: queue 与 threads 对默认单 lane、heavy/人工/lane-failure 例外和 retry identity 使用相同规则；Verify: `rg -n "One reviewer lane per PR|heavy|lane failure" skills/specrail-implement-queue/SKILL.md integrations/threads.md`。
- [ ] `SP200-T2` Owner: artifact-contract; Dependencies: SP200-T1; Covers: B-003 B-004 B-005 B-007 B-008；Done when: artifact-only repair 与 bounded re-review 的分流明确，current-head/manifest tests 全绿；Verify: `.venv/bin/python -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py tests/test_review_content_binding.py tests/test_runtime_ledger_review.py tests/test_pr_gate_terminal.py`。
- [ ] `SP200-T3` Owner: pack-verification; Dependencies: SP200-T1 SP200-T2; Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008；Done when: packet、depth、workflow、lock 与 whitespace 全绿；Verify: `.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH200 && .venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH200 --gate && git diff --check`。

## 并行拆分

queue 和 threads 都是共享 orchestration 合同，串行修改。只读 reviewer 可检查两处
措辞一致性，不得写文件。

## 验证

```sh
.venv/bin/python -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py tests/test_review_content_binding.py tests/test_runtime_ledger_review.py tests/test_pr_gate_terminal.py
.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH200
.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH200 --gate
git diff --check
```

## Handoff Notes

- artifact repair 不得解决或隐藏 reviewer finding。
- PR #205 最终仍需 independent diff-only re-review 与 fresh PR gate。
