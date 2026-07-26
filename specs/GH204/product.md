# Product Spec

## Linked Issue

GH-204

## 用户问题

implx 的 queue、threads integration、wrapper handoff 与报告曾分别复制
`specrail_implementation_queue`、`thread_dispatch_gate`、`context_budget` 和
`output_firewall`。重复块逐渐出现字段和必填点差异，执行器无法判断哪个版本是事实
源；同时“小单文件不使用 threads”和“GitHub PR 必须 native reviewer”两条规则缺少
统一判定，导致相同任务可能走相反路径。重复合同还把 queue Skill 推到维护性行数
上限以上。

## 目标

- 让 `specrail_implementation_queue` 结构只在 queue Skill 定义一次。
- 让 dispatch/budget/firewall 事实只写入 runtime checkpoint，handoff/报告只引用。
- 用经 #202 收紧的 `fastlane_policy` 统一小改动与 reviewer lane 的冲突。
- 删除重复说明而不删除任何验证、授权或 fail-closed 门禁。
- 将 queue Skill 收敛到仓库文件大小上限内。

## 非目标

- 不把 runtime checkpoint 提升为 GitHub/spec durable truth 的替代品。
- 不让 handoff 引用丢失可恢复所需的 checkpoint path、head 或 next action。
- 不为 standard/heavy PR 取消 native reviewer 要求。
- 不改变 schema 字段名称或生成新的同义 alias。

## Behavior Invariants

1. B-001 当执行器需要 queue plan 时，`specrail_implementation_queue` 的完整字段定义
   必须只来自 `skills/specrail-implement-queue/SKILL.md`；implx 和 threads 不得维护
   同名结构副本。
2. B-002 当 threads 需要额外 orchestration 数据时，只能定义具名 extension 并引用
   queue block；extension 不得重声明 queue mode、coverage、items、budget 或
   checkpoint 字段。
3. B-003 当 `thread_dispatch_gate`、`context_budget` 或 `output_firewall` 产生或更新
   时，其权威值只写入当前 runtime checkpoint 一次；handoff、wrapper 与报告只能记录
   checkpoint path/ref。
4. B-004 当 handoff 或报告恢复执行时，引用必须足以定位存在且可验证的 checkpoint；
   缺失、不可读或 gate 不通过时不得从复制字段或旧 transcript 重建“通过”状态。
5. B-005 当任务是小型单文件 GitHub PR 且可信 current-head evidence 满足
   `fastlane_policy` 时，可不派 native reviewer lane，但仍需 exact-head local
   self-review artifact 与所有其余 PR gates。
6. B-006 当 B-005 任一条件缺失、PR 为 standard/heavy、触及受保护路径或 tier 有
   歧义时，“小单文件”规则不得覆盖 native reviewer 要求，必须采用更严格路径。
7. B-007 runtime checkpoint 只在 tranche 起点、merge-readiness 前、tranche 终点及
   material state change 更新；不得为每个微步骤重复写相同 dispatch/budget/firewall。
8. B-008 closure audit 在 tranche 末覆盖该 tranche 触及的全部 PR/issue 并批量执行
   一次；只有 audit 前提漂移或人工明确要求时才在 tranche 中途重跑。
9. B-009 当 checkpoint、GitHub truth 与 handoff 引用发生冲突或验证期间出现竞态时，
   执行器必须以 fresh GitHub truth + 通过 gate 的 checkpoint 重新收敛，不能选择
   最有利的副本。
10. B-010 当任务取消、中断或 compaction 发生时，只写必要 checkpoint 和 resume
    引用；恢复后不得读取 raw session/transcript 作为 live queue state。
11. B-011 queue Skill 的最终文件长度必须不超过 800 行；精简只能删除重复说明或迁移
    引用，不能删去独立行为规则、验证命令、授权边界和失败路径。

## 验收标准

- [ ] 仓库中只有 queue Skill 定义完整 `specrail_implementation_queue` block。
- [ ] implx/threads handoff 对 dispatch/budget/firewall 仅引用 checkpoint。
- [ ] small-file/native-review 冲突只通过可信 `fastlane_policy` 判定。
- [ ] checkpoint 三个必写点与 tranche 末批量 closure audit 保持明确。
- [ ] queue Skill 不超过 800 行，pack/lock/runtime/review tests 全绿。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002 B-004 B-005 |
| 错误与失败路径 | covered: B-004 B-006 B-009 |
| 授权/权限 | covered: B-005 B-006 B-011 |
| 并发/竞态 | covered: B-009 |
| 重试/幂等 | covered: B-003 B-007 B-008 B-009 |
| 非法状态转换 | covered: B-004 B-006 |
| 兼容/迁移 | covered: B-001 B-002；保留稳定 block/field IDs |
| 降级/回退 | covered: B-004 B-006 B-009 |
| 证据与审计完整性 | covered: B-003 B-004 B-007 B-008 B-011 |
| 取消/中断 | covered: B-010 |

## 发布说明

这是 agent contract 的单一事实源整理。handoff 消费者应跟随 checkpoint 引用读取
dispatch/budget/firewall，不再期待内嵌副本。无 schema migration；旧复制字段不再是
权威证据。
