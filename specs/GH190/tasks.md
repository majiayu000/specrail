# Task Plan

## Linked Issue

GH-190

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP190-T1` Owner: goal-core | Depends on: SP190-T6, approved spec, GH-189 contract + runtime implementation merged into target default base and branch rebased | Done when: canonical builder 只从 verified invocation/capability/GitHub/lease evidence 导出 routing、预算与 baseline；自行生成 objective/完整 `contract_digest`；`build` 输出 exact create args，`bind` 禁止 `--goal-id` 并只接受 exact request 的 attested create/live receipt，一次输出含 routing/baseline/current/sequence-0/external anchor/active contract 的 closed bundle；稳定 reason/error/exit 0/1 与乱序等价测试全绿 | Verify: `python3 -m pytest -q tests/test_goal_contract.py -k "builder or budget or digest or cli or bind or receipt or bundle"` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-014 B-015 B-019 B-020 B-022 B-023 | 不调用真实 API，不接受 caller ID/mode/capability。
- [ ] `SP190-T2` Owner: schema-gate | Depends on: SP190-T1 | Done when: runtime checkpoint v4 `$ref` 的 closed `goal_binding` 仅允许 active/disabled/migration_pending；gate 重算 policy/budget/contract、content-bound queue、canonical transition evidence，验证 GH-189 lease 与 external monotonic Goal revision/status/tail；terminal history 删除后伪造 active、anchor 缺失/回退、receipt mismatch、直接改 current、断链与超预算全部 blocked；goal/evidence/runtime schemas 均 <800 行并注册 pack ownership | Verify: `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k "goal or transition or evidence or anchor or reactivation or rebind or budget"` | Covers: B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-015 B-016 B-017 B-020 B-022 B-023 B-024 B-025 B-026 B-028 | 接入 runtime schema/rules/gate。
- [ ] `SP190-T3` Owner: migration | Depends on: SP190-T1 SP190-T2 | Done when: v1/v2/v3 legacy resume stable blocked；verified disabled route 可直接迁移 final v4；需要 active Goal 时只输出 schema/gate-valid、queue-action-blocked 的 `migration_pending`，唯一 recovery 为 finalize；finalize 消费 exact pending digest、fresh remote evidence 与 attested create/live receipt并原子输出 complete bundle，崩溃重试复用同一 Goal；普通 `goal:null` v4、未知版本与非法输出被拒绝 | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k "migration or pending or finalize or recovery or legacy"` | Covers: B-011 B-012 B-013 B-018 B-022 B-023 B-025 B-026 B-027 | 不 grandfather 旧 active goal。
- [ ] `SP190-T4` Owner: queue-pack-integration | Depends on: SP190-T1 SP190-T2 SP190-T3 SP190-T6, GH-172 merged, GH-189 contract + runtime implementation merged into target default base | Done when: queue 与 implx 实际执行 GitHub adapter + `build`/`bind`/transition/finalize CLI，只传 exact `create_goal` object、host receipt 与完整 bundle；不得手拼 Goal ID/routing/digest/bundle；active path 每次 resume/rebind/terminal 都取得 fresh live/GitHub evidence；templates/AGENT_USAGE/CHANGELOG/checker/assets/skills lock 同步 | Verify: `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_goal_contract.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py -k "queue or tool_payload or evidence or migration or template"` | Covers: B-001 B-003 B-006 B-007 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 B-027 B-028 | GH-189 assets 未合并/未 rebase 时不得开始。
- [ ] `SP190-T6` Owner: evidence-provenance | Depends on: approved spec, GH-189 contract + runtime implementation merged into target default base and branch rebased | Done when: `github_goal_evidence.py` 完整分页收集 repo/default-base、canonical `workflow.yaml` policy bytes、source/merge/maintainer approval 与 queue snapshot，输出 schema-valid content-bound artifact；runtime invocation/capability/create/update/get receipts 只接受 host verifier 对 repo/run/request/revision/tail 的 attestation，缺失 evidence 与 trusted absence 区分；伪造 approval、caller digest、分页漂移、跨 run receipt 均有负例 | Verify: `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_goal_contract.py -k "policy or approval or routing or capability or receipt or pagination or content"` | Covers: B-003 B-007 B-011 B-015 B-020 B-021 B-022 B-024 B-025 B-026 B-028 | 复用现有 GitHub evidence/content-binding 模式。

## 并行拆分

- 固定串行 `T6 → T1 → T2 → T3 → T4 → T5`；保留已发布 T1..T5，新增 evidence lane
  为 T6；builder/schema/evidence/queue 共享合同。
- 不并行修改 GH-160 或自行选择预算值。

## 验证

- [ ] `SP190-T5` Owner: verification-owner | Depends on: SP190-T1 SP190-T2 SP190-T3 SP190-T4 SP190-T6 | Done when: focused/full/pack/depth/committed-range-diff/hash 与 dry-run forward-use 全绿；伪造 routing/capability/approval/Goal ID、incomplete bind bundle、unbound transition/remote digest、terminal history rewrite、migration pending bypass 与 GH-189 未合并 dependency 均有 schema-valid blocked fixture；无真实 Goal API 副作用、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_goal_contract.py tests/test_runtime_ledger_gate.py tests/test_specrail_schema.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH190 --gate && git diff --check "$(git merge-base origin/main HEAD)"..HEAD` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 B-027 B-028 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；spec merge/readiness gate 前不得实现。
- 本 issue 不定义默认/aggregate budget；缺批准值时 fail closed。
- checkpoint 目标版本是 v4；v1–v3 active route 只能经 `migration_pending` + finalize，
  旧 goal/普通 `goal:null` 不可继续。
- GH-189/PR #193 fresh 状态仍 OPEN；所有实现等待其合并到 target default base 后
  rebase，且只复用其 lease evidence，不复制 run/fencing contract。
- queue/lock integration 另等待 GH-172；GH-174 已合并后的结构在 rebase 时对齐。
