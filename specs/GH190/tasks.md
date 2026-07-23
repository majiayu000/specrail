# Task Plan

## Linked Issue

GH-190

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP190-T1` Owner: goal-core | Depends on: approved spec | Done when: canonical builder、budget source、四终止、re-anchor、digest、branch 与失败均有纯函数测试 | Verify: `python3 -m pytest -q tests/test_goal_contract.py` | Covers: B-001 B-002 B-003 B-004 B-005 B-007 B-013 B-014 | 新增 goal contract，不调用真实 API。
- [ ] `SP190-T2` Owner: schema-gate | Depends on: SP190-T1 | Done when: active goal closed schema、状态转换、queue/run/checkpoint/digest/budget binding 全部 fail closed | Verify: `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k goal` | Covers: B-006 B-008 B-009 B-010 B-011 B-012 B-013 | 接入 runtime schema/rules/gate/template。
- [ ] `SP190-T3` Owner: queue-integration | Depends on: SP190-T1 SP190-T2, GH-172 merged | Done when: queue 只从 builder 取得 create_goal 参数，缺批准预算不创建 active Goal，返回 ID 后才写 bound checkpoint | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "queue or tool_payload"` | Covers: B-001 B-003 B-006 B-007 B-014 | 更新 queue 与 Skill hash；对齐已合并 GH-174/GH-189。
- [ ] `SP190-T4` Owner: pack-docs | Depends on: SP190-T3 | Done when: checker required asset、AGENT_USAGE/CHANGELOG 说明迁移，workflow check 纯仓库通过 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-012 B-013 | pack 收口。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4`；builder/schema/queue 共享合同。
- 不并行修改 GH-160 或自行选择预算值。

## 验证

- [ ] `SP190-T5` Owner: verification-owner | Depends on: SP190-T1 SP190-T2 SP190-T3 SP190-T4 | Done when: focused/full/pack/depth/diff/hash 与 dry-run forward-use 全绿，无真实 Goal API 副作用、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py tests/test_specrail_schema.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH190 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；spec merge/readiness gate 前不得实现。
- 本 issue 不定义默认/aggregate budget；缺批准值时 fail closed。
- queue/lock 实现等待 GH-172，并 rebase 已合并 GH-174/GH-189 合同。
