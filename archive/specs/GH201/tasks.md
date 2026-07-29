# Task Plan

## Linked Issue

GH-201

## Spec Packet

- Product: `specs/GH201/product.md`
- Tech: `specs/GH201/tech.md`

## 实现任务

- [ ] `SP201-T1` Owner: spawn-contract; Dependencies: approved spec; Covers: B-001 B-002 B-003 B-007；Done when: queue 与 threads 对所有 lane 固定 task/ref/spec/carry 四类输入并禁止 full-history；Verify: `rg -n "minimal context pack|fork_turns: all|explicit file paths" skills/specrail-implement-queue/SKILL.md integrations/threads.md`。
- [ ] `SP201-T2` Owner: orchestration-boundaries; Dependencies: SP201-T1; Covers: B-004 B-005 B-006 B-008；Done when: resume/diff-only、output firewall、durable handoff 与 disjoint ownership 合同可定位且现有 tests 绿色；Verify: `.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate_terminal.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_gate.py`。
- [ ] `SP201-T3` Owner: pack-verification; Dependencies: SP201-T1 SP201-T2; Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008；Done when: packet、depth、workflow、lock 与 diff 全绿；Verify: `.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH201 && .venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH201 --gate && git diff --check`。

## 并行拆分

两个 agent-facing 合同共享语义，串行收口；只读 reviewer 可核对角色覆盖和禁止项。

## 验证

```sh
.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate_terminal.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_gate.py
.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH201
.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH201 --gate
git diff --check
```

## Handoff Notes

- minimal context 不削弱 ownership、review independence 或 output firewall。
- 不把 raw session JSONL 写入任何 repo artifact。
