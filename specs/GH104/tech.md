# Tech Spec

## Linked Issue

GH-104

## Product Spec

Link to `product.md`.

## Codebase Context

锚点按当前实现现场核实（2026-07-19，`origin/main` c0be38f）。

| Area | Anchor | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Goal Use 两分支 | `skills/specrail-implement-queue/SKILL.md:493`（auto drain 分支 `SKILL.md:497-506`，其余分支 `SKILL.md:507-509`） | auto+full_queue_drain+goal 能力 → 默认建 goal，objective 含整体目标/四类终止条件/重锚指令与 token 预算；其余记 `goal_candidate` | B-001 B-002 的权威条文 |
| Goal 终态协议 | `skills/specrail-implement-queue/SKILL.md:511-519` | 排空/仅剩 human_decisions → complete；预算耗尽 → checkpoint + resume_prompt 交接；打断走原生；goal 状态不替代 checkpoint | B-007 |
| Goal 不替代 gates | `skills/specrail-implement-queue/SKILL.md:521-523` | reviewer-lane、self-review、ledger、spec 覆盖、merge 证据逐字适用 | B-008 |
| Goal/session 解耦 | `skills/specrail-implement-queue/SKILL.md:366-378` | goal 从不豁免 compaction 预算；稳定 `goal_id` 跨 session；历史 tranche append-only；第二次 compaction gate 结果与无 goal 一致 | B-003 B-004（GH112 收紧后的现行契约） |
| Same-Session Rollover | `skills/specrail-implement-queue/SKILL.md:353-360` | item_cap 耗尽且 compaction 未超限、context 低于 soft stop → 同 session 开新 tranche | B-006 |
| checkpoint_version 3 | `skills/specrail-implement-queue/SKILL.md:380-397` | gate 比较 `max(observed_compaction_count, compaction_count)`；`telemetry_source: unavailable` 禁 compaction basis；四硬预算维度；逐维度 `budget_overrides` | B-003 B-005 |
| Compaction discipline | `skills/specrail-implement-queue/SKILL.md:399-412` | 压缩后五步先行；唯一 session-jsonl 访问是 `checks/session_telemetry.py` 只读收集器 | B-005 B-010 |
| implx auto 入口 | `skills/implx/SKILL.md:97-103` | auto bullet 声明 goal 默认开启、compaction 不中断 run（重锚语义）与四类终止条件 | B-001 B-007 入口条文 |
| Checkpoint 模板 | `templates/tranche_checkpoint.md:19-23`（`goal` 对象 `tranche_checkpoint.md:56-62`） | goal guidance 注释说明 auto-drain 默认建 goal 与预算记录要求 | B-002 |
| Budget 校验 | `checks/runtime_gate_rules.py:264`（`_validate_budget`） | 校验 budget 结构、basis、compaction 计数与 override 要求；goal 不引入分支 | B-003 B-006（零代码改动的边界） |

## 设计方案

### 1. Goal Use 两分支（`specrail-implement-queue/SKILL.md:493-523`）

- auto drain 分支（B-001）：`auth_mode: auto` + `full_queue_drain` + goal 能力
  可用 → 启动时建 thread goal。objective 必须包含：整体 drain 目标、四类终止
  条件、"每 turn 从 checkpoint + fresh remote truth 重锚"指令。token 预算：
  用户给出则用之；否则用保守默认并记入 checkpoint（B-002）。
- 其余情况：保持现行为（记录 `goal_candidate`，不建 goal）（B-009）。

保留 "Goal never replaces the runtime checkpoint, GitHub truth, or SpecRail
gates"原句（B-008，`SKILL.md:513`）。

### 2. Goal/session 解耦（同文件 `SKILL.md:358-370`，GH112 收紧）

goal 激活期间 compaction 预算照常生效：达到 `compaction_budget` 即结束
tranche 并交接 fresh session；goal 以稳定 `goal_id` 跨 session 持久，新
session 从 checkpoint + fresh remote truth 恢复（B-003 B-004）。压缩后先走
compaction discipline 五步（`SKILL.md:391-398`），再继续队列工作（B-005）。
无 goal 时规则原样（B-009）。tranche 记账与 ledger gate 不变（B-006）。

### 3. 终态协议（同文件 `SKILL.md:511-519`）

- 队列排空或仅剩 `human_decisions` → goal complete + 最终报告（B-007）。
- token 预算耗尽 → 停止并交接，首行 `resume_prompt`。
- 明确禁止：队列未排空时标 complete；用 goal 状态替代 checkpoint。

### 4. implx auto 入口（`skills/implx/SKILL.md:97-103`）

auto bullet list 声明：goal 能力可用时按 queue skill 的 Goal Use auto drain
分支建 goal；compaction 不中断 run（解耦语义下由跨 session 的 goal 承接）；
终止条件四类。

### 5. 模板注释与锁文件

`templates/tranche_checkpoint.md:19-23` goal guidance 注释说明 auto drain
默认启用条件；`skills-lock.json` 记录两个 SKILL.md 的 hash，改动后刷新。

## 风险与兼容

- `checks/runtime_gate_rules.py:264` `_validate_budget` 只在计数超过
  `compaction_budget` 时要求 override；goal-active 运行照常记录计数，超限
  仍按现有规则处理（逐维度 `budget_overrides`），不绕过 gate。
- review 模式与 bounded_tranche 路径不进入新分支（B-009）。
- 纯 skill/模板文本变更，无运行时代码；验证以 pack 校验 + 全量 pytest + hash
  一致性为准。
