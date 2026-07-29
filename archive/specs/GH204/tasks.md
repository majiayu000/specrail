# Task Plan

## Linked Issue

GH-204

## Spec Packet

- Product: `specs/GH204/product.md`
- Tech: `specs/GH204/tech.md`

## 实现任务

- [ ] `SP204-T1` Owner: queue-authority; Dependencies: approved spec; Covers: B-001 B-002；Done when: 完整 `specrail_implementation_queue` 只在 queue Skill 出现一次，threads 仅保留不同名 extension/ref；Verify: `test "$(rg -l '^specrail_implementation_queue:$' skills integrations | wc -l | tr -d ' ')" -eq 1 && rg -n "authoritative queue block|orchestration extension" integrations/threads.md`。
- [ ] `SP204-T2` Owner: checkpoint-references; Dependencies: SP204-T1; Covers: B-003 B-004 B-007 B-009 B-010；Done when: dispatch/budget/firewall 只写 checkpoint，implx/threads handoff/report 仅引用，三点 cadence、恢复 gate 与 fresh truth 明确；Verify: `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_budget.py && rg -n "recorded exactly once|three required points|fresh remote truth" skills/implx/SKILL.md integrations/threads.md skills/specrail-implement-queue/SKILL.md`。
- [ ] `SP204-T3` Owner: reviewer-conflict; Dependencies: SP204-T1; Covers: B-005 B-006；Done when: small-file/native-review 决策只引用 GH202 `fastlane_policy`，standard/heavy/unknown 保留 native reviewer；Verify: `rg -n "fastlane_policy|small single-file|standard.*heavy|native reviewer" integrations/threads.md skills/specrail-implement-queue/SKILL.md`。
- [ ] `SP204-T4` Owner: cadence-and-size; Dependencies: SP204-T2 SP204-T3; Covers: B-007 B-008 B-011；Done when: closure audit tranche 末批量一次，queue Skill 删除重复后不超过 800 行且关键 gate/authorization 文本仍可定位；Verify: `test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 800 && rg -n "once per tranche|one batch" integrations/threads.md && .venv/bin/python checks/check_workflow.py --repo .`。
- [ ] `SP204-T5` Owner: regression; Dependencies: SP204-T1 SP204-T2 SP204-T3 SP204-T4; Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011；Done when: runtime/review/closure focused tests、packet/depth/all-specs、Skill lock、full suite 和 diff check 全绿；Verify: `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_review.py tests/test_closure_audit.py && .venv/bin/python checks/check_workflow.py --repo . --all-specs && .venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH204 --gate && git diff --check`。

## 并行拆分

queue、threads 与 implx 是同一合同的三个消费者，串行编辑并由单一 owner 收口。
只读 reviewer 可检查删减前后的闭集字段、授权条件和恢复语义，不得修改文件。

## 验证

```sh
.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_review.py tests/test_closure_audit.py
.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH204
.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH204 --gate
test "$(rg -l '^specrail_implementation_queue:$' skills integrations | wc -l | tr -d ' ')" -eq 1
test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 800
git diff --check
```

## Handoff Notes

- queue block 的唯一权威位置是 `skills/specrail-implement-queue/SKILL.md`。
- checkpoint 是 handoff 单点，不替代 GitHub/spec durable truth。
- queue Skill 当前 872 行；必须在不删门禁语义的前提下收敛到 <=800。
