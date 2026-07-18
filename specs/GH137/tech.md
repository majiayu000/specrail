# Tech Spec

## Linked Issue

GH-137

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":137,"complete":true,"paths":["checks/session_telemetry.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","schemas/runtime_checkpoint.schema.json","skills/specrail-implement-queue/SKILL.md","examples/fixtures/runtime-telemetry-mismatch-blocked.json","examples/fixtures/runtime-telemetry-unavailable-compaction-basis.json","examples/fixtures/runtime-goal-active-second-compaction.json","examples/fixtures/runtime-wall-clock-exceeded-blocked.json","examples/fixtures/runtime-tool-calls-exceeded-blocked.json","examples/fixtures/runtime-review-rounds-exceeded-blocked.json","examples/fixtures/runtime-full-test-runs-exceeded-blocked.json","examples/fixtures/runtime-override-per-dimension.json","examples/fixtures/runtime-new-tranche-reset.json","tests/test_session_telemetry.py","tests/test_runtime_ledger_gate.py"],"spec_refs":["specs/GH137/product.md","specs/GH137/tech.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 预算 basis 定义 | `checks/runtime_gate_rules.py:21` | `BUDGET_BASES = {"compaction", "item_cap", "both"}` | B-002 需在 basis 校验处拒绝 unavailable + compaction |
| budget 缺失早退 | `checks/runtime_gate_rules.py:257` | `budget is None` 时仅当 `checkpoint_version == 2` 且 `queue_mode == "full_queue_drain"` 才报错，其余直接 return | v3 full_queue_drain 若不扩展此处，可整体省略 budget 绕过全部默认硬预算 |
| 自报计数解析 | `checks/runtime_gate_rules.py:283` | `compaction_count` 仅做非负整数校验，来源是 checkpoint 自报 | B-001 的 max(observed, self_reported) 在此扩展 |
| 预算比较与 override | `checks/runtime_gate_rules.py:319` | `compaction_count > compaction_budget` 时无 override 即报错 | 新维度超限复用同一 blocked/override 分支结构（B-005/B-007） |
| context budget 形式校验 | `checks/runtime_ledger_gate.py:431` | 仅校验 `0 < soft < hard < critical < 1` | 事故证明纯 schema 校验无控制作用；gate 输出需带 telemetry 不一致审计信息 |
| ledger gate 字段清单 | `checks/runtime_ledger_gate.py:400` | `context_budget` 在必填键列表中 | version 3 新增 telemetry/goal 字段的接入点 |
| version 门禁 | `checks/runtime_ledger_gate.py:70`、`schemas/runtime_checkpoint.schema.json` | `CHECKPOINT_VERSIONS = {1, 2}`；schema `checkpoint_version` 枚举 `[1, 2]`；schema `budget.basis` 枚举 `["compaction", "item_cap", "both"]`；顶层 `tranche_id` 必填 | version 3 必须先在版本枚举与 `budget.basis` 枚举两处放开，否则 v3 checkpoint 在进入新校验前即被拒绝 |
| compaction 默认预算 | `skills/specrail-implement-queue/SKILL.md:334` | `compaction_budget` default 1: stop before the second compaction | 与 goal-active 豁免冲突的一侧 |
| goal-active 豁免 | `skills/specrail-implement-queue/SKILL.md:358` | goal active 时 observed compaction 不是 handoff trigger | B-004 要求整段删除并替换为 goal/session 解耦语义 |
| 现有 ledger 测试 | `tests/test_runtime_ledger_gate.py:1` | 基于 fixture 的 blocked/allowed 断言风格 | 新增 B-001…B-010 回归用例沿用同一风格 |

## Proposed Design

### 1. Telemetry 采集器（新文件 `checks/session_telemetry.py`）

- `collect(session_path: Path, tranche_start_offset: int = 0) -> Telemetry`：
  从 `tranche_start_offset`（0-based 行号，tranche 开始时记录）起逐行解析
  jsonl，统计 `payload.type == "context_compacted"`（兼容顶层
  `type: compacted`）事件数，返回 `{observed_compaction_count,
  telemetry_source, last_compaction_window_id, tranche_window: {start_line,
  end_line}, collected_at}`。
