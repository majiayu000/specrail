# Product Spec

## Linked Issue

GH-137

## 用户问题

2026-07-17 一次 implx AUTO 运行（remem-web #3 → remem #880，跨仓库 5 PR / +11,622 行）
连续执行约 13 小时、真实发生 13 次 context compaction，而 checkpoint 全程记录
`compaction_count: 0`、`compaction_budget: 1`，runtime gate 全程放行。根因是三处
结构缺陷：

1. `checks/runtime_gate_rules.py` 的预算判定只读取 checkpoint 内代理自报的
   `compaction_count`，仓库中没有任何代码采集真实 compaction 事件或校验两者一致。
2. `checks/runtime_ledger_gate.py` 对 `context_budget` 只校验
   `0 < soft < hard < critical < 1` 的排序，从不读取真实使用量。
3. `skills/specrail-implement-queue/SKILL.md` 的 goal-active compaction 豁免与
   "stop before the second compaction" 互相冲突，实际执行中被解读为
   "goal 未结束就继续跑"。

预算维度也过于单一：没有 wall-clock、tool-call、review 轮次、同 head 全量测试
次数的上限，本次 861 次 shell / 619 次 wait / 单 spec PR 22 次 review event 均无
熔断。

## 目标

- 预算门禁改用运行时可信计数：checkpoint 新增 `observed_compaction_count`、
  `telemetry_source`、`last_compaction_window_id`；gate 取
  `max(observed, self_reported)` 与预算比较。
- 提供 session telemetry 采集器：从 Codex session jsonl 统计 `context_compacted`
  事件数，作为 `observed_compaction_count` 的来源。
- `telemetry_source: unavailable` 时禁止 `basis: compaction`（校验期失败），强制
  降级到可观测 basis；`basis` 枚举扩展 `runtime_dims`（仅 version 3），使
  wall-clock/tool-call 等硬预算维度可以独立作为合法 basis，覆盖既无 compaction
  遥测又无有意义 item cap 的运行时。
- goal 与 session 解耦：删除 goal-active compaction 豁免，明确 goal 跨 session
  持续、session/tranche 达到 compaction 预算必须结束并 handoff。
- budget 对象新增四个硬预算维度：`max_wall_clock_minutes`、`max_tool_calls`、
  `max_review_correction_rounds`、`max_full_test_runs_per_head`，任一超限与
  compaction 超限同等处理。
- 回归测试覆盖"自报与运行时不一致"与新增维度的全部阻断路径。

## 非目标

- 不修改 goal 工具的 token budget 契约（工具侧限制，由 wall-clock 上限兜底）。
- 不改 implx 的 PR 结构收敛、规模预报义务（独立 issue）。
- 不改 reviewer lane 降级路径与 SKILL.md 中 spec correction 的流程级两轮熔断
  文本（GH-137 的 P1，后续拆分）。注意分层：该非目标指 SKILL 流程语义；B-005
  的 `max_review_correction_rounds`（默认 2）是 checkpoint/gate 侧的硬预算
  维度，属于本 spec 范围，两者互不替代——实现者应新增 gate 维度而不动 SKILL
  的 spec correction 流程文本。
- 不改 `checks/pr_gate.py`、GitHub evidence 链路及现有 fixture 的语义。
- 不为历史 checkpoint 做数据迁移；仅对 checkpoint_version 3 生效，version 2
  照旧校验。

## Behavior Invariants

1. B-001 当 checkpoint 声明 `basis: compaction`（或 `both`）且
   `max(observed_compaction_count, compaction_count) > compaction_budget`，且无
   `budget_override` 时，`runtime_ledger_gate.py` 必须返回 blocked；自报
   `compaction_count` 低于 observed 不得改变结论。
2. B-002 当 `telemetry_source: unavailable` 且 `basis` 为 `compaction` 或 `both`
   时，checkpoint 校验必须失败并给出降级指引（改用 `item_cap` 或
   `runtime_dims`），不得进入预算比较；`basis: runtime_dims`（仅 version 3
   合法，只按四个硬预算维度判定）必须是 gate 接受的合法 checkpoint 形态，
   使降级路径存在合法出口而非被迫伪造 item cap。
3. B-003 telemetry 采集器对同一 session jsonl 的统计必须与文件中
   `context_compacted` 事件行数精确一致；文件不存在或不可读时返回
   `telemetry_source: unavailable`，不得返回 0 计数冒充真实观测。
4. B-004 goal-active 场景不再豁免：goal 处于 active 状态时发生第二次 compaction，
   gate 结论与非 goal 场景完全一致（blocked，除非有 override）；SKILL.md 中不得
   残留 "compaction is not a handoff trigger" 语义的文本。
