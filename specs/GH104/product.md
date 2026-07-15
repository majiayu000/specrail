# Product Spec

## Linked Issue

GH-104

## 用户问题

GH100 修掉了 item_cap 造成的假性暂停，但 compaction 仍是停机信号：
`compaction_budget: 1` 一触发就强制 fresh-session handoff，而没有机制自动拉起
新 session，用户必须手动粘贴 `resume_prompt` 才能继续。implx 的初衷是解决
压缩问题，现状却把压缩变成了"每压缩一次就要人工插手一次"。

Codex 源码证实（`core/src/compact.rs`、`core/src/state/auto_compact_window.rs`）
compaction 本身不终止 session：历史被替换为 summary 并重注入 initial context，
压缩窗口带编号无限滚动。Goal 扩展（`ext/goal/`）正是官方的抗压缩机制：

- objective 存在会话历史之外的状态库，压缩吞不掉、改写不了；
- `continue_if_idle()` 在 thread 空闲且 goal Active 时自动发起新 turn，重注入
  完整 objective（continuation 模板），无需人工恢复；
- continuation 模板强制 "work from evidence"：以当前 worktree 与外部状态为
  权威，不信压缩后的记忆——与 implx 的 checkpoint + fresh remote truth 规则
  一致；
- token budget 在模型外记账；blocked 需连续 3 轮同一阻塞；完成前强制逐条
  证据审计。

当前 skill 的 Goal Use 一节默认"不主动建 goal"，加上 `compaction_budget: 1`，
把这条官方自动续命链路整个掐断。

## 目标

- `implx auto` + `full_queue_drain` 在 Codex goal 能力可用时，默认把 drain
  objective 建成 thread goal（带 token 预算护栏），记入 checkpoint `goal` 对象。
- goal 激活期间 compaction 不再是停机信号：每次压缩后从 checkpoint + fresh
  remote truth 重锚，继续排干队列。
- 运行终点收敛为四类：队列排空或全阻塞（goal complete）、goal token 预算
  耗尽、用户打断、真人类决策（汇总在 `human_decisions`）。
- goal 不可用或 review 模式时，行为与 GH100 之后完全一致。

## 非目标

- 不修改 `checks/` gate 代码；checkpoint `goal` 对象沿用现有模板 schema。
- 不放宽 reviewer-lane、self-review、ledger gate、review 模式人工授权。
- 无 goal 时的 compaction 语义原样保留（`compaction_budget`、`budget_override`
  规则不变）。
- 不在 review 模式或 bounded_tranche 下自动建 goal。

## Behavior Invariants

1. B-001 自动建 goal 仅当以下条件全部成立：`auth_mode: auto`、
   `queue_mode: full_queue_drain`、当前运行时暴露 Codex goal 能力。任一不成立
   则维持 GH100 行为，并按现有规则记录 `goal_candidate`。
2. B-002 建 goal 时必须设置 token 预算（用户给出预算时用用户值；未给出时
   使用一个明确记录进 checkpoint 的保守默认值），并把 objective、budget、
   status 写入 checkpoint `goal` 对象。goal objective 必须描述整个 drain 目标
   与终止条件，不得只覆盖当前 tranche。
3. B-003 goal 激活期间，观测到 compaction 不触发 fresh-session handoff：
   压缩后的下一个 goal turn 必须先从 runtime checkpoint 与 fresh remote truth
   重锚（重读 checkpoint、刷新远端队列状态），再继续执行；不得依赖压缩
   summary 里的队列记忆。
4. B-004 goal 激活期间 tranche 记账不变：每个 tranche 仍声明 budget、写
   checkpoint、跑 ledger gate；item_cap 耗尽走 GH100 的 Same-Session Tranche
   Rollover。区别仅在 compaction 不再是 handoff 触发器。
5. B-005 运行终止时必须调用 goal 终态：队列排空或仅剩 `human_decisions` 时
   标记 complete 并输出最终报告；token 预算耗尽时按 budget_limit 语义停止并
   交接（此时交接报告首行仍为可粘贴 `resume_prompt`）；用户打断遵循 Codex
   原生行为。禁止在队列未排空时把 goal 标成 complete。
6. B-006 goal 不可用、review 模式、或 bounded_tranche 时：不建 goal，
   compaction 仍按 GH100 规则触发交接，行为不回归。
7. B-007 goal 不弱化任何 gate：reviewer-lane、self-review 授权、ledger gate、
   spec 覆盖、merge 证据要求在 goal 激活期间逐字适用。
