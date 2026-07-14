# Tech Spec

## Linked Issue

GH-100

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Bounded Tranche Hard Stop | `skills/specrail-implement-queue/SKILL.md` | 任何 budget exhaustion 都写 checkpoint 并 hand off to a fresh session | rollover 规则的落点 |
| item_cap 声明 | `skills/specrail-implement-queue/SKILL.md`、`templates/tranche_checkpoint.md` | `basis`/`item_cap` 由 session 自行声明，无默认值指导 | 实测 agent 声明 `item_cap: 1` 造成过度暂停 |
| Reviewer Lane Failures | `skills/specrail-implement-queue/SKILL.md` | 定义失败种类与恢复路径，但无等待上限 | 挂死 lane 被反复 wait |
| auto 模式入口 | `skills/implx/SKILL.md` | auto bullet list 描述 standing merge authorization 与跳过规则 | 需要声明"无退化信号不暂停" |
| Budget 校验 | `checks/runtime_gate_rules.py:193` | 校验 basis/compaction/item_cap 类型与 compaction 超限，需 `budget_override`；不校验 item 数与 session 边界 | 证明 rollover 与现有 gate 兼容，无需改 checks |
| Skill hash lock | `skills-lock.json` | 记录每个 SKILL.md 的 sha256 | SKILL.md 变更后必须刷新 |

## 设计方案

### 1. Same-Session Tranche Rollover（`specrail-implement-queue/SKILL.md`）

在 Bounded Tranche Hard Stop 小节内，把"budget exhaustion → 一律 fresh-session
handoff"改为两分支：

- rollover 分支（B-001 条件全部成立）：以 `stop_reason: budget_exhausted` 关闭
  当前 tranche checkpoint，随后在同一 session 声明新 `tranche_id` 与全新
  budget，继续选择下一 tranche。明确这不是 `budget_override`（B-002）。
- handoff 分支（其余情况）：保持现行为；交接报告首行为可粘贴的
  `resume_prompt`（B-007）。

### 2. item_cap 默认值（同文件 + `templates/tranche_checkpoint.md` 注释）

auto 模式声明 `item_cap` 时默认 3；`item_cap: 1` 必须附
`item_cap_reason`（B-004）。compaction 可观测时仍优先 `basis: compaction`。

### 3. Lane 等待上限（同文件 Reviewer Lane Failures 小节）

新增等待协议：spawn 后最多一次有界等待，再一次显式 stop-and-return 请求；
仍无输出即记录 `failure_kind: zero_output` 并走既有恢复路径（换独立 lane，
重试一次）。禁止对同一 lane 追加等待轮（B-006）。

### 4. implx auto 入口声明（`skills/implx/SKILL.md`）

auto 模式 bullet list 增加一条：预算耗尽且无退化信号时按 queue skill 的
Same-Session Tranche Rollover 继续，不暂停；仅在 compaction 超限、上下文
soft stop、用户打断或队列排空/全阻塞时交接（B-003）。

### 5. 锁文件

刷新 `skills-lock.json` 中两个改动 SKILL.md 的 `computedHash`。

## 风险与兼容

- `runtime_gate_rules._validate_budget` 只校验单个 checkpoint 的 budget 结构与
  compaction 超限；rollover 产生的是"新 tranche + 新 budget"的合法 checkpoint，
  不触发 override 路径，无 checks 改动（非目标）。
- review 模式路径不在修改的条件分支内（B-005）。
- 文档型变更，无运行时代码；验证以 pack 校验 + 全量 pytest + hash 一致性为准。