- 统计按 tranche 窗口而非整个 session：同 session rollover 开新 tranche 时，
  新 tranche 在 checkpoint 记录 `tranche_session_offset`（新 tranche 起始时
  session jsonl 的行数），采集器只统计该 offset 之后的事件。这样 B-010 的
  per-tranche 计数清零可审计：上一 tranche 的 compaction 不会污染新 tranche
  的 `observed_compaction_count`，且窗口边界（start_line/end_line）随
  telemetry 一起输出供 gate 打印。
- 同一窗口内同时统计 `observed_tool_calls`（tool-call 事件行数）并由窗口内
  首末事件时间戳推导 `observed_wall_clock_minutes`（见 §2 可信来源）。
- 文件缺失/不可读 → `telemetry_source: "unavailable"`，无计数字段（B-003）。
- 损坏行跳过；全部行不可解析视为不可读。
- 纯只读，无网络（B-009）。CLI 入口
  `python -m checks.session_telemetry <path> [--tranche-start-offset N]`
  输出 JSON，供 agent 在更新 checkpoint 前调用。

### 2. checkpoint_version 3 schema（版本门禁 + `checks/runtime_gate_rules.py`）

- 版本门禁先行放开：`checks/runtime_ledger_gate.py:70` 的
  `CHECKPOINT_VERSIONS = {1, 2}` 扩展为 `{1, 2, 3}`；
  `schemas/runtime_checkpoint.schema.json` 的 `checkpoint_version` 枚举
  `[1, 2]` 扩展为 `[1, 2, 3]`；同一 schema 中 `budget.basis` 的枚举
  `["compaction", "item_cap", "both"]` 也必须扩展为含 `"runtime_dims"`，并用
  `if/then`（`checkpoint_version: 3` 条件）限制 `runtime_dims` 仅 v3 合法，
  version 2 分支保持原三值枚举。不同时改这三处门禁，任何 v3 checkpoint 或
  `basis: runtime_dims` 形态在进入新校验前即被 schema 消费方拒绝。
- budget 存在性检查扩展：`checks/runtime_gate_rules.py:257` 的
  `budget is None` 早退分支目前仅在 `checkpoint_version == 2` 且
  `queue_mode == "full_queue_drain"` 时报错，必须扩展为
  `checkpoint_version in {2, 3}`，使 v3 full_queue_drain checkpoint 省略
  `budget` 时同样 fail closed，而非绕过全部默认硬预算。
- budget 对象新增：`observed_compaction_count`、`telemetry_source`
  （`runtime` | `session_log` | `unavailable`）、
  `last_compaction_window_id`（字符串，可选）。
- `basis` 枚举扩展 `runtime_dims`（仅 version 3 接受，version 2 仍限
  `{compaction, item_cap, both}`）：不依赖 compaction 计数与 item_cap，仅按
  四个硬预算维度判定，是 `telemetry_source: unavailable` 时的合法降级
  checkpoint 形态（B-002）。
- version 3 且 `basis ∈ {compaction, both}` 时：`telemetry_source` 必填；为
  `unavailable` 时校验失败，错误信息给出降级指引（改用 `item_cap` 或
  `runtime_dims`）（B-002）。
- version 3 必填观测字段（一律非负整数，缺失或非法即校验失败，不得默认 0）：
  `observed_compaction_count`（`telemetry_source: unavailable` 时允许缺省——
  此时 basis 已被 B-002 限制为 `item_cap` 或 `runtime_dims`，采集器无法产出
  计数，不得伪造；其余必填）、`observed_wall_clock_minutes`、
  `observed_tool_calls`、`observed_review_correction_rounds`、
  `observed_full_test_runs_current_head`。
  否则默认上限没有比较对象，unbounded-run 会绕过默认硬预算。
- 预算判定改为 `effective = max(observed_compaction_count, compaction_count)`；
  `effective > compaction_budget` 走 override/blocked 分支（B-001/B-007）。
  observed 与自报不一致时追加 warning，包含双方数值与 source（审计边界）。
- 新增声明维度：`max_wall_clock_minutes`/`max_tool_calls`/
  `max_review_correction_rounds`/`max_full_test_runs_per_head`。
  声明值缺省用默认（120/250/2/1），显式声明必须为正整数（B-006）；
  `observed > limit` → blocked，错误信息含维度名与数值（B-005）。
