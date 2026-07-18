# Tech Spec

## Linked Issue

GH-143

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":143,"complete":true,"paths":["checks/runtime_ledger_gate.py","checks/runtime_gate_rules.py","checks/pr_gate.py","tests/test_runtime_ledger_gate.py","tests/test_pr_gate.py","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-pr-gate/SKILL.md"],"spec_refs":["specs/GH143/product.md","specs/GH143/tech.md","specs/GH143/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| pr_gate 授权项 | `checks/pr_gate.py:198` | `_authorization_item()` 只认 `human_authorization` 对象且要求 `actor`/`source` 非空；缺失时返回 missing，消费点 `checks/pr_gate.py:312` 汇入后由 `checks/pr_gate.py:368` 的判定逻辑落 `needs_human`（仅 human_authorization 缺失时）或 blocked | B-007 的唯一改造点：授权项需新增识别 tier-scoped 授权来源 |
| pr_gate 敏感面 | `checks/pr_gate.py:317` | `has_sensitive_evidence` 汇集 `enforcement_sensitive`/`sensitive_classification`/`approved_spec` 与 pack registry，敏感复核失败汇入 reasons；结果对象在 `checks/pr_gate.py:391` 输出 `enforcement_sensitive` 布尔 | B-002/B-007：敏感 PR 不得走 tier 自动授权，判定复用该布尔 |
| ledger gate 授权校验 | `checks/runtime_ledger_gate.py:616` | merge-ready item 要求 `merge_authorization` 为对象且 `actor`/`source` 非空字符串，无 tier 概念 | B-006 的改造点：source 声明 tier 授权时追加 tier 一致性校验 |
| ledger gate merge-ready 证据 | `checks/runtime_ledger_gate.py:522` | merge-ready item 已强制 CI 绿（:536-540）、review 通过（:542-580）、review_threads 干净且 unresolved_count 为 0（:582-595）、pr_gate passed 且 evidence 复评（:597-610）、merge_state clean（:612-614） | B-001/B-005 的四类绿色证据已有现成校验，tier 授权直接叠加其上，不重复造证据检查 |
| ledger gate 敏感 item | `checks/runtime_ledger_gate.py:101` | `_validate_enforcement_sensitive()` 校验布尔；`checks/runtime_ledger_gate.py:177` 敏感 item 强制本地机器可读 pr_gate 证据 | B-006：`enforcement_sensitive: true` 的 item 拒绝 standard_auto |
| 授权辅助规则 | `checks/runtime_gate_rules.py:170` | `_validate_self_review_authorization()` 已示范"授权对象 + auth_mode 上下文"的校验形态（actor/source/scope + 模式相关分支） | 新增 `_validate_tier_authorization()` 参照同一形态放入本模块，供 ledger gate 调用 |
| implx auth_mode 语义 | `skills/implx/SKILL.md:56` | `auth_mode: review` 要求"per-PR explicit human merge authorization"无任何例外；`skills/implx/SKILL.md:179` Boundaries 重申 review 模式不经人工授权不得合并 | B-001/B-002 的文档强制点之一：review 段与 Boundaries 段需写入 tier 分级例外 |
| implement-queue tier 定义 | `skills/specrail-implement-queue/SKILL.md:86` | PR Tier Lanes 已定义 `pr_tier`（heavy/standard/fastlane）、证据规则（changed-line 数、touched paths）、CI tier check 为准、存疑取重 | tier 本体不动，B-003/B-004 的 fail-closed 与争议规则与"存疑取重"同向 |
| implement-queue 合并授权 | `skills/specrail-implement-queue/SKILL.md:576` | Merge Authorization 小节：auto 分支为站立授权；`skills/specrail-implement-queue/SKILL.md:598` review 分支一句话"逐 PR 人工授权"，`skills/specrail-implement-queue/SKILL.md:634` Boundaries 重申 | B-001/B-008/B-009 的文档强制点：review 分支改写为 tier 分级 + 重确认规则 |
| pr-gate skill 授权文档 | `skills/specrail-pr-gate/SKILL.md:40` | 描述收集"human merge authorization"证据，无 tier 概念 | 授权证据描述需同步 tier-scoped 来源，避免文档与 gate 语义漂移 |

## Proposed Design

