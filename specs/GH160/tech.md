# Tech Spec

## 关联 Issue

GH-160

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":160,"complete":true,"paths":["checks/session_telemetry.py","checks/runtime_context_budget.py","checks/runtime_ledger_gate.py","schemas/runtime_checkpoint.schema.json","tests/test_session_telemetry.py","tests/test_runtime_context_budget.py","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement-queue/references/context-budget.md","skills-lock.json","templates/tranche_checkpoint.md","templates/zh-CN/tranche_checkpoint.md"],"spec_refs":["specs/GH160/product.md","specs/GH160/tech.md","specs/GH160/tasks.md"]}
-->

## Product Spec

`specs/GH160/product.md`

## Codebase Context

| 区域 | 文件 | 当前行为 | 关联原因 |
| --- | --- | --- | --- |
| Session telemetry | `checks/session_telemetry.py:61`, `:113`, `:165` | 识别 compaction/tool event 并按显式 tranche window 输出计数；不处理 `token_count` | B-001..B-003 B-009 扩展唯一 read-only adapter |
| Runtime ledger | `checks/runtime_ledger_gate.py:500` | 751 行；只检查 window 为正数和三档 ratio 有序 | B-004..B-008 需要确定性 watermark/handoff gate；新逻辑进入 helper，避免主文件越过 800 行 |
| Runtime v3 rules | `checks/runtime_gate_rules.py:486` | 753 行；校验 `tranche_session_offset` 等 v3 结构 | GH-160 不在此继续堆叠规则，防止第二个近上限文件增长 |
| Checkpoint schema | `schemas/runtime_checkpoint.schema.json:334` | `context_budget` 只要求 window 与 thresholds，并允许附加字段 | 新 observation/convergence 需要机器可读 shape，旧 checkpoint 保持兼容 |
| Queue protocol | `skills/specrail-implement-queue/SKILL.md:321` | 876 行；watermark 仍是 prose，且已超过 U-16 硬上限 | B-005 B-008 B-010 需要抽取 reference 并缩短主 skill |
| Checkpoint templates | `templates/tranche_checkpoint.md:76`, `templates/zh-CN/tranche_checkpoint.md:65` | 没有真实 context observation 与 handoff evidence | operator 需要可复制字段 |
| Tests | `tests/test_session_telemetry.py`, `tests/test_runtime_ledger_gate.py` | 覆盖 GH-137，但不覆盖 context watermark | 新建 focused gate test，保留既有 regressions |

## 设计方案

### 1. Token telemetry extraction

在 `checks/session_telemetry.py` 增加小型 `token_count` parser。合法 observation 只能来自：

- event type 为 `token_count`（payload 或 top-level shape）；
- `info.last_token_usage.input_tokens` 为当前 context；
- `info.model_context_window` 为 runtime 分母。

parser 只接受非 boolean、非负整数 token 与正整数 window，且
`input_tokens <= model_context_window`；超出 runtime window 的 observation 必须跳过并计入
`invalid_context_observation_count`。parser 忽略累计 `info.total_token_usage`。在
`tranche_start_offset` 后聚合：

```text
observed_context_tokens              # latest
max_observed_context_tokens
observed_context_tokens_p50          # sorted[(n - 1) // 2]
context_observation_count
invalid_context_observation_count
observed_model_context_window
context_window_conflict
context_observed_at
```

无有效 observation 时省略 latest/max/p50/window/timestamp，只保留有效计数 0 与无效
计数。若有效 event 出现多个不同 `model_context_window`，设置
`context_window_conflict: true`，不产出可信 ratio；gate 必须阻断，而不是选择任一分母。
collector 只返回数值、boolean 与 provenance，不返回 raw event。

### 2. Context-budget gate helper

新增 `checks/runtime_context_budget.py`，由 `runtime_ledger_gate.py` 的既有
`context_budget` validation point 调用。对未声明任何新 observation 字段的 legacy
checkpoint 直接返回，保持 B-007。

只要声明任一新字段，就要求完整且一致的 evidence：

```text
observation_source: runtime | session_log
observed_context_tokens: non-negative integer
max_observed_context_tokens: non-negative integer >= latest
observed_context_tokens_p50: non-negative integer <= maximum
context_observation_count: positive integer
invalid_context_observation_count: non-negative integer
observed_model_context_window: positive integer == window_tokens
context_window_conflict: false
observed_context_ratio: number
max_observed_context_ratio: number
context_observed_at: timezone-aware ISO8601
```

gate 先验证 `observed_model_context_window == window_tokens`，再用 runtime window 重算
latest/max ratio，并拒绝超出小浮点 tolerance 的自报值。

当 latest 或 maximum ratio 达到 soft stop 时，唯一合法 action 是：

```json
{
  "action": "handoff",
  "recorded_at": "ISO8601",
  "trigger_observed_context_tokens": 150000,
  "next_action": "non-empty fresh-session resume instruction",
  "critical_only_checkpoint_and_resume": false
}
```

顶层 status 必须为 `handoff`，trigger 必须等于 maximum。`end_tranche`、`complete`、
`blocked` 不能满足 soft stop。达到 critical stop 时
`critical_only_checkpoint_and_resume` 必须为 true。所有违反项都是 errors，且不受无关
budget override 影响。

