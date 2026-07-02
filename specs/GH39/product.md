# Product Spec

## Linked Issue

GH-39

## 用户问题

`states.yaml` 是 SpecRail 的规范状态机,但 `checks/runtime_ledger_gate.py`
另起了一套 runtime 状态词表:`eligible_impl`、`waiting_ci`、`needs_ci`、
`needs_review`、`review_required`、`ready_to_merge` 等状态不在
`states.yaml` 中,两套词表之间没有映射声明,也没有一致性校验。词表在
一处修改时另一处不会同步,长期漂移后 agent 无法判断 checkpoint 里的
item 状态对应规范状态机的哪个位置,交接语义变得不可靠。

## 目标

- 在一处显式声明 runtime item 状态词表及其到 `states.yaml` 规范状态的
  映射(或显式标记为 runtime-only)。
- 提供漂移哨兵测试:gate 使用的每个状态要么映射到规范状态,要么被显式
  声明为 runtime-only;新增未声明状态会使测试失败。
- 保持 runtime ledger gate 的现有阻断行为不变。

## 非目标

- 不修改 `states.yaml` 的规范状态机结构。
- 不重命名 checkpoint 中已使用的 runtime 状态值(不破坏已有 checkpoint)。
- 不把 runtime 词表升格为第二个规范状态机。

## Behavior Invariants

1. 存在唯一的映射声明(代码常量),列出 gate 认可的全部 runtime item
   状态,每个状态标注:映射到的 `states.yaml` 状态 ID,或
   `runtime_only` 标记。
2. 漂移哨兵测试从 `runtime_ledger_gate` 的状态集合出发逐一核对映射
   声明;任何出现在 gate 集合但不在映射声明中的状态使测试失败,反之
   亦然。
3. 映射声明中引用的规范状态 ID 必须真实存在于 `states.yaml`;引用不
   存在的状态 ID 使测试失败。
4. gate 对既有合法/非法 checkpoint 的决策输出与现状完全一致。

## 验收标准

- [ ] 映射声明存在且唯一,覆盖 `FULL_QUEUE_NON_DRAINED_STATES`、
      `MERGE_READY_STATES`、`FULL_QUEUE_TERMINAL_REMAINDER_STATES` 与
      `CHECKPOINT_STATUSES` 中的全部状态。
- [ ] 漂移哨兵测试存在并通过;人为添加一个未声明状态可复现失败。
- [ ] `python3 -m pytest -q tests/test_runtime_ledger_gate.py` 通过。
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` 通过。

## 边界情况

- 一个 runtime 状态映射到多个规范状态(如 `waiting_ci` 横跨
  `human_review`→`ci_green`)时,允许映射为规范状态列表,但列表不能
  为空。
- `states.yaml` 未来删除某个被映射引用的状态时,哨兵测试必须失败,
  提示同步修改映射。

## 发布说明

无 checkpoint 格式变化,无 gate 行为变化;纯声明与测试加固。文档中
首次明确"runtime 词表是交接辅助词表,不是第二个规范状态机"。