- `checks/runtime_gate_rules.py` 新增 `_validate_tier_authorization(item, label, errors)`（形态参照 `checks/runtime_gate_rules.py:170` 的 self-review 校验）：
  - 触发条件：merge-ready item 的 `merge_authorization.source` 声明 tier 授权（约定 source 值 `tier_policy_gh143`，同时 item 携带 `authorization_tier` 字段）。
  - 校验（B-006）：`authorization_tier` ∈ {`standard_auto`, `heavy_manual`}；取 `standard_auto` 时要求 `pr_tier` ∈ {fastlane, standard} 且 item 带 `pr_tier_evidence`（changed-line 数 + touched paths，或 CI tier check 引用），`enforcement_sensitive` 非 true；`pr_tier` 缺失/越界/无证据 → error（fail-closed 按 heavy，B-003）；item 记录 `tier_dispute: true` 时 standard_auto 无效（B-004）。
  - `heavy_manual` 路径不新增要求：沿用既有 actor/source 人工授权校验（`checks/runtime_ledger_gate.py:616`）。
- `checks/runtime_ledger_gate.py`：在 merge_authorization 校验块（`checks/runtime_ledger_gate.py:616`）调用 `_validate_tier_authorization`；`auth_mode` 从 checkpoint 顶层读取（与 `checks/runtime_ledger_gate.py:560` 传 self-review 校验同源）。`auth_mode: auto` 时 tier 校验不改变任何现状判定（B-011）。standard_auto item 的审计字段（B-012）：`pr_tier`、`pr_tier_evidence`、`authorization_tier` 任一缺失即 error；四类绿色证据沿用 :522-614 的既有强制，不重复实现。
- `checks/pr_gate.py`：`_authorization_item()`（`checks/pr_gate.py:198`）扩展（B-007）：evidence 存在 `authorization_tier: standard_auto` 且 `pr_tier` ∈ {fastlane, standard} 且带 `pr_tier_evidence` 且 evidence 的 `enforcement_sensitive` 非 true（含 sensitive 复核结论，`checks/pr_gate.py:391` 同源布尔）时，返回 satisfied（`tier authorization: standard_auto (pr_tier=...)`），不再要求 `human_authorization`；其余情形（heavy、敏感、tier 证据缺失、`authorization_tier` 越界）保持现状返回 missing → decision 落 `needs_human`（`checks/pr_gate.py:368` 判定逻辑不动，B-007 兼容）。`authorization_tier` 越界取值追加 `invalid_evidence_value` rejection item。
- 重确认规则（B-008/B-009/B-010）主要落在 SKILL.md 语义层 + ledger gate 记录层：
  - item 新增可选 `post_authorization_findings[]`：每条含 `severity`（closed set：`critical`/`important`/`minor`/`nit`）、`mechanical`（bool）、`disposition`（`fixed_re_reviewed`/`paused_re_authorized`）。
  - ledger gate 校验：存在 `severity: critical` 或 `mechanical: false` 的 finding 而 item 仍为 merged/merge-ready 且无新一轮 `merge_authorization`（或 `re_authorization` 记录）→ error（B-009）；`severity` 缺失/越界按 critical 处理（B-010）；`mechanical: true` 的 finding 要求 `disposition: fixed_re_reviewed` 且 review 证据为修复后 head（复用 `checks/runtime_gate_rules.py:197` 的 terminal review summary head 一致性）。
- `skills/implx/SKILL.md`：review 模式段（:56-62）与 Boundaries（:179）改写：review 模式下 fastlane/standard + 全绿证据 = tier 自动授权（记录 `authorization_tier: standard_auto`，不逐 PR 提问）；heavy/敏感逐 PR 人工授权；tier 缺失/歧义/争议按 heavy。
- `skills/specrail-implement-queue/SKILL.md`：Merge Authorization 小节（:576）review 分支展开为分级授权全文（B-001..B-005）+ 分级重确认小节（B-008..B-010）；Review And Verification 证据清单（:518-534）追加 `pr_tier` 证据与 `authorization_tier`；Boundaries（:634）同步。PR Tier Lanes（:86）追加一句：tier 同时决定 review 模式合并授权路径，存疑取重规则对授权同样生效。
- `skills/specrail-pr-gate/SKILL.md`：授权证据描述（:40）补充 tier-scoped 授权来源与其证据要求。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | ledger gate tier 授权通过路径 + SKILL.md review 段 | `test_standard_auto_merge_ready_allowed`（fastlane/standard 全绿 fixture，gate allowed，无 human actor） |
| B-002 | `_validate_tier_authorization` 敏感/heavy 拒绝 | `test_heavy_or_sensitive_rejects_standard_auto`（heavy tier 与 `enforcement_sensitive: true` 两个 fixture 均 blocked） |
| B-003 | tier 缺失/越界/无证据 fail-closed | `test_missing_or_unevidenced_tier_fails_closed` |
| B-004 | `tier_dispute` 阻断 | `test_disputed_tier_blocks_standard_auto` |
| B-005 | 绿色证据缺口下 standard_auto 不成立 | `test_evidence_gap_not_covered_by_tier_authorization`（逐类抹掉 CI/threads/pr_gate/reviewer 证据，均 blocked） |
| B-006 | ledger gate merge_authorization tier 校验 | `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k tier` |
| B-007 | pr_gate `_authorization_item` 扩展 + 兼容 | `test_pr_gate_tier_scoped_authorization_allowed` + 既有 `tests/test_pr_gate.py` 用例零改动全绿 |
| B-008 | `post_authorization_findings` 机械路径 | `test_mechanical_findings_merge_within_original_authorization`（important + mechanical + fixed_re_reviewed → allowed） |
| B-009 | critical/扩面暂停重授权 | `test_critical_finding_requires_re_authorization`（critical 无 re_authorization → blocked） |
| B-010 | 严重度缺失按 critical | `test_unknown_severity_treated_as_critical` |
| B-011 | auto 模式零回归 | 既有 `tests/test_runtime_ledger_gate.py`、`tests/test_runtime_ledger_review.py`、`tests/test_pr_gate.py` 零改动全绿 |
| B-012 | standard_auto 审计字段强制 | `test_standard_auto_missing_audit_fields_blocked`（逐一抹掉 pr_tier/pr_tier_evidence/authorization_tier） |