### 3. Schema、templates 与 queue skill

在 schema 与两份 template 中加入上述可选 typed fields；legacy checkpoint 仍合法，
partial declaration fail closed。

搜索确认当前 `skills/specrail-implement-queue/` 没有 reference 文件。实施时新增
`skills/specrail-implement-queue/references/context-budget.md`，把现有 Context Budget、
Bounded Tranche 与 fresh-session convergence 的详细协议迁入该文件；主 `SKILL.md` 只保留
触发条件、四步顺序和 reference 路由。验收要求：

- 主 `SKILL.md` 保留所有非 context-budget 契约；
- 新 reference 自包含字段表、soft/hard/critical 行为和 resume contract；
- 主文件 `wc -l` 必须 ≤800；
- 该局部抽取不替代 #174 的全面 context/read-frequency 优化。

修改 skill 后用仓库确定性 helper 重建 `skills-lock.json`。

### 4. Post-rollout closure

Spec PR 与 implementation PR 都使用 `Refs #160`。implementation merge gate 只验证
B-001..B-011 的确定性证据，不关闭 issue。合并后由 coordinator/operator 运行一个命名
bounded drain，附加以下证据到 GH-160：

- 样本窗口、tranche/PR 数；
- context p50 与 `<130K` 比较；
- token/PR 与基线比较；
- collector/runtime 版本和失败样本说明。

只有该证据存在且可复核时，才允许声称 B-012 达成并关闭 issue；否则明确保持
`rollout evidence pending`。

## Product-to-Test Mapping

| Invariant | 实现区域 | Verification |
| --- | --- | --- |
| B-001 | token-count parser | `test_collect_uses_last_token_usage_for_context` |
| B-002 | telemetry aggregation | latest/max/lower-median/offset tests |
| B-003 | telemetry validation | invalid count、omission、boolean/negative、input-over-window tests |
| B-004 | `runtime_context_budget.validate_context_budget` | denominator equality、window conflict、ratio mismatch tests |
| B-005 B-006 | soft-stop handoff | status/action/high-watermark tests；显式拒绝 `end_tranche` |
| B-007 | compatibility | legacy checkpoint unchanged + full suite |
| B-008 | hard/critical branches | handoff + critical-only tests |
| B-009 | collector purity | read-only、no-network、no raw event assertions |
| B-010 | queue skill/reference/templates | workflow checks + text/schema assertions |
| B-011 | GH-137 regression | telemetry/runtime-ledger existing suites |
| B-012 | rollout task | unit p50 + issue 上真实 bounded drain evidence |

## 数据流

```text
explicit session JSONL path + tranche offset
  -> session_telemetry numeric summaries + runtime window
  -> context_budget checkpoint fields
  -> runtime_context_budget denominator/ratio/convergence checks
  -> runtime_ledger_gate allowed | blocked
  -> soft-stop handoff checkpoint + fresh-session resume
```

gate 不做文件发现、网络调用或 checkpoint mutation。

## 备选方案

- 使用累计 `total_token_usage`：拒绝；它表示 lifetime spend，不是 per-turn context。
- 只更新 SKILL prose：拒绝；生产审计已证明 prose watermark 未执行。
- 新建平行 context gate：拒绝；违反 issue scope 与 W-17。
- 信任 checkpoint 手填 `window_tokens`：拒绝；可错误降低 ratio 并绕过 soft stop。
- 保留 `end_tranche`：拒绝；同一高 context session 可重开 tranche 继续。
- 在现有 876 行 skill 内继续追加：拒绝；违反 U-16 硬上限。

## 风险

- Security：collector 读取显式本地 session 文件但只输出 aggregate；raw content 不得进入
  checkpoint、artifact 或日志。
- Compatibility：新字段可选；一旦出现就要求完整。legacy checkpoint 维持原判定。
- Runtime drift：未知/malformed event 计入 invalid count；window conflict fail closed。
- Performance：聚合对已限定 tranche window 为线性，输出常数大小。
- Maintenance：gate 规则进入 focused helper；skill 细节进入 reference，避免两个近上限
  Python 文件和主 skill 继续膨胀。

## 验证计划

- [ ] Unit：token observation parsing、invalid count、aggregation、lower median、offset。
- [ ] Unit：denominator equality、window conflict、soft/hard/critical handoff 与 legacy。
- [ ] Schema/workflow：`python3 checks/check_workflow.py --repo . --all-specs`。
- [ ] Spec depth：`python3 tools/spec_depth_audit.py --spec-dir specs/GH160 --gate`。
- [ ] Full regression：`python3 -m pytest -q`。
- [ ] File ceiling：`wc -l skills/specrail-implement-queue/SKILL.md | awk '$1 <= 800 {ok=1} END {exit !ok}'`。
- [ ] Operational rollout：merge 后真实 bounded drain；本地 fixture 不得代替。

## 回滚方案

一起回滚 helper import/call、collector aggregation、schema/template fields 与 queue reference
路由。既有 checkpoint version 与 GH-137 budget fields 无数据迁移，始终保持可读。
