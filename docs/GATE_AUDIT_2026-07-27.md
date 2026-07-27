# Gate 事故率审计报告（2026-07-27，GH208 Done-When C）

范围：当前树 `checks/*.py` 全部 **36 个模块、14,779 行**。统计命令：

```sh
for f in checks/*.py; do printf '%s\t%s\n' "${f#checks/}" "$(wc -l < "$f")"; done | sort
wc -l checks/*.py
```

审计窗口为 2026-06-28 至 2026-07-27。事故证据只采用仓库内 rejection/review
artifact、可定位的 issue/PR finding 或修复提交；未找到证据时明确记为“无记录”，
不把推测写成事故。安全属性即使 30 天零拦截也可保留。

## 已核实证据

| 证据 | 性质 | 关联处置 |
|---|---|---|
| `.specrail/runtime/rejections/pr_gate-pr-205.json` 与 PR #205 review artifact | 真实拦截：5 条 blocking findings，含 fastlane fail-open | 保留 PR/review 主链与 tier 安全校验 |
| `.specrail/runtime/rejections/route_gate-199.json`、`route_gate-pr-181/186/193.json` | 流程摩擦：dry-run 状态/verification 缺失 | route/重复工作/预算类降级为 warning 候选 |
| GH97 | 敏感路径与批准规格信任边界，安全属性 | 保留能力，合并重复模块 |
| GH116、GH166、GH184 | issue closure、证据内容绑定、非默认 base CI 可用性事故 | 保留相应链路 |
| GH202 修复提交 `47cbfbf` | runtime/PR-gate tier evidence 绑定缺口 | 保留 runtime PR-gate binder |
| GH208 / PR #210 review | size gate false-green、protected filename 漏判、base retarget/rewrite 可复用 tier evidence、审计漏项 | 保留并修复 `skill_size_gate.py`、`runtime_tier_authorization.py`、`runtime_pr_gate_evidence.py` |

## 逐模块全量处置（36/36）

| # | 模块 | 行数 | 30 天事故或安全依据 | 处置 |
|---:|---|---:|---|---|
| 1 | `check_workflow.py` | 526 | CI 主验证链；历史持续拦截 workflow/spec 合同缺陷 | 保留 |
| 2 | `checks_availability.py` | 123 | GH184 非默认 base 的 CI 结构性不可用 | 保留（共享库） |
| 3 | `closure_audit.py` | 337 | GH116 merged-but-open | 保留 |
| 4 | `duplicate_work_gate.py` | 271 | 无真实重复工单拦截记录 | 降级 warning |
| 5 | `evidence_content_binding.py` | 540 | GH166 旧 head 证据复用 | 合并进单一 content-binding 模块 |
| 6 | `github_approved_spec_evidence.py` | 592 | GH97 安全属性 | 合并进单一 sensitive-gate 模块 |
| 7 | `github_duplicate_evidence.py` | 202 | 无真实重复工单拦截记录 | 与 duplicate gate 一并降级 warning |
| 8 | `github_evidence_common.py` | 165 | adapter 共用解析/信任边界 | 保留（共享库） |
| 9 | `github_issue_evidence.py` | 326 | issue readiness 证据主 adapter | 保留 |
| 10 | `github_issue_reference.py` | 230 | partial reference 误闭链路 | 保留 |
| 11 | `github_pr_evidence.py` | 796 | PR #205；GH208 base-drift finding | 保留 |
| 12 | `github_pr_snapshot.py` | 244 | GH97 完整 changed-file snapshot 安全属性 | 合并进单一 sensitive-gate 模块 |
| 13 | `github_review_evidence.py` | 587 | GH97 reviewer/resolver 信任边界 | 合并进单一 sensitive-gate 模块 |
| 14 | `pack_asset_validation.py` | 139 | 无拦截；consumer 分发工作随 #188 parked | 挂起并从默认链路摘除 |
| 15 | `pr_evidence_items.py` | 171 | PR gate rejection item 共用转换 | 保留（共享库） |
| 16 | `pr_gate.py` | 733 | PR #205 真实拦截；GH208 base-drift finding | 保留 |
| 17 | `pr_review_contract.py` | 754 | PR #205 review 主链，但与 review gate 重叠 | 合并进 `review_json_gate.py` |
| 18 | `rejection_items.py` | 301 | gate rejection 持久化共用合同 | 保留（共享库） |
| 19 | `review_content_binding.py` | 269 | GH166 review 证据复用 | 合并进单一 content-binding 模块 |
| 20 | `review_json_gate.py` | 791 | PR #205 review artifact 验证主链 | 保留，作为 review 合并目标 |
| 21 | `review_result_semantics.py` | 702 | PR #205 review 主链，但与 review gate 重叠 | 合并进 `review_json_gate.py` |
| 22 | `review_round_semantics.py` | 192 | 唯一观察为 PR #207 round-4 修复摩擦 | 降级为需确认 |
| 23 | `route_gate.py` | 705 | 已存记录均为状态/字段摩擦；敏感路由除外 | 普通 invalid-state 降级 warning，敏感路由保留 block |
| 24 | `runtime_budget_dimensions.py` | 292 | 无真实拦截记录 | 降级 warning |
| 25 | `runtime_gate_rules.py` | 796 | 无独立真实拦截；checkpoint 第二状态机重复 | 随 #198 收敛 |
| 26 | `runtime_ledger_gate.py` | 705 | 无独立真实拦截；承载 runtime 聚合 | 随 #198 收敛，保留必要安全绑定 |
| 27 | `runtime_pr_gate_evidence.py` | 132 | GH202；GH208 base-drift finding | 保留；docstring 记录 GH208 与拦截场景 |
| 28 | `runtime_review_evidence.py` | 84 | GH166 review 证据复用 | 合并进单一 content-binding 模块 |
| 29 | `runtime_sensitive_routes.py` | 161 | GH97 安全属性 | 合并进单一 sensitive-gate 模块 |
| 30 | `runtime_tier_authorization.py` | 525 | PR #205 fail-open；GH208 filename/base findings | 保留并 fail-closed 修复 |
| 31 | `schema_validation.py` | 418 | 所有 schema gate 的确定性基础 | 保留（共享库） |
| 32 | `sensitive_enforcement.py` | 716 | GH97 安全属性 | 保留能力，作为 sensitive 合并目标 |
| 33 | `session_telemetry.py` | 228 | 无真实拦截记录 | 降级 warning |
| 34 | `skill_size_gate.py` | 109 | GH208 anti-flywheel 验收；PR #210 false-green finding | 保留；实际 startup read-set 纳入预算 |
| 35 | `spec_revision_evidence.py` | 261 | GH97 spec approval 安全属性 | 合并进单一 sensitive-gate 模块 |
| 36 | `specrail_lib.py` | 656 | workflow/config/spec 共用基础 | 保留（共享库） |

行数合计复核：**14,779**。表中模块名与 `checks/*.py` 排序集合完全一致。

## 处置汇总

- 保留：16（含 6 个共享库/基础模块）。
- 合并消重：11 → 3 个既有目标（review、sensitive、content binding）。
- 降级 warning/需确认：6。
- 随 #198 收敛：2。
- 挂起/摘除：1。

本报告只给出处置结论，不在 GH208 同一修复中实施大规模删除或合并。新 gate
仍须在 docstring 写明真实 issue 与预期拦截场景；连续 30 天零真实拦截且无安全
属性的模块，在下一次审计中继续降级或删除。
