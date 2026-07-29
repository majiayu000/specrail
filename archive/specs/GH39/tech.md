# Tech Spec

## Linked Issue

GH-39

## Product Spec

`specs/GH39/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| gate | `checks/runtime_ledger_gate.py` | 顶部定义多个 runtime 状态集合,与 `states.yaml` 无关联 | 映射的源词表 |
| contract | `states.yaml` | 15 个规范状态,`owner`/`next`/`terminal` | 映射的目标词表 |
| lib | `checks/specrail_lib.py` | 已有 `parse_yaml_subset` 与 `validate_state_graph` | 读取规范状态集合的既有能力 |
| tests | `tests/test_runtime_ledger_gate.py` | 覆盖 gate 决策 | 哨兵测试落点 |
| schema | `schemas/runtime_checkpoint.schema.json` | item.state 为自由字符串 | 描述文案需同步"runtime-only 词表"定位 |

## 设计方案

1. 在 `checks/runtime_ledger_gate.py`(或 `specrail_lib.py`,以 GH-38 落地
   位置为准)新增映射常量:

   ```python
   RUNTIME_STATE_MAPPING = {
       "needs_spec": ["ready_to_spec"],
       "needs_tasks": ["spec_approved"],
       "eligible_impl": ["ready_to_implement"],
       "waiting_ci": ["human_review", "ci_green"],
       "needs_ci": ["human_review"],
       "needs_review": ["impl_pr_open", "agent_review"],
       "review_required": ["human_review"],
       "ready_to_merge": ["merge_ready"],
       "merge_ready": ["merge_ready"],
       "merged": ["merged"],
       "open": "runtime_only",
       "planning": "runtime_only",
       "running": "runtime_only",
       "blocked": "runtime_only",
       "handoff": "runtime_only",
       "complete": "runtime_only",
       ...
   }
   ```

   具体映射值在实现时逐一核对语义,以上为方向示例;`runtime_only`
   哨兵值表示该状态描述 agent 执行生命周期而非仓库工作流位置。
2. 新增哨兵测试:
   - 收集 gate 全部状态集合的并集,断言与 `RUNTIME_STATE_MAPPING` 的
     键集合相等(双向)。
   - 对每个非 `runtime_only` 的映射值,用 `parse_yaml_subset` 读取
     `states.yaml`,断言每个目标状态 ID 存在。
3. 在 schema 的 `state` 字段 description 与 `templates/tranche_checkpoint.md`
   补一句定位声明:runtime 状态是交接辅助词表,规范工作流状态见
   `states.yaml`,映射见 `RUNTIME_STATE_MAPPING`。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `RUNTIME_STATE_MAPPING` 常量 | 代码审查 + 哨兵测试 |
| P2 | 哨兵测试(键集合双向相等) | `pytest -k runtime_state_mapping` |
| P3 | 哨兵测试(states.yaml 存在性) | `pytest -k runtime_state_mapping` |
| P4 | gate 回归 | `pytest -q tests/test_runtime_ledger_gate.py` |

## 数据流

新增测试期数据流:`states.yaml` → `parse_yaml_subset` → 状态 ID 集合 →
与映射常量对账。运行时数据流不变。

## 备选方案

- 收敛 runtime 词表直接复用 `states.yaml` 状态 ID:被否——会破坏已有
  checkpoint 兼容性,且 `planning`/`running`/`handoff` 等执行生命周期
  状态在规范状态机中本就没有对应物。
- 把映射写进 `states.yaml`:被否——污染规范契约文件,runtime 词表是
  gate 的实现细节。

## 风险

- Security: 无新增面。
- Compatibility: 已有 checkpoint 完全兼容;映射是新增声明,不改判定。
- Performance: 哨兵测试解析一次 `states.yaml`,可忽略。
- Maintenance: 新增映射需要在增删状态时维护,但这正是哨兵测试要强制的
  同步点——把隐性漂移变成显性测试失败。

## 测试计划

- [ ] Unit tests: 映射双向完整性;states.yaml 存在性;gate 回归。
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`。
- [ ] Manual verification: 在本地向 `FULL_QUEUE_NON_DRAINED_STATES` 临时
      添加一个未声明状态,确认哨兵测试失败后还原。

## 回滚方案

单 commit 回滚:删除映射常量、哨兵测试与文档定位声明。无格式迁移。
