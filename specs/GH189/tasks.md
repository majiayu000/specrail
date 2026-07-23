# Task Plan

## Linked Issue

GH-189

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP189-T1` Owner: lease-core | Depends on: approved spec | Done when: shared repo identity、closed schema、inspect/acquire/renew/release/takeover 与原子失败全部有测试 | Verify: `python3 -m pytest -q tests/test_active_run_lease.py` | Covers: B-001 B-002 B-004 B-005 B-006 B-008 B-009 B-010 B-011 B-013 B-014 | 新增 lease 核心，不接 queue。
- [ ] `SP189-T2` Owner: runtime-binding | Depends on: SP189-T1 | Done when: checkpoint schema/gate 强制 repo/run/token/digest 与显式 lease 证据一致，旧/串线 token 阻断 | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k lease` | Covers: B-003 B-004 B-007 B-008 B-011 | 接入 runtime schema/rules/gate/template。
- [ ] `SP189-T3` Owner: queue-integration | Depends on: SP189-T1 SP189-T2 | Done when: startup acquire，lane/checkpoint/所有 remote write 前 renew/validate，正常完成/中断只释放自己的 lease，held 状态无 polling | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_runtime_ledger_gate.py -k "queue or boundary or release"` | Covers: B-003 B-004 B-007 B-010 B-011 B-014 | 更新 queue；若 GH-174 已合并则放入其 canonical runtime phase。
- [ ] `SP189-T4` Owner: pack-docs | Depends on: SP189-T3 | Done when: checker/schema required assets、AGENT_USAGE/CHANGELOG 与 Skill hash 同步，普通 workflow 不读取活动 lease | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-012 B-013 | 完成 pack wiring。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4`，lease/schema/queue 是共享状态机。
- 只读 reviewer 可并行，不得修改 manifest 文件。

## 验证

- [ ] `SP189-T5` Owner: verification-owner | Depends on: SP189-T1 SP189-T2 SP189-T3 SP189-T4 | Done when: focused/full/pack/depth/diff/hash 全绿，两个临时 worktree 证明唯一 owner、resume 和授权 takeover，无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH189 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 | exact-head 交付证据。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 ready_to_implement 前不得实现。
- 不得自动 takeover/kill/删除他人 lease，remote write 仍遵守当前会话授权。
- manifest 限定 14 个路径，不含 GH-160。
