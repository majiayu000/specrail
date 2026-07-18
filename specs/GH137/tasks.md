# Task Plan

## Linked Issue

GH-137

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP137-T1` 新建 `checks/session_telemetry.py`：只读扫描 session jsonl 统计 `context_compacted` 事件，输出 `observed_compaction_count`/`telemetry_source`/`last_compaction_window_id`，缺文件或全不可解析返回 unavailable。Covers: B-003 B-009。Owner: agent. Done when: 采集器单测通过. Verify: `python -m pytest tests/test_session_telemetry.py -q`
- [ ] `SP137-T2` 落地 checkpoint_version 3：先放开版本门禁（`checks/runtime_ledger_gate.py` 的 `CHECKPOINT_VERSIONS = {1, 2}` → `{1, 2, 3}`，`schemas/runtime_checkpoint.schema.json` 的 `checkpoint_version` 枚举 `[1, 2]` → `[1, 2, 3]`），再在 `checks/runtime_gate_rules.py` 实现：必填非负观测字段校验、`basis` 扩展 `runtime_dims`、unavailable 拒绝 compaction basis、`max(observed, self_reported)` 判定、四维硬预算、`full_test_head_sha` 绑定与重置规则、per-dimension `budget_overrides`、`goal_id` 可选而顶层 `tranche_id` 保持必填，version 2 路径不变。Covers: B-001 B-002 B-005 B-006 B-007 B-008 B-010。Owner: agent. Done when: 新旧 fixture 判定全部符合 Product-to-Test Mapping. Verify: `python -m pytest tests/test_runtime_ledger_gate.py tests/test_check_workflow.py -q`
- [ ] `SP137-T3` 修订 `skills/specrail-implement-queue/SKILL.md`：删除 goal-active compaction 豁免段，替换为 goal/session 解耦语义与 compaction 后五步纪律（采集 telemetry → 回写 → 读 checkpoint → 刷新远端 → gate 判定）。Covers: B-004。Owner: agent. Done when: 豁免文本不存在且新语义段完整. Verify: `rg -c "not a handoff trigger" skills/specrail-implement-queue/SKILL.md` 退出码 1
- [ ] `SP137-T4` 新增回归 fixtures 与测试：telemetry mismatch blocked、unavailable + compaction basis 校验失败、goal-active 第二次 compaction blocked、四维超限各一条、override 按维度独立、新 tranche 计数清零。Covers: B-001 B-002 B-004 B-005 B-007 B-010。Owner: agent. Done when: 全部新用例通过且现有测试无回归. Verify: `python -m pytest tests/ -q`

## 并行拆分

T1 与 T3 可并行；T2 依赖 T1 的 Telemetry 数据结构；T4 依赖 T1/T2/T3 完成。
