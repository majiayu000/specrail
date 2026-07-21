# Task Plan

## Linked Issue

GH-162

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP162-T1` 扩展 review artifact/schema/manifest aggregation，新增 `review_execution: local | hosted`，缺失、冲突、hosted-as-primary 与 self-review 组合均 fail closed。Covers: B-001 B-002 B-003 B-004 B-006 B-009 B-010。Owner: agent。Done when: semantic/manifest 负例与 local 正例全绿。Verify: `python3 -m pytest -q tests/test_review_json_gate.py`。
- [ ] `SP162-T2` 将派生 execution provenance 接入 GitHub PR evidence 与 schema，禁止仅靠顶层自报提升 hosted review。Covers: B-003 B-007 B-009。Owner: agent。Done when: adapter 正例派生 local，冲突/缺失测试阻断。Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py`。
- [ ] `SP162-T3` 同步 offline PR gate 和 runtime ledger 的 local-primary 断言及 fixtures。Covers: B-002 B-006 B-008 B-009 B-010。Owner: agent。Done when: hosted/缺失 provenance 双路径均 blocked，本地 independent 与合法 self-review 兼容路径通过。Verify: `python3 -m pytest -q tests/test_pr_gate_terminal.py tests/test_runtime_ledger_review.py`。
- [ ] `SP162-T4` 更新 `implx`、PR gate、agent usage 和 changelog，明确本地主审与 hosted supplemental 的命名和使用边界，并刷新 skill lock。Covers: B-005 B-007 B-008。Owner: agent。Done when: 文档不再把 `@codex review` 称作主要 Codex review，skill hashes 匹配。Verify: `python3 checks/check_workflow.py --repo .`。
- [ ] `SP162-T5` 运行全量测试、all-spec 与 diff 检查。Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010。Owner: agent。Done when: 所有 fresh commands 通过。Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`。

## 并行拆分

本任务不并行修改：schema、semantic aggregation、PR evidence 与 runtime ledger 共享 review
contract，串行实现可避免同一字段在多个 lane 中产生命名漂移。

## 验证

- Product invariants：B-001..B-010 全部被任务覆盖。
- Focused tests 与全量 tests 通过。
- PR 保持 Draft，human final review 与 merge gate 未被绕过。

## Handoff Notes

用户决策：hosted/cloud review 可作为 supplemental，但本地 CLI/native reviewer lane 必须
是 primary。Issue 创建与实现 PR 已获当前会话授权；未授权 merge。