- 四维观测值的可信来源（防止 telemetry 断供时退化为纯自报）：
  - `observed_wall_clock_minutes`：version 3 新增必填 `tranche_started_at`
    （ISO8601，tranche 开始时写入，历史 tranche 记录 append-only 不可改）。
    gate 以 `gate 运行时刻 − tranche_started_at` 独立重算 wall-clock，
    取 `max(重算值, 自报值)` 判定；该来源不依赖 session jsonl，telemetry
    断供时依然有效。
  - `observed_tool_calls`：telemetry 可用时由采集器在 tranche 窗口内统计
    tool-call 事件行数，gate 取 `max(采集值, 自报值)`。
  - `observed_review_correction_rounds` / `observed_full_test_runs_current_head`：
    每轮 correction / 每次 full-test 追加一条历史 tranche 记录
    （append-only），gate 以历史记录条数与自报值取 max 判定。
  - telemetry 不可用且无独立来源的维度，gate 输出中必须标注
    `provenance: self_reported` warning，使降级运行的审计痕迹显式存在，
    而非静默等同于可信观测。
- full-test 维度绑定 head：`full_test_head_sha`（非空字符串）与
  `observed_full_test_runs_current_head` 成对记录，但仅在
  `observed_full_test_runs_current_head > 0` 或当前 tranche 存在被检验的
  PR head 时必填；issue/spec-only tranche 无 PR head 时允许缺省该字段且
  计数必须为 0，不得为满足校验伪造 SHA。checkpoint 声明的 head 与当前
  PR head 不一致时，计数对新 head 重置为 0 并更新 `full_test_head_sha`，
  旧 head 的计数保留在历史 tranche 记录中不被覆盖（product.md B-005）。
- override 改为 per-dimension 多条结构：version 3 使用 `budget_overrides`
  （对象数组），每条含 `dimension`
  （`compaction` | `wall_clock` | `tool_calls` | `review_rounds` |
  `full_test_runs`）加既有 `budget_override` 的引用范围与会话标记字段。
  同一 checkpoint 两个维度同时超限时，每个维度各需一条独立记录，缺失其一
  即对该维度 blocked（B-007）。version 2 的单 `budget_override` 对象结构与
  校验路径不动（B-008）。
- 新增 `goal_id`（version 3 可选字符串）与 `tranche_session_offset`
  （version 3 非负整数，同 session rollover 时记录新 tranche 的 jsonl 起始
  行号，session 首个 tranche 为 0）。顶层 `tranche_id` 保持全版本必填
  （既有 schema/gate 契约不变，B-010 的 tranche 边界依赖它）；同一 `goal_id`
  下新 tranche 观测字段清零，telemetry 按 `tranche_session_offset` 窗口
  统计使清零可审计（B-010）。version 2 分支代码路径不动（B-008）。

### 3. SKILL.md 语义修订（`skills/specrail-implement-queue/SKILL.md`）

- 删除 goal-active compaction 豁免段（`SKILL.md:358` 起的整段）。
- 替换为解耦语义：goal 跨 session 持续（`goal_id` 不变）；session/tranche 达到
  compaction 预算必须结束，写 checkpoint（`tranche_id` 递增）+ resume_prompt 后
  fresh-session handoff；新 session 从 checkpoint + fresh remote truth 恢复。
- 在 Context Budget 小节补充：每次 compaction 后第一动作是运行 telemetry 采集器
  并回写 `observed_compaction_count`，然后才允许其他工具调用。

### 4. Fixtures 与 gate 输出

- 新增 fixtures（`examples/fixtures/`）：`runtime-telemetry-mismatch-blocked.json`
  （observed=2/自报=0/budget=1）、
  `runtime-telemetry-unavailable-compaction-basis.json`、
  `runtime-goal-active-second-compaction.json`，四个维度各一条超限 fixture：
  `runtime-wall-clock-exceeded-blocked.json`、
  `runtime-tool-calls-exceeded-blocked.json`、
  `runtime-review-rounds-exceeded-blocked.json`、
  `runtime-full-test-runs-exceeded-blocked.json`，以及
  `runtime-override-per-dimension.json`（双维度超限、仅一维有 override →
  另一维 blocked，B-007）与 `runtime-new-tranche-reset.json`（同 goal 新
  tranche 观测计数清零且历史记录保留，B-010）。
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
| B-010 | goal_id/tranche_id 语义 + tranche 窗口统计 | `test_new_tranche_resets_observed_counters` |

## Data Flow

```
Codex session jsonl ──(checks/session_telemetry.py 按 tranche 窗口只读扫描)──▶ Telemetry JSON
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
