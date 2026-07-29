# Task Plan

## Linked Issue

GH-199

## Spec Packet

- Product: `specs/GH199/product.md`
- Tech: `specs/GH199/tech.md`

## 实现任务

- [ ] `SP199-T1` Owner: contract; Dependencies: approved spec; Covers: B-001 B-002 B-003 B-004 B-005；Done when: queue Skill 明确 focused/full/CI 三层职责、一次本地 full-suite、exact-head 证据归属与全部失效条件；Verify: `rg -n "focused tests|full-suite|CI rollup|exact-head" skills/specrail-implement-queue/SKILL.md`。
- [ ] `SP199-T2` Owner: evidence-verification; Dependencies: SP199-T1; Covers: B-006 B-007 B-008；Done when: CI coverage、runtime budget、head race 与 evidence reuse 的现有 fail-closed tests 全绿；Verify: `.venv/bin/python -m pytest -q tests/test_runtime_ledger_budget.py tests/test_github_pr_content_binding.py tests/test_review_content_binding.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py`。
- [ ] `SP199-T3` Owner: pack-verification; Dependencies: SP199-T1 SP199-T2; Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008；Done when: spec packet、Skill lock、workflow pack 和 whitespace 均通过；Verify: `.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH199 && .venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH199 --gate && git diff --check`。

## 并行拆分

queue Skill 与 `skills-lock.json` 是共享收口面，任务必须串行。只读 reviewer 可在
SP199-T2 后检查 B-001..B-008，不得修改文件。

## 验证

```sh
.venv/bin/python -m pytest -q tests/test_runtime_ledger_budget.py tests/test_github_pr_content_binding.py tests/test_review_content_binding.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py
.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH199
.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH199 --gate
git diff --check
```

## Handoff Notes

- 用户在当前会话授权继续修复 PR #205，但 merge 仍以 fresh `pr_gate=allowed` 为准。
- GH-199 不改变授权或 review gate；未知 CI coverage 必须 fail closed。
