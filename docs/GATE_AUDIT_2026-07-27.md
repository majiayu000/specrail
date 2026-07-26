# Gate 事故率审计报告（2026-07-27，#208 Done-When C）

范围：`checks/` 全部 34 个模块（14,561 行），逐一列出，无抽样。
事故判据：仓库生命周期内（2026-06-21 起，≈36 天，覆盖"最近 30 天"窗口）该 gate 是否**拦截过真实缺陷**（有 rejection artifact、review finding 或 fix commit 佐证），还是仅产生流程摩擦（dry-run 状态标签缺失、格式重验等）。

## 实测拦截证据（.specrail/runtime/rejections/ + artifacts/review/）

| 记录 | 时间 | 性质 |
|---|---|---|
| `pr_gate-pr-205.json` | 07-26 16:59Z | **真实拦截**：独立审查 lane 记 5 条 blocking findings（含 1 条 critical fail-open），pr_gate 正确 blocked |
| `route_gate-199.json` | 07-27 | 摩擦：`write_spec` 要求 triaged 标签，dry-run 拒绝 |
| `route_gate-pr-181/186/193.json` | 07-26 | 摩擦：verification 字段缺失 warn |

## 逐模块处置（34/34 全量）

### 共享库（6 个，非 gate，保留）

| 模块 | 行数 | 结论 |
|---|---|---|
| specrail_lib.py | 656 | 保留（基础库） |
| github_evidence_common.py | 165 | 保留 |
| schema_validation.py | 418 | 保留 |
| rejection_items.py | 301 | 保留 |
| checks_availability.py | 123 | 保留（GH184 CI 结构性不可用区分，有真实动机事故） |
| pr_evidence_items.py | 171 | 保留 |

### 有真实拦截记录或持续 CI 价值（9 个，保留）

| 模块 | 行数 | 证据 | 结论 |
|---|---|---|---|
| pr_gate.py | 718 | 07-26 拦截 PR#205（5 findings，1 critical） | **保留** |
| check_workflow.py | 526 | CI 每次 PR 运行，历史多次拦截 spec 包缺陷 | **保留** |
| review_json_gate.py | 791 | PR#205 findings 经此管道产出 | 保留，但与下两项合并（三者共 2,220 行大量重叠） |
| review_result_semantics.py | 702 | 同上 | **合并**入 review_json_gate |
| pr_review_contract.py | 727 | 同上 | **合并**入 review_json_gate |
| github_pr_evidence.py | 734 | merge 证据核验主链路 | 保留 |
| github_issue_evidence.py | 326 | 同上 | 保留 |
| github_issue_reference.py | 230 | GH-partial 引用误闭事故（07-12 a62f379） | 保留 |
| closure_audit.py | 337 | merged-but-open 误留事故（GH116） | 保留 |

### 单一事故衍生集群（消重合并，2 组 9 个）

| 集群 | 模块 | 合计行数 | 结论 |
|---|---|---|---|
| GH97 敏感分类（07-14~16 一个事故衍生 6 模块） | sensitive_enforcement (716), github_approved_spec_evidence (592), github_pr_snapshot (233), github_review_evidence (566), spec_revision_evidence (261), runtime_sensitive_routes (161) | 2,529 | 事故真实但防御面过宽：**合并为 1 个 sensitive_gate 模块**，预计 ≤800 行 |
| GH166 证据内容绑定（07-23 一个事故衍生 3 模块） | evidence_content_binding (540), review_content_binding (269), runtime_review_evidence (84) | 893 | 事故真实（证据复用幻觉）：**合并为 1 个 content_binding 模块** |

### 30 天零真实拦截（8 个，降级或删除）

| 模块 | 行数 | 分析 | 结论 |
|---|---|---|---|
| route_gate.py | 705 | 4 条记录全为 dry-run 状态标签摩擦，无真实缺陷拦截 | **降级**：invalid_state 类由 block 改 warn，仅保留敏感路由 block |
| runtime_gate_rules.py | 796 | checkpoint 第二状态机字段校验，无拦截记录 | **删除大部**（PR#198 已实测 795→107 行方案） |
| runtime_ledger_gate.py | 788 | 同上 | **随 #198 收敛** |
| runtime_budget_dimensions.py | 292 | 预算维度校验，无拦截；实际超预算靠会话自觉 | **降级 warning** |
| session_telemetry.py | 228 | telemetry 交叉校验，无拦截 | **降级 warning** |
| review_round_semantics.py | 192 | 唯一"拦截"是挡 PR#207 round-4 修复（摩擦大于收益） | 保留 cap 但**降级**为需确认而非硬 block |
| duplicate_work_gate.py + github_duplicate_evidence.py | 473 | 07-04 引入以来无重复工单拦截记录 | **降级 warning** |
| pack_asset_validation.py | 139 | 服务 consumer 分发（#188 已 parked） | **随 #188 挂起**，从默认链路摘除 |
| runtime_tier_authorization.py | 355 | 07-26 发现其自身 fail-open（PR205-F001）——gate 本身是缺陷来源 | 保留但按 F001 修复收紧（本 PR 已含 fix） |

## 汇总

- 保留：15（含 6 库）；合并消重：9 → 2；降级 warning：7；挂起/摘除：1；随 #198 收敛：2
- 预计 checks/ 总行数 14,561 → **≈8,500**（-42%），gate 硬 block 面收窄至有真实拦截记录的链路
- 执行途径：合并与删除主体由 PR #198（二阶段）承载；本报告作为其评审依据

## 防复发钩子（写入 AGENTS.md）

新 gate 入库必须携带：动机事故的 issue 编号 + 预期拦截场景；连续 30 天零真实拦截且无安全属性的 gate 在月度审计中降级或删除。
