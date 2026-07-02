# Product Spec

## Linked Issue

GH-37

## 用户问题

在 full-queue drain 过程中，runtime checkpoint 可以记录队列里仍有
`needs_spec` 或 `needs_tasks` 的 issue/PR。如果这些条目同时被标成
`running`、`complete` 或其他 implementation/完成状态，agent 可能误以为队列
已经可以继续实现或已经完成，从而跳过 SpecRail 的 spec/task planning gate。

## 目标

- 阻止 `needs_spec` 和 `needs_tasks` 条目进入 implementation-like 状态。
- 允许 handoff checkpoint 明确保留仍需 spec/task planning 的剩余队列。
- 阻止 full-queue checkpoint 在仍有 spec/task work 时报告 `complete`。
- 用 fixture 覆盖允许 handoff 与阻断 false-complete 两种行为。

## 非目标

- 不改变 GitHub issue、PR、label、review 或 SpecRail spec packet 的 canonical
  truth 地位。
- 不给 agent 增加 merge、final approval 或自动关闭 issue 的权限。
- 不把 runtime checkpoint 变成必需工作流；它仍然是可选本地 handoff 辅助。
- 不扩大 #36 到完整 queue runner 或 threads orchestration 实现。

## Behavior Invariants

1. 当 `queue_mode` 是 `full_queue_drain` 时，带 issue/PR 的条目必须声明
   `spec_status`。
2. `spec_status: needs_spec` 或 `needs_tasks` 的条目只能处于 spec/task
   planning 相关状态，例如 `planning`、`needs_spec`、`needs_tasks`、
   `blocked`、`deferred` 或 `needs_human`。
3. `spec_status: needs_spec` 或 `needs_tasks` 的条目不得处于 `running`、
   `complete`、`merge_ready`、`merged` 等会暗示实现或完成的状态。
4. `status: handoff` 的 full-queue checkpoint 可以保留 `needs_spec` 或
   `needs_tasks` 的 `remaining_queue`，前提是每个剩余项都有 `next_action`。
5. `status: complete` 的 full-queue checkpoint 如果仍有
   `needs_spec`、`needs_tasks`、`waiting_ci` 或其他未 drained 状态，必须返回
   `blocked`。

## Acceptance Criteria

- [ ] `checks/runtime_ledger_gate.py` 阻止 `needs_spec` / `needs_tasks` 条目以
      implementation-like 状态继续。
- [ ] handoff fixture 中保留 `needs_spec` 剩余队列时，runtime ledger gate 返回
      `allowed`。
- [ ] false-complete fixture 中保留 `needs_spec` 剩余队列时，runtime ledger gate
      返回 `blocked`。
- [ ] `tests/test_runtime_ledger_gate.py` 覆盖 missing spec、umbrella coverage、
      waiting CI 和 remaining needs_spec 的 full-queue 场景。
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` 通过。
- [ ] `python3 -m pytest -q` 通过。

## 边界情况

- 条目缺少 `spec_status`：block。
- `spec_status` 是 `needs_spec`，但 `state` 是 `running`：block。
- `spec_status` 是 `umbrella_covered` 且说明了覆盖来源：允许继续通过 gate。
- full queue 已标记 `complete`，但 `remaining_queue` 里仍有 `waiting_ci`：block。
- full queue handoff 仍有 `needs_spec`：允许 handoff，但不能报告 complete。

## 发布说明

收紧 full-queue runtime checkpoint gate，确保仍需 spec/task planning 的队列项
不会被误标为正在实现或已完成。
