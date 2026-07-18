# Task Plan

## Linked Issue

GH-143

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP143-T1` `checks/runtime_gate_rules.py` 新增 `_validate_tier_authorization()`：source 约定值 `tier_policy_gh143` 触发；`authorization_tier` 闭集校验；`standard_auto` 要求 `pr_tier` ∈ {fastlane, standard} + `pr_tier_evidence` + 非敏感 + 无 `tier_dispute`；缺失/越界/无证据/争议全部 fail-closed 报 error。配套单元用例。Covers: B-002 B-003 B-004 B-006。Owner: agent. Done when: 校验函数覆盖全部拒绝分支且用例全绿. Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k tier`
- [ ] `SP143-T2` `checks/runtime_ledger_gate.py` 接线：merge_authorization 校验块调用 T1 函数并传入顶层 `auth_mode`；standard_auto item 强制审计字段（`pr_tier`/`pr_tier_evidence`/`authorization_tier`）；`post_authorization_findings[]` 校验（critical 或非机械 finding 无 re_authorization → blocked；severity 缺失/越界按 critical；mechanical 要求 `disposition: fixed_re_reviewed` 且复审证据对齐修复后 head）。Covers: B-001 B-005 B-006 B-008 B-009 B-010 B-012。Owner: agent. Done when: 全绿 fixture allowed、各拒绝 fixture blocked、既有用例零改动全绿. Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_review.py tests/test_runtime_ledger_queue.py`
- [ ] `SP143-T3` `checks/pr_gate.py` `_authorization_item()` 扩展：识别 tier-scoped 授权（`authorization_tier: standard_auto` + fastlane/standard + `pr_tier_evidence` + 非敏感）为 satisfied；其余情形保持 `human_authorization` 要求与 needs_human 语义；`authorization_tier` 越界产出 `invalid_evidence_value` rejection item。Covers: B-005 B-007 B-011。Owner: agent. Done when: tier 授权用例通过且既有 pr_gate 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py`
- [ ] `SP143-T4` SKILL.md auth_mode 语义更新：`skills/implx/SKILL.md`（review 段 + Boundaries）、`skills/specrail-implement-queue/SKILL.md`（Merge Authorization review 分支展开分级授权全文 + 新增分级重确认小节 + 证据清单追加 `pr_tier`/`authorization_tier` + PR Tier Lanes 一句授权关联 + Boundaries）、`skills/specrail-pr-gate/SKILL.md`（授权证据描述补 tier-scoped 来源）。Covers: B-001 B-002 B-008 B-009。Owner: agent. Done when: 三个 SKILL.md 均含 `authorization_tier` 与分级重确认约定且 workflow 校验通过. Verify: `grep -l authorization_tier skills/implx/SKILL.md skills/specrail-implement-queue/SKILL.md skills/specrail-pr-gate/SKILL.md | wc -l | grep -qx 3 && python3 checks/check_workflow.py --repo .`
- [ ] `SP143-T5` 端到端回归与审计演练:构造 standard_auto 全绿 checkpoint 走 gate CLI 得 allowed；同一 fixture 逐一抹掉四类绿色证据、改 heavy、置 `enforcement_sensitive: true`、注入 critical finding，逐个确认 blocked 及错误信息可定位。Covers: B-001 B-005 B-009 B-012。Owner: agent. Done when: 演练脚本化为测试或记录于 PR 描述附命令输出. Verify: `python3 checks/runtime_ledger_gate.py --checkpoint tests/fixtures/gh143-standard-auto.json --repo . --json`

## 并行拆分

T1 先行；T2 依赖 T1；T3 与 T1/T2 文件不相交可并行；T4 只改 skills/*/SKILL.md，依赖 T1-T3 确定的字段名后执行；T5 依赖 T2/T3。

## Verification

- `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_review.py tests/test_runtime_ledger_queue.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py`
- `python3 checks/check_workflow.py --repo .`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH143 --gate`

## Handoff Notes

- 本实现属授权语义变更，`pr_tier: heavy`：实现 PR 逐 PR 人工授权合并，不得引用本 spec 的 standard_auto 给自己授权。
- `merge_authorization.source` 约定值 `tier_policy_gh143` 是审计锚点，勿改名；未来新增 tier 时先改 SKILL.md PR Tier Lanes 再同步闭集校验。
- auto 模式零改动是硬约束（B-011），实现时以既有测试零改动为准绳。
