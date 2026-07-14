# Product Spec

## Linked Issue

GH-100

## 用户问题

`implx auto` + `queue_mode: full_queue_drain` 的承诺是"排干整个可执行队列"，
但实测（2026-07-10 ~ 07-14，litellm-rs 39 个 tranche checkpoint、vibeguard/remem
各 1 个）几乎每个 tranche 结束就暂停等待人工"继续"：

- Bounded Tranche Hard Stop 把"tranche 预算耗尽"与"session 交接"绑定，而没有
  任何机制自动拉起新 session，full_queue_drain 退化为"每 tranche 一次人工恢复"。
- skill 没有给 `item_cap` 默认值或下限指导，agent 实际声明了 `item_cap: 1`，
  在零 compaction、上下文健康时也整段停机（vibeguard
  `2026-07-14-vibeguard-gh588-t03`: `item_cap: 1, compaction_count: 0,
  stop_reason: budget_exhausted`）。
- Reviewer Lane Failures 协议没有 lane 等待上限：挂死 lane 被反复 wait（去重后
  7 个 `zero_output` 事件，marker 均为 "no output after repeated waits and
  explicit stop-and-return"），造成长时间假性暂停。

## 目标

- auto 模式 full_queue_drain 在"无退化信号"时不暂停：`item_cap` 耗尽且
  compaction 未超、上下文低于 soft stop 时，在同一 session 内滚动进入下一个
  tranche。
- 给 auto 模式的 `item_cap` 合理默认值（3）；`item_cap: 1` 需要记录高风险理由。
- lane 等待有硬上限：一次有界等待 + 一次显式 stop-and-return 后仍无输出即判
  `zero_output`，换一条独立 lane 重试一次，不再对挂死 lane 重复等待。
- 真正交接时，报告首行必须是可直接粘贴的 `resume_prompt`。

## 非目标

- 不改变 review 模式的 per-PR 人工合并授权与暂停行为。
- 不放宽 compaction 预算语义：compaction 超限仍必须交接，`budget_override`
  规则不变。
- 不修改 `checks/` gate 代码；同 session 新 tranche + 新 budget 的 checkpoint
  与现有 `runtime_ledger_gate` 兼容。
- 不削弱 reviewer-lane 独立性、self-review 授权或 ledger gate。

## Behavior Invariants

1. B-001 同 session tranche rollover 只在以下条件全部成立时发生：
   `auth_mode: auto`、`queue_mode: full_queue_drain`、耗尽的 basis 是
   `item_cap`、观测 `compaction_count` 未超 `compaction_budget`、父上下文低于
   soft-stop ratio。任一条件不满足则维持现有交接行为。
2. B-002 rollover 不是 `budget_override`：旧 tranche checkpoint 以
   `stop_reason: budget_exhausted` 正常关闭，新 tranche 声明新的 `tranche_id`
   与全新 budget；不需要也不得伪造用户 override。
3. B-003 compaction 超限、上下文到达 soft stop、用户打断、队列排空或全部阻塞时，
   仍按现有规则交接或终止；rollover 不得绕过这些终止条件。
4. B-004 auto 模式下声明 `item_cap` 时默认值为 3；声明 `item_cap: 1` 必须在
   checkpoint budget 中记录高风险理由（`item_cap_reason`）。
5. B-005 review 模式行为完全不变。
6. B-006 lane 等待上限：一次有界等待加一次显式 stop-and-return 请求后仍无输出，
   立即记录 `zero_output` lane failure 并按既有失败协议换独立 lane 重试一次；
   禁止对同一 lane 继续重复等待。
7. B-007 发生真实交接时，交接报告的第一行是完整可粘贴的 `resume_prompt`。
