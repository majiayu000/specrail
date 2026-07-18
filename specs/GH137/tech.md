# Tech Spec

## Linked Issue

GH-137

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 预算 basis 定义 | `checks/runtime_gate_rules.py:21` | `BUDGET_BASES = {"compaction", "item_cap", "both"}` | B-002 需在 basis 校验处拒绝 unavailable + compaction |
| 自报计数解析 | `checks/runtime_gate_rules.py:283` | `compaction_count` 仅做非负整数校验，来源是 checkpoint 自报 | B-001 的 max(observed, self_reported) 在此扩展 |
| 预算比较与 override | `checks/runtime_gate_rules.py:319` | `compaction_count > compaction_budget` 时无 override 即报错 | 新维度超限复用同一 blocked/override 分支结构（B-005/B-007） |
| context budget 形式校验 | `checks/runtime_ledger_gate.py:431` | 仅校验 `0 < soft < hard < critical < 1` | 事故证明纯 schema 校验无控制作用；gate 输出需带 telemetry 不一致审计信息 |
| ledger gate 字段清单 | `checks/runtime_ledger_gate.py:400` | `context_budget` 在必填键列表中 | version 3 新增 telemetry/goal 字段的接入点 |
| compaction 默认预算 | `skills/specrail-implement-queue/SKILL.md:334` | `compaction_budget` default 1: stop before the second compaction | 与 goal-active 豁免冲突的一侧 |
| goal-active 豁免 | `skills/specrail-implement-queue/SKILL.md:358` | goal active 时 observed compaction 不是 handoff trigger | B-004 要求整段删除并替换为 goal/session 解耦语义 |
| 现有 ledger 测试 | `tests/test_runtime_ledger_gate.py:1` | 基于 fixture 的 blocked/allowed 断言风格 | 新增 B-001…B-010 回归用例沿用同一风格 |

## Proposed Design

### 1. Telemetry 采集器（新文件 `checks/session_telemetry.py`）

- `collect(session_path: Path) -> Telemetry`：逐行解析 jsonl，统计
  `payload.type == "context_compacted"`（兼容顶层 `type: compacted`）事件数，
  返回 `{observed_compaction_count, telemetry_source, last_compaction_window_id,
  collected_at}`。
- 文件缺失/不可读 → `telemetry_source: "unavailable"`，无计数字段（B-003）。
- 损坏行跳过；全部行不可解析视为不可读。
- 纯只读，无网络（B-009）。CLI 入口 `python -m checks.session_telemetry <path>`
  输出 JSON，供 agent 在更新 checkpoint 前调用。

### 2. checkpoint_version 3 schema（`checks/runtime_gate_rules.py`）

- budget 对象新增：`observed_compaction_count`（非负整数，来源 telemetry）、
  `telemetry_source`（`runtime` | `session_log` | `unavailable`）、
  `last_compaction_window_id`（字符串，可选）。
- version 3 且 `basis ∈ {compaction, both}` 时：`telemetry_source` 必填；为
  `unavailable` 时校验失败，错误信息给出降级指引（B-002）。
- 预算判定改为 `effective = max(observed_compaction_count, compaction_count)`；
  `effective > compaction_budget` 走既有 override/blocked 分支（B-001/B-007）。
  observed 与自报不一致时追加 warning，包含双方数值与 source（审计边界）。
- 新增维度：`max_wall_clock_minutes`/`max_tool_calls`/
  `max_review_correction_rounds`/`max_full_test_runs_per_head` 及对应观测字段
  `observed_wall_clock_minutes`/`observed_tool_calls`/
  `observed_review_correction_rounds`/`observed_full_test_runs_current_head`。
  声明值缺省用默认（120/250/2/1），显式声明必须为正整数（B-006）；
  `observed > limit` → blocked，错误信息含维度名与数值（B-005）。override
  按维度独立记录，复用现有 `budget_override` 结构加 `dimension` 字段（B-007）。
