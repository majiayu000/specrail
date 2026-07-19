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
- goal 激活期间 compaction 不再中断 drain run：goal 跨 session 持久，每次
  compaction 后从 checkpoint + fresh remote truth 重锚，继续排干队列。
- 运行终点收敛为四类：队列排空或全阻塞（goal complete）、goal token 预算
  耗尽、用户打断、真人类决策（汇总在 `human_decisions`）。
- goal 不可用或 review 模式时，行为与 GH100 之后完全一致。

## 契约演进说明

本 spec 最初（PR #107 时期）把 goal 激活期间的 compaction 定义为"不触发
fresh-session handoff"。GH112 重设计将其收紧为 goal/session 解耦：goal 从不
豁免 session/tranche 的 compaction 预算，跨 session 持久的是 goal（稳定
`goal_id`），session 本身仍按预算交接。下述不变式描述收紧后的现行契约
（`skills/specrail-implement-queue/SKILL.md` Goal Use 与 Bounded Tranche
Hard Stop 小节为权威文本）。

## 非目标

- 不修改 `checks/` gate 代码语义；checkpoint `goal` 对象沿用现有模板 schema。
- 不放宽 reviewer-lane、self-review、ledger gate、review 模式人工授权。
- 无 goal 时的 compaction 语义原样保留（`compaction_budget`、
  `budget_overrides` 规则不变）。
- 不在 review 模式或 bounded_tranche 下自动建 goal。

## Behavior Invariants

1. B-001 当且仅当 `auth_mode: auto`、`queue_mode: full_queue_drain`、当前
   运行时暴露 Codex goal 能力三者同时成立时，启动即默认创建 thread goal；
   任一不成立则不建 goal，维持既有行为并按现有规则记录 `goal_candidate`。
2. B-002 当建 goal 时，必须设置 token 预算（用户给出预算时用用户值；未给出
   时使用一个明确记录进 checkpoint 的保守默认值），并把 objective、budget、
   status 写入 checkpoint `goal` 对象。goal objective 必须描述整个 drain
   目标、四类终止条件与"每 turn 从 runtime checkpoint + fresh remote truth
   重锚"的指令，不得只覆盖当前 tranche。
3. B-003 goal/session 解耦：goal 从不豁免任何 session/tranche 的 compaction
   预算。当 session 达到 `compaction_budget` 时，无论 goal 是否激活都必须
   结束该 tranche：写 checkpoint（递增 `tranche_id`，记录
   `tranche_started_at` 与 `tranche_session_offset`）、交接报告首行为可粘贴
   `resume_prompt`、交接到 fresh session。goal 激活时第二次 compaction 的
   gate 结果与无 goal 时完全一致（blocked，除非逐维度 override 记录授权）。
4. B-004 "compaction 不中断 run"仅指 drain objective 层面：goal 跨 session
   持久（checkpoint 记录稳定 `goal_id`；新 session 在同一 `goal_id` 下从
   checkpoint + fresh remote truth 恢复；新 tranche 观测计数从零开始，历史
   tranche 记录 append-only 不得改写）；不得依赖压缩 summary 里的队列记忆。
5. B-005 当任意 compaction 发生后，第一动作必须是 compaction discipline
   五步（只读 telemetry collector → 回写 `observed_compaction_count` /
   `telemetry_source` / `last_compaction_window_id` → 重读 runtime
   checkpoint → 刷新 remote truth → 跑 ledger gate 并服从其决定），此后
   才可继续其他队列工作。
6. B-006 goal 激活期间 tranche 记账不变：每个 tranche 仍声明 budget、写
   checkpoint、跑 ledger gate；当 item_cap 耗尽、compaction 未超限且
   context 低于 soft-stop 时，走 Same-Session Tranche Rollover 在同 session
   继续。
7. B-007 当运行终止时必须收敛为四类终态：队列排空或仅剩 `human_decisions`
   时标记 goal complete 并输出最终报告；goal token 预算耗尽时停止、写
   checkpoint 并交接（交接报告首行仍为可粘贴 `resume_prompt`）；用户打断
   遵循 Codex 原生行为。禁止在队列未排空时把 goal 标成 complete；goal
   状态永不替代 runtime checkpoint。
8. B-008 goal 不弱化任何 gate：reviewer-lane、self-review 授权、ledger
   gate、spec 覆盖、merge 证据要求在 goal 激活期间逐字适用。
9. B-009 当 goal 不可用、review 模式、或 bounded_tranche 时：不建 goal，
   compaction 仍按既有规则触发交接，行为零回归。
10. B-010 当需要观测 session 状态时，唯一允许的 session-jsonl 访问是只读
    telemetry collector（返回事件计数、不返回内容）；禁止读取原始
    `~/.codex/sessions` 日志、旧 parent transcript 或广义 session JSONL
    作为队列状态。

## Acceptance Criteria

- [ ] auto + full_queue_drain + goal 能力可用 → 默认建 goal，带 token 预算，
      记入 checkpoint `goal` 对象
- [ ] goal 跨 session 持久（稳定 `goal_id`），compaction 预算不被 goal 豁免
- [ ] 压缩后 compaction discipline 五步先于任何队列工作
- [ ] 四类终态收敛成文；禁止未排空标 complete
- [ ] review 模式 / bounded_tranche / goal 不可用路径零回归
- [ ] skills-lock hash 与改动文件一致

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 B-002（goal 能力缺失时不建 goal 只记 candidate；用户未给预算时用记录在案的保守默认值，不留空） |
| Error / failure paths | covered: B-003 B-005（compaction 超限 gate 判 blocked；压缩后必须走 discipline 五步并服从 ledger gate 决定） |
| Authorization / permission | covered: B-003 B-008（超预算续跑需逐维度显式用户 override；goal 不弱化任何授权 gate） |
| Concurrency / race | N/A: 单 coordinator 串行推进 tranche；lane 并行归 queue skill 既有 ownership 规则，goal 不引入新共享可变状态 |
| Retry / idempotency | covered: B-004 B-006（新 session 从 checkpoint + fresh remote truth 幂等恢复；rollover 关闭旧预算开新预算而非复用） |
| Illegal state transitions | covered: B-007（队列未排空时标 goal complete 是被禁止的非法转移；goal 状态不得替代 checkpoint） |
| Compatibility / migration | covered: B-009（无 goal / review / bounded_tranche 路径行为零回归；checkpoint schema 沿用现有模板） |
| Degradation / fallback | covered: B-005 B-010（`telemetry_source: unavailable` 时禁用 compaction basis、降级为 item_cap/runtime_dims，显式记录而非静默） |
| Evidence / audit integrity | covered: B-004 B-005（历史 tranche 记录 append-only；observed 计数由只读 telemetry 收集器回写，禁读原始 session 日志） |
| Cancellation / interruption | covered: B-007（用户打断走 Codex 原生行为并列为四类终态之一；交接报告首行 resume_prompt 保证可恢复） |

## Rollout Notes

先合 queue skill 的 Goal Use / Hard Stop 条文，再改 implx 入口与 checkpoint
模板注释，最后刷新 skills-lock。合并后三台机器重装 skills；首次 goal-wired
auto run 建议给出显式 token 预算并观察 goal 终态与 checkpoint 一致性。