## Data Flow

checkpoint/evidence JSON（新增可选字段：item 级 `pr_tier_evidence`、`authorization_tier`、`tier_dispute`、`post_authorization_findings[]`；`merge_authorization.source` 新约定值 `tier_policy_gh143`）→ `runtime_ledger_gate.py` / `pr_gate.py` 只读评估 → decision + errors/rejection_items。未声明新字段的输入走既有路径，输出零变化。无持久化、无网络调用。

## Alternatives Considered

- 方案 A（issue 内被否）：review 模式一律保持逐 PR 授权。被 owner 决策 B 取代：仪式性授权无信息量且阻塞吞吐。
- 把 tier 授权做成 auto 模式的子集（review 下建议用户切 auto）：被否。auto 会同时改变 needs_spec 处置、evidence-gap 跳过等语义，粒度过粗；决策 B 要求的是 review 模式内的分级。
- 授权后新增 findings 一律重新授权（不分级）：被否。owner 补充决策明确机械性 findings 在原授权内闭环，否则重确认打断把 standard_auto 的收益清零。
- source 不约定固定值、仅凭 `authorization_tier` 字段触发校验：被否。`merge_authorization.source` 是既有审计锚点（`checks/runtime_ledger_gate.py:622`），固定值使"这次合并凭什么授权"可 grep 审计。

## Risks

- Security: 授权面放宽仅限非敏感 fastlane/standard；敏感判定复用既有 `enforcement_sensitive` 双源（evidence 声明 + pack registry 复核，`checks/pr_gate.py:317`），且 fail-closed。本实现 PR 自身属授权语义变更，按 heavy 流程人工授权合并。
- Compatibility: 新字段全部可选，未声明时两个 gate 输出逐字节不变（B-007/B-011 回归护住）；下游宽松读取。
- Performance: 纯本地字段校验，可忽略。
- Maintenance: tier 名单（fastlane/standard/heavy）与 SKILL.md 的 PR Tier Lanes 单一来源对齐；若未来新增 tier，`_validate_tier_authorization` 的闭集校验会把漂移暴露为 gate error 而非静默放行。
- File size (U-16): `checks/runtime_ledger_gate.py` 现 675 行，新增校验放入 `checks/runtime_gate_rules.py`（现 400+ 行）避免主文件逼近 800 行硬上限；两文件实现后均须 `wc -l` 复核，超限则拆分。

## Test Plan

- [ ] Unit tests: `tests/test_runtime_ledger_gate.py` 新增 tier 授权用例（B-001..B-006、B-008..B-010、B-012）；`tests/test_pr_gate.py` 新增 tier-scoped 授权项用例（B-007）。
- [ ] Integration tests: 既有 pr_gate / runtime_ledger 全套用例零改动全绿（B-007/B-011）。
- [ ] Manual verification: 构造 standard_auto 全绿 checkpoint fixture 与 heavy 拒绝 fixture，各跑一次 gate CLI 确认 decision 与错误信息。

## Rollback Plan

回滚删除两个 checks 文件中的 tier 授权校验分支与 SKILL.md 的分级段落即可；新字段全部可选、未写入任何持久状态，未声明 tier 授权的 checkpoint/evidence 在回滚前后行为一致，无数据迁移。