- 新增 `goal_id`/`tranche_id`（version 3 可选，成对出现）；同一 goal 下新
  tranche 观测字段清零（B-010）。version 2 分支代码路径不动（B-008）。

### 3. SKILL.md 语义修订（`skills/specrail-implement-queue/SKILL.md`）

- 删除 goal-active compaction 豁免段（`SKILL.md:358` 起的整段）。
- 替换为解耦语义：goal 跨 session 持续（`goal_id` 不变）；session/tranche 达到
  compaction 预算必须结束，写 checkpoint（`tranche_id` 递增）+ resume_prompt 后
  fresh-session handoff；新 session 从 checkpoint + fresh remote truth 恢复。
- 在 Context Budget 小节补充：每次 compaction 后第一动作是运行 telemetry 采集器
  并回写 `observed_compaction_count`，然后才允许其他工具调用。

### 4. Fixtures 与 gate 输出

- 新增 fixtures：`runtime-telemetry-mismatch-blocked.json`（observed=2/自报=0/
  budget=1）、`runtime-telemetry-unavailable-compaction-basis.json`、
  `runtime-goal-active-second-compaction.json`、四个维度各一条超限 fixture。
- gate blocked 输出统一格式：`budget exceeded: <dimension> observed <n> >
  limit <m> (telemetry_source=<s>)`。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | max(observed, self_reported) 判定 | `test_blocked_when_runtime_observed_exceeds_budget_despite_low_self_report` |
| B-002 | basis 校验 unavailable 分支 | `test_compaction_basis_rejected_without_telemetry` |
| B-003 | `session_telemetry.collect` | `test_collect_counts_context_compacted_exactly` / `test_collect_missing_file_returns_unavailable` |
| B-004 | SKILL.md 修订 + gate 无豁免路径 | `test_goal_active_second_compaction_blocked` + `rg` 断言豁免文本不存在 |
| B-005 | 四维度超限分支 | `test_wall_clock_exceeded_blocked` 等四条 |
| B-006 | 声明值类型校验 | `test_invalid_dimension_limits_fail_validation` |
| B-007 | 按维度 override | `test_override_is_per_dimension` |
| B-008 | version 2 兼容路径 | 既有 `tests/test_runtime_ledger_gate.py` 全绿 + version 2 fixture 结果比对 |
| B-009 | 采集器/gate 只读 | `test_telemetry_collect_is_read_only`（采集前后文件 mtime/内容一致） |
| B-010 | goal_id/tranche_id 语义 | `test_new_tranche_resets_observed_counters` |

## Data Flow

```
Codex session jsonl ──(checks/session_telemetry.py 只读扫描)──▶ Telemetry JSON
Telemetry JSON ──(agent 回写)──▶ checkpoint budget(version 3)
checkpoint ──▶ runtime_gate_rules 校验 ──▶ runtime_ledger_gate 判定
                                  │
                                  └─ max(observed, self_reported) vs budget
                                     + 四维硬预算 → allowed / warning / blocked
```

无持久化副作用、无网络调用；telemetry 是单向只读输入。

## Alternatives Considered

- gate 直接扫 session 文件而不经 checkpoint：被否。gate 需保持纯函数式、可用
  fixture 测试；session 路径发现引入环境耦合。采集与判定分离后两者各自可测。
- 保留 goal-active 豁免但加 telemetry 校验：被否。豁免与 hard-stop 的语义冲突
  正是本次事故的授权来源，修补豁免仍留下双重解释空间。
- 用 token 计量替代 compaction 计数：被否。goal 工具契约禁止代理擅自设 token
  budget（GH-137 out of scope），且 token 遥测同样依赖自报；compaction 事件在
  session jsonl 中客观存在、可独立复核。
- 只加文字规则不改 gate：被否。13 小时事故中所有文字规则均未生效，提示性约束
  在长程执行中衰减为零。
