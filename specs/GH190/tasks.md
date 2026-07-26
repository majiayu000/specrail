# Task Plan

## Linked Issue

GH-190

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP190-T1` Owner: goal-core | Depends on: approved spec | Done when: canonical builder 接收原始 queue/human-decision 与 closed `budget_selection_evidence`，自行生成 immutable baseline、objective/完整 `contract_digest` 和 derived budget decision；`build`/`bind` CLI 的 closed JSON envelope、稳定 reason/error 顺序、exit 0/1、required-ID active binding 均有测试；等价乱序输入稳定，存在可用预算时伪造 missing/invalid 被拒绝 | Verify: `python3 -m pytest -q tests/test_goal_contract.py -k "builder or budget or digest or cli or bind"` | Covers: B-001 B-002 B-003 B-004 B-005 B-014 B-015 B-019 | 新增 goal contract，不调用真实 API。
- [ ] `SP190-T2` Owner: schema-gate | Depends on: SP190-T1 | Done when: draft 与 required-`goal_id` active 类型分离；active closed schema 独立为 `schemas/goal_contract.schema.json` 并由 runtime checkpoint v4 `$ref` 引用（两个 schema 均 <800 行），注册进 `SPEC_SCHEMA_FILES` 并同步 ownership 测试；gate 重算 budget selection/contract digest，验证 immutable baseline、current queue rebind hash chain、append-only status transition hash chain、run/fencing/checkpoint binding，拒绝 terminal→active、断链、直接改 current digest 与超预算 | Verify: `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k "goal or transition or rebind or budget"` | Covers: B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-015 B-016 B-017 | 接入 runtime schema/rules/gate。
- [ ] `SP190-T3` Owner: migration | Depends on: SP190-T1 SP190-T2 | Done when: schema 以 version-conditional 分支读取 v1/v2/v3/v4，legacy resume 稳定 blocked；`migrate-checkpoint` 对 v1、v2、v3 分别保留合法字段与 provenance，输出 v4 `goal:null`，不把 tranche budget 推断为 Goal budget；缺 fresh routing evidence、未知版本、非法输出均 exit 1 且没有可写 checkpoint | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k "migration or legacy"` | Covers: B-011 B-012 B-013 B-018 | 显式迁移，不 grandfather 旧 active goal。
- [ ] `SP190-T4` Owner: queue-pack-integration | Depends on: SP190-T1 SP190-T2 SP190-T3, GH-172 merged | Done when: queue 与 implx 两个入口实际执行 `build`/`bind` CLI，只传 CLI `create_goal` object 且只写 bound output；缺批准预算不创建 active Goal；templates/AGENT_USAGE/CHANGELOG、checker required asset 与 skills lock 同步 v4 migration/baseline/rebind/transition 形态 | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py -k "queue or tool_payload or migration or template"` | Covers: B-001 B-003 B-006 B-007 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 | 对齐已合并 GH-174/GH-189，不手拼 payload。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4`；builder/schema/queue 共享合同。
- 不并行修改 GH-160 或自行选择预算值。

## 验证

- [ ] `SP190-T5` Owner: verification-owner | Depends on: SP190-T1 SP190-T2 SP190-T3 SP190-T4 | Done when: focused/full/pack/depth/committed-range-diff/hash 与 dry-run forward-use 全绿，无真实 Goal API 副作用、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py tests/test_specrail_schema.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH190 --gate && git diff --check "$(git merge-base origin/main HEAD)"..HEAD` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；spec merge/readiness gate 前不得实现。
- 本 issue 不定义默认/aggregate budget；缺批准值时 fail closed。
- checkpoint 目标版本是 v4；v1–v3 只能经 `migrate-checkpoint` 迁移，旧 goal 不可继续 active。
- queue/lock 实现等待 GH-172，并 rebase 已合并 GH-174/GH-189 合同。
