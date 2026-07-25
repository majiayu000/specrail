# Task Plan

## Linked Issue

GH-189

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP189-T1` Owner: lease-core | Depends on: approved spec | Done when: shared repo identity、required `checkpoint_bound` closed schema、repo-wide non-blocking mutation mutex、inspect/acquire/renew/release/takeover、required bounded TTL 与原子失败全部有测试；barrier race 证明 renew/release/takeover 只有一个旧 digest compare 成功 | Verify: `python3 -m pytest -q tests/test_active_run_lease.py` | Covers: B-001 B-002 B-004 B-005 B-006 B-008 B-009 B-010 B-011 B-013 B-014 | 新增 lease 核心，不接 queue。
- [ ] `SP189-T2` Owner: runtime-binding | Depends on: SP189-T1 | Done when: `checkpoint_version: 4` 强制 `run_lease` 的 repo/run/token，lease 单向保存完整 checkpoint bytes digest，稳定绑定与任一侧篡改均有测试；首租 `checkpoint_bound: false` + `checkpoint_digest: null` schema 合法但不能通过 resume/lane/remote-write gate；Goal 明确只作连续性/预算上下文，不参与安全授权；v1–v3 fixture 继续合法但不能授权 lease-aware resume，v4 继承 v3 budget/telemetry，5+ 拒绝；模板 JSON 示例同步为 v4 | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_gate_rules.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_queue.py tests/test_specrail_schema.py -k "lease or goal or first_acquire or digest or version or budget" && rg -n run_lease templates/tranche_checkpoint.md templates/zh-CN/tranche_checkpoint.md` | Covers: B-003 B-004 B-007 B-008 B-011 | 更新 schema/rules/gate、v4 fixture/builder、版本接受测试和模板；保留已声明的 v1–v3 compatibility fixtures 不变。
- [ ] `SP189-T3` Owner: queue-integration | Depends on: SP189-T1 SP189-T2 | Done when: startup acquire，lane/checkpoint/所有 remote write 前以 required bounded TTL renew/validate，等待超过硬上限先 checkpoint/handoff，正常完成/中断只在 mutation mutex 内释放自己的 lease，held/busy 状态无 polling | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_runtime_ledger_gate.py -k "queue or boundary or release or ttl or mutex"` | Covers: B-003 B-004 B-007 B-010 B-011 B-014 | 更新 queue；若 GH-174 已合并则放入其 canonical runtime phase。
- [ ] `SP189-T4` Owner: pack-docs | Depends on: SP189-T3 | Done when: checker/schema required assets（含在 `checks/pack_asset_validation.py` 的 `SPEC_SCHEMA_FILES` 注册 `schemas/active_run_lease.schema.json` 并更新 `tests/test_pack_asset_validation.py` 的 ownership 断言）、AGENT_USAGE/CHANGELOG 与 Skill hash 同步，普通 workflow 不读取活动 lease | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-012 B-013 | 完成 pack wiring。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4`，lease/schema/queue 是共享状态机。
- 只读 reviewer 可并行，不得修改 manifest 文件。

## 验证

- [ ] `SP189-T5` Owner: verification-owner | Depends on: SP189-T1 SP189-T2 SP189-T3 SP189-T4 | Done when: focused/full/pack/depth/diff/hash 全绿，两个临时 worktree 证明唯一 owner、稳定单向 digest resume、serialized replace race、bounded TTL 与授权 takeover，无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH189 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 | exact-head 交付证据。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 ready_to_implement 前不得实现。
- 不得自动 takeover/kill/删除他人 lease，remote write 仍遵守当前会话授权。
- manifest 完整列出 v4 hard-coded consumers、builder/acceptance tests 与新增 v4 fixture；
  已有 v1–v3 fixtures 按兼容合同保持不变，不含 GH-160。
