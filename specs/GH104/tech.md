# Tech Spec

## Linked Issue

GH-104

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Goal Use | `skills/specrail-implement-queue/SKILL.md` | 默认不建 goal，只记录 `goal_candidate` | 自动建 goal 的落点 |
| Bounded Tranche Hard Stop | `skills/specrail-implement-queue/SKILL.md` | GH100 后：item_cap 可 rollover，compaction 超限仍强制 handoff | goal 激活分支需豁免 compaction 触发器 |
| implx auto 入口 | `skills/implx/SKILL.md` | auto bullet 声明 rollover 与四个交接条件 | 需声明 goal 默认开启与新终止条件 |
| Checkpoint 模板 | `templates/tranche_checkpoint.md` | `goal` 对象已存在（enabled/objective/status/tokens_used/token_budget） | 只需填写指导，无 schema 改动 |
| Budget 校验 | `checks/runtime_gate_rules.py:193` | 校验 budget 结构与 compaction 超限（需 override） | goal-active 时 compaction_count 不超限即不触发；不改代码 |
| Codex Goal 上游 | `codex-rs/ext/goal/`（外部参考） | objective 库外持久；`continue_if_idle()` 自动续 turn；continuation 模板强制 work-from-evidence | 行为契约的事实基础 |

## 设计方案

### 1. Goal Use 改写（`specrail-implement-queue/SKILL.md`）

把"仅显式请求才建 goal"改为两分支：

- auto drain 分支（B-001）：`auth_mode: auto` + `full_queue_drain` + goal 能力
  可用 → 启动时建 thread goal。objective 必须包含：整体 drain 目标、四类终止
  条件、"每 turn 从 checkpoint + fresh remote truth 重锚"指令。token 预算：
  用户给出则用之；否则用保守默认并记入 checkpoint（B-002）。
- 其余情况：保持现行为（记录 `goal_candidate`，不建 goal）（B-006）。

保留"Goal never replaces the runtime checkpoint, GitHub truth, or SpecRail
gates"原句（B-007）。

### 2. Compaction 豁免（同文件 Bounded Tranche Hard Stop / Context Budget）

goal 激活期间：compaction 观测仍记录 `compaction_count`，但不作为 handoff
触发器；压缩后的下一 turn 先重读 checkpoint、刷新远端队列，再继续（B-003）。
无 goal 时规则原样（B-006）。tranche 记账与 ledger gate 不变（B-004）。

### 3. 终态协议（同文件 Goal Use）

- 队列排空或仅剩 `human_decisions` → goal complete + 最终报告（B-005）。
- token 预算耗尽 → 停止并交接，首行 `resume_prompt`。
- 明确禁止：队列未排空时标 complete；用 goal 状态替代 checkpoint。

### 4. implx auto 入口（`skills/implx/SKILL.md`）

auto bullet list 增加：goal 能力可用时按 queue skill 的 Goal Use auto drain
分支建 goal；compaction 不再中断 run；终止条件四类。

### 5. 模板注释与锁文件

`templates/tranche_checkpoint.md` goal 对象上方加一行注释说明 auto drain 默认
启用条件；刷新 `skills-lock.json` 两个 SKILL.md 的 hash。

## 风险与兼容

- `runtime_gate_rules._validate_budget` 只在 `compaction_count >
  compaction_budget` 时要求 override；goal-active 运行照常记录计数，若单
  tranche 内压缩确实超过声明预算，仍需按现有规则处理——设计上 goal-active
  的 tranche 应声明与实际匹配的 `compaction_budget`（如提高到实际观测值并在
  checkpoint 记录理由），不绕过 gate。
- review 模式与 bounded_tranche 路径不进入新分支（B-006）。
- 纯 skill/模板文本变更，无运行时代码；验证以 pack 校验 + 全量 pytest + hash
  一致性为准。
