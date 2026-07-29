# Task Plan

## Linked Issue

GH-190

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP190-T1` Owner: goal-core | Depends on: SP190-T6 SP190-T7, approved spec, upstream serial gate allowed | Done when: canonical builder 分别加载 verified invocation/capability/GitHub/lease references；`create_request_digest` 使用唯一 domain+closed RFC8785 object 并精确等于 receipt request digest；`build` 对 active 输出 exact create args、对合法 disabled/missing-budget 直接输出完整 disabled binding、对 invalid evidence 不输出 binding；`bind` 禁止 `--goal-id`、分别消费 create receipt 与 fresh live snapshot，并按 pre-event projection→sequence-0→final bundle 顺序输出无自引用 closed bundle | Verify: `python3 -m pytest -q tests/test_goal_contract.py -k "builder or capability_input or disabled_binding or create_request_digest or bind or live_snapshot or initial_projection or sequence_zero"` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-014 B-015 B-019 B-020 B-022 B-023 B-029 B-030 B-031 B-034 B-038 | 不调用真实 API，不接受 caller ID/mode/capability。
- [ ] `SP190-T2` Owner: schema-gate | Depends on: SP190-T1 | Done when: runtime checkpoint v4 `$ref` 的 closed `goal_binding` 支持 active/disabled/migration_pending 与 active 内的 transition pending；gate 重算 policy/budget/contract、initial/final digest、content-bound queue、action re-anchor、canonical transition evidence，验证 GH-189 lease 与 external revision/status/tail；完整 checkpoint/Goal status+stop_reason 矩阵、terminal reconciliation、post-update false-complete、直接改 current/断链/超预算均 blocked；goal/evidence/runtime schemas 均 <800 行并注册 pack ownership | Verify: `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_queue.py -k "goal or transition or reconciliation or post_update_queue or status_matrix or action_reanchor or rebind or budget"` | Covers: B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-015 B-016 B-017 B-020 B-022 B-023 B-024 B-025 B-026 B-028 B-029 B-031 B-035 B-036 B-037 B-038 B-039 B-040 | 接入 runtime schema/rules/gate。
- [ ] `SP190-T3` Owner: migration | Depends on: SP190-T1 SP190-T2 | Done when: v1/v2/v3 legacy resume stable blocked；verified disabled route 可直接迁移 final v4；active route 先输出 queue-action-blocked `migration_pending`，唯一 create 命令绑定 pending/build/request digest 与 provider idempotency key并先持久化 create-inflight；唯一 finalize 消费同一 receipt/live/GitHub evidence输出 active bundle，崩溃重试通过 request-digest lookup 复用同一 Goal；普通 `goal:null` v4、重复 Goal、未知版本与非法输出被拒绝 | Verify: `python3 -m pytest -q tests/test_goal_contract.py tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k "migration or pending or migration_create or idempotency or receipt_reuse or finalize or recovery or legacy"` | Covers: B-011 B-012 B-013 B-018 B-022 B-023 B-025 B-026 B-027 B-032 B-037 | 不 grandfather 旧 active goal。
- [ ] `SP190-T4` Owner: queue-pack-integration | Depends on: SP190-T1 SP190-T2 SP190-T3 SP190-T6 SP190-T7, GH-172 contract+runtime merged, GH-174 contract+runtime merged and GH-190 rebased after its seven-path overlap, GH-189 contract+runtime merged after GH-174 integration and GH-190 rebased | Done when: queue 与 implx 在 GH-174 canonical phase/reference layout 实际执行 GitHub adapter + `build`/`bind`/`rebind`/`prepare-transition`/`finalize-transition`/migration CLI，只传 exact tool objects、host receipts、action attestations与完整 bundles；active path 每次受保护 action 前取得 fresh live/GitHub evidence；不得手拼 Goal/event/rebind/bundle；templates/AGENT_USAGE/CHANGELOG/checker/assets/skills lock 同步 | Verify: `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_goal_contract.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py -k "queue or tool_payload or action_reanchor or rebind_cli or prepare_transition or finalize_transition or migration or template"` | Covers: B-001 B-003 B-005 B-006 B-007 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 B-027 B-028 B-030 B-031 B-032 B-035 B-036 B-037 B-038 B-039 B-040 B-041 | GH-174/GH-189 未合并、七路径 overlap 未 rebase 或跳序时不得开始。
- [ ] `SP190-T6` Owner: evidence-provenance | Depends on: SP190-T7, approved spec, upstream serial gate allowed | Done when: `github_goal_evidence.py` 完整分页收集 repo/default-base、canonical `workflow.yaml` policy bytes、source/merge/maintainer approval 与 queue snapshot，输出 schema-valid content-bound artifact；runtime invocation/capability/create/update/get/action receipts 只接受 host verifier 对 repo/run/request/revision/tail/action sequence 的 attestation，并支持 request-digest receipt lookup 与 idempotent create；伪造 approval、caller digest、分页漂移、cross-evidence envelope、跨 run receipt 均有负例 | Verify: `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_goal_contract.py -k "policy or approval or routing or capability or receipt_lookup or idempotent_create or action_sequence or pagination or content"` | Covers: B-003 B-005 B-007 B-011 B-015 B-020 B-021 B-022 B-024 B-025 B-026 B-030 B-031 B-032 B-036 B-037 B-039 | 复用现有 GitHub evidence/content-binding 模式。
- [ ] `SP190-T7` Owner: dependency-route | Depends on: approved spec；bootstrap 仅在 fresh 人工证据确认 `GH172→GH174→GH189` contract+runtime 均已合并且 GH190 已逐步 rebase 后执行 | Done when: checker 验证 `specrail-implementation-dependencies-v1` 与 exact overlap；issue adapter/schema 收集 dependency spec/runtime PR、target-base ancestry与rebase证据；route gate 在任一 open/只合并 spec/runtime 缺失/七路径 overlap 未消解/跳序/旧 base fixture 上 blocked，仅 ready fixture allowed；T7 落地后 T6/T1 前重新运行机械 route gate | Verify: `python3 -m pytest -q tests/test_check_workflow.py tests/test_github_issue_evidence.py tests/test_route_gate.py -k "GH190 or dependency or implementation_merged or overlap or serial_order or rebase"` | Covers: B-028 B-033 B-041 | 这是 route dependency 的 bootstrap；handoff 文本本身不算 allowed evidence。

## 并行拆分

- 外部固定串行 `GH-172 merge → rebase+merge GH-174 → rebase+merge GH-189 → rebase GH-190`；截至 2026-07-26 PR #186/#192/#193 均 OPEN，当前不得实现。
- 内部固定串行 `T7 → T6 → T1 → T2 → T3 → T4 → T5`；保留已发布 T1..T6，新增 dependency route 为 T7；builder/schema/evidence/queue 共享合同。
- 不并行修改 GH-160 或自行选择预算值。

## 验证

- [ ] `SP190-T5` Owner: verification-owner | Depends on: SP190-T1 SP190-T2 SP190-T3 SP190-T4 SP190-T6 SP190-T7 | Done when: focused/full/pack/depth/committed-range-diff/hash 与 dry-run forward-use 全绿；`goal-contract-vectors.json` 逐项命名并覆盖 hosted comments `3651606792/95/97/6801/6804/6806/6808/6809/6810/6811/6812/6814` 的正反用例，本地 `pr194-r2-gh174-dependency-not-ready` 由三份 schema-valid issue fixtures 覆盖；13 项均有 case ID→B-ID→test assertion 映射；无真实 Goal API 副作用、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_github_issue_evidence.py tests/test_goal_contract.py tests/test_route_gate.py tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_queue.py tests/test_specrail_schema.py tests/test_check_workflow.py tests/test_pack_asset_validation.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH190 --gate && git diff --check "$(git merge-base origin/main HEAD)"..HEAD` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 B-027 B-028 B-029 B-030 B-031 B-032 B-033 B-034 B-035 B-036 B-037 B-038 B-039 B-040 B-041 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；spec merge/readiness gate 前不得实现。
- 本 issue 不定义默认/aggregate budget；缺批准值时 fail closed。
- checkpoint 目标版本是 v4；v1–v3 active route 只能经 `migration_pending` + finalize，
  旧 goal/普通 `goal:null` 不可继续。
- PR #186/#192/#193 fresh 状态均 OPEN；所有实现等待并按
  `GH-172 → GH-174 → GH-189 → GH-190` 逐项 merge/rebase。GH-174 与 GH-190 的七路径
  overlap 未由 fresh dependency route evidence 消解时，SP190-T4 保持 blocked。
- 合并后只复用 GH-174 canonical queue references 与 GH-189 lease evidence，不复制
  queue/run/fencing contract。