5. B-005 `max_wall_clock_minutes`（默认 120）、`max_tool_calls`（默认 250）、
   `max_review_correction_rounds`（默认 2）、`max_full_test_runs_per_head`
   （默认 1）任一观测值超过声明值时 gate 返回 blocked，错误信息必须点名超限维度
   与 `observed > limit` 的具体数值。`max_full_test_runs_per_head` 的计数必须
   绑定被检验的 head：checkpoint 记录 `full_test_head_sha` 与
   `observed_full_test_runs_current_head` 成对出现——当计数大于 0 或当前
   tranche 存在被检验的 PR head 时，缺 `full_test_head_sha` 的 full-test 计数
   视为非法；issue/spec-only 等无 PR head 的 tranche 允许缺省该字段且计数
   必须为 0，不得为通过校验伪造 SHA；当记录的 head 与当前 PR head 不一致时，计数
   对新 head 重置为 0 并更新 `full_test_head_sha`，旧 head 的计数保留在历史
   tranche 记录中不被覆盖，使重置可审计而非代理擅自清零。
6. B-006 四个新维度均允许显式声明覆盖默认值，但必须为正整数；非法值（0、负数、
   布尔、非整数）在校验期失败，不得静默回退默认值。
7. B-007 `budget_override` 语义保持不变：有 override 时超预算记 warning 并放行，
   override 必须含引用范围与会话标记；新维度超限同样接受 override，且 override
   不跨维度共享——version 3 采用按维度的多条 override 结构
   （`budget_overrides`），同一 checkpoint 多个维度同时超限时每个维度各需一条
   独立授权记录，缺失其一即对该维度 blocked。
8. B-008 checkpoint_version 2 的现有 checkpoint 与全部现有 fixture 在本次改动后
   校验结果不变（新字段仅在 version 3 必填）；`python -m pytest tests/` 全绿。
9. B-009 gate 与 telemetry 采集器均为只读：不写 session 文件、不修改 checkpoint、
   不发起网络调用；采集器输入路径来自 checkpoint 声明或 CLI 参数，不做目录递归
   猜测。
10. B-010 goal 跨 session 续接语义：checkpoint 新增 `goal_id`/`tranche_id` 后，
    同一 `goal_id` 下新 tranche 的预算独立清零计数，且历史 tranche 的超限记录
    不被覆盖；telemetry 统计必须以 tranche 窗口为界（checkpoint 记录新 tranche
    在 session jsonl 中的起始 offset），同 session rollover 时上一 tranche 的
    compaction 事件不得计入新 tranche 的 `observed_compaction_count`。

## Boundary Checklist

| 边界 | 判定 |
| --- | --- |
| 空输入/缺失输入：session 文件缺失、telemetry 字段缺失 | telemetry 缺失时 `telemetry_source: unavailable`，B-002/B-003 拒绝 compaction basis，不得默认 0 |
| 错误/失败：session jsonl 含损坏行 | 采集器跳过不可解析行但仍统计可解析的 `context_compacted`；解析失败率 100% 时按不可读处理 |
| 权限/未授权：无 override 的超预算继续 | B-001/B-005 blocked；override 缺引用范围或会话标记视为无 override |
| 并发/竞态：session 文件在统计时仍被追加写入 | 采集器按读取时刻快照计数，结果单调不减；gate 使用采集时间戳标注 |
| 重试/幂等：同一 checkpoint 重复跑 gate | 结论幂等；telemetry 重复采集不产生副作用（B-009 只读） |
| 非法状态/状态转换：observed < self-reported | 取 max 判定（B-001），并输出不一致 warning 供审计 |
| 兼容/迁移/回滚：version 2 checkpoint | B-008 行为不变；version 3 才要求新字段；回滚 = 继续用 version 2 |
| 降级/回退：runtime 不暴露 compaction | B-002 强制降级到 `item_cap` 或 `runtime_dims`（wall-clock/tool-call 硬预算维度），禁止不可验证的 compaction basis |
| 证据/审计完整：checkpoint 与 telemetry 不一致 | 不一致本身记入 gate 输出（observed、self-reported、source、window_id 全打印） |
| 取消/中断：tranche 中途 handoff | `stop_reason: budget_exhausted` + resume_prompt 路径保持可用，新维度复用同一 handoff 流程 |

## 验收标准

- [ ] fixture：`compaction_budget=1, observed=2, self-reported=0` → blocked。
- [ ] fixture：`telemetry_source=unavailable` + `basis: compaction` → 校验失败。
- [ ] fixture：goal-active + 第二次 compaction → blocked（无 override 时）。
- [ ] fixture：wall-clock / tool-call / review 轮次 / full-test 各一条超限 → blocked，错误信息含维度名与数值。
- [ ] 采集器单测：构造含 N 行 `context_compacted` 的 jsonl，计数恰为 N；缺文件 → unavailable。
- [ ] SKILL.md 无 goal-active compaction 豁免文本；新增 goal/session 解耦语义段。
- [ ] 现有 `python -m pytest tests/` 与 workflow check 全绿，version 2 fixture 结果不变。
