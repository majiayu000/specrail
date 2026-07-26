# Task Plan

## Linked Issue

GH-203

## Spec Packet

- Product: `specs/GH203/product.md`
- Tech: `specs/GH203/tech.md`

## 实现任务

- [ ] `SP203-T1` Owner: shortcut-contract; Dependencies: approved spec; Covers: B-001 B-002 B-004 B-005 B-010；Done when: shortcut 仅接受单一 complete/non-legacy/decidable/non-heavy issue，明确省略三类 queue-only 产物，并对例外/耦合/漂移回退；Verify: `rg -n "Single-issue short circuit|complete|done-when|full-queue coverage|fall back" skills/implx/SKILL.md`。
- [ ] `SP203-T2` Owner: target-coverage; Dependencies: SP203-T1; Covers: B-003 B-004；Done when: queue skill 对 `bounded_tranche` 只分类 target/linked PR，`full_queue_drain` 才全分类，`exception_allowed` 不被描述为完整 packet；Verify: `rg -n "full_queue_drain|bounded_tranche|exception_allowed" skills/specrail-implement-queue/SKILL.md`。
- [ ] `SP203-T3` Owner: review-chain; Dependencies: SP203-T1; Covers: B-006 B-007 B-008 B-009 B-010；Done when: implx shortcut 与 scoped implement 明确 duplicate/route/spec-check、exact-head local review JSON/manifest、current evidence、serial PR gate 和 authorization；Verify: `rg -n "duplicate-work|review_json_gate|review-manifest|exact-head|pr_gate|authorization" skills/implx/SKILL.md skills/specrail-implement/SKILL.md`。
- [ ] `SP203-T4` Owner: verification; Dependencies: SP203-T1 SP203-T2 SP203-T3; Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010；Done when: Skill lock、packet/depth、review/PR gate regressions 与 workflow checks 全绿；Verify: `.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py && .venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH203 && .venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH203 --gate && git diff --check`。

## 并行拆分

三个 Skill 共同定义一条 shortcut 证据链，必须由单一 owner 串行收口。只读 reviewer
可分别演练 complete/exception/heavy/drift 四个场景，不修改文件。

## 验证

```sh
.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py
.venv/bin/python checks/check_workflow.py --repo . --spec-dir specs/GH203
.venv/bin/python tools/spec_depth_audit.py --spec-dir specs/GH203 --gate
git diff --check
```

## Handoff Notes

- `exception_allowed` 是非 spec 例外，不等于 `complete`；不得留在 shortcut 资格中。
- shortcut 仍需 exact-head local review artifact + manifest，不能只传
  `--review-source`。
- PR #205 最终需对 shortcut 合同变更执行 independent diff-only re-review。
