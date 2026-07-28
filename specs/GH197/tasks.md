# Task Plan

## Linked Issue

GH-197

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP197-T1` Owner: migration-core | Depends on: approved spec | Done when: `checks/review_migration.py`、record/authorization schemas 与 `review_result.schema.json` closed `migration_provenance` marker 落地；受理域仅 round-1 bounded legacy；record/authorization 持久化 `migration_base_sha`、`source_artifact_head_sha`、`authorized_pr_base_sha`、`authorized_pr_head_sha`；source 必须匹配迁移前 Git commit/path/blob bytes；normalization 只对存在且 non-null 的 base 执行 `set_null`、对存在且 non-null 的 diff 执行 `delete`，absent/null shape 原样保留；authorization ID 从完整 trusted scope 确定性派生；重放/摘要/marker/record cross-binding、非白名单差异与跨 scope 复用均 block | Verify: `python3 -m pytest -q tests/test_review_migration.py tests/test_specrail_schema.py -k "scope or git_blob or normalization or absent_base or migration_base or head_identity or authorization_id or replay or tamper or reuse"` | Covers: B-001 B-002 B-003 B-004 B-005 B-007 B-015 B-016 B-018 B-019 | Git 命令使用参数数组，source/record 同提交重算不能过。
- [ ] `SP197-T2` Owner: migration-auth-cli | Depends on: SP197-T1 | Done when: 新增 `checks/github_review_migration_evidence.py`，fresh 双读 GitHub authorization comment、actor `maintain|admin` permission、repository immutable ID、PR base/head 与 default-base migration cutoff；`github_pr_evidence.py` 仅薄委托且保持 ≤800 行；CLI dry-run 只输出 provider-bound `authorization_request`，没有远端事件时不能产出完整 authorization；`--apply` 强制查询远端 exact decision，拒绝本地 authorization/role map/actor/source 自证及 provider/comment/identity 漂移；source commit 必须是 `authorized_pr_head_sha` ancestor，`migration_base_sha` 只绑定 registry cutoff；record path/ID 唯一派生、`migrated_at=authorized_at`，partial state fail closed、exact retry/reapply 幂等 | Verify: `python3 -m pytest -q tests/test_github_review_migration_evidence.py tests/test_review_migration.py tests/test_github_pr_evidence.py -k "provider or permission or comment or dry_run or migration_base or head_identity or ancestry or authorization_id or rollback"` | Covers: B-002 B-003 B-007 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-019 | 工具不改 manifest；GitHub/provider 不可用时 fail closed。
- [ ] `SP197-T3` Owner: trusted-loader-routing | Depends on: SP197-T1 SP197-T2 | Done when: 新增 generic closed registry schema 与 repo overlay `.specrail/review_legacy_round1_registry.json`；adapter/PR gate 只从 trusted `migration_base_sha` 的固定 conventional path 加载，校验 repo/cutoff/provider snapshot、expected PR/identity list/count/entries digest 与 source Git objects，再输出分离 legacy/current head 的 exact-set `legacy_review_artifacts[]`；caller path/空集合/子集/coverage scope 均拒绝；manifest v2 `migrations[]` + verifier 接入 loader，通用 artifact validation 前先分类 trusted legacy，命中 identity 时 marker/record/fresh provider authorization/entry mandatory，未迁移只产生 `legacy_round1_migration_required`；`pr_review_contract.py` 与 terminal `pr_gate.py` 用同一 registry/auth reload | Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_github_review_migration_evidence.py tests/test_pack_asset_validation.py tests/test_review_result_semantics.py tests/test_review_migration.py tests/test_pr_gate_terminal.py -k "legacy_registry or legacy_identity or migration or provenance or trusted_reload or migration_required"` | Covers: B-006 B-007 B-008 B-009 B-011 B-013 B-015 B-016 B-020 | 同步 PR evidence schema、`skills/specrail-pr-gate/SKILL.md` 与 pack ownership；native v1/v2 零改动。
- [ ] `SP197-T4` Owner: origin-gate | Depends on: SP197-T3 | Done when: `review_json_gate.py` 对 creation-mode 新 round-1 bounded artifact 的 non-null base/diff block；`review_result_semantics.py` 使用闭集 `artifact_origin`，仅 registry pre-classification 可进入 legacy mode；#186 absent/null base shape 不被新增字段；native、legacy candidate 与 marker-bearing migrated artifact 路由不混淆 | Verify: `python3 -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py tests/test_review_migration.py -k "round1 or creation_origin or legacy_classification or absent_base"` | Covers: B-005 B-006 B-010 B-018 B-020 | 不追溯未命中 trusted registry 的普通 artifact。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4 → T5`：record/marker/auth/legacy identity 是同一
  trust chain，禁止由并行 lane 在共享 schema/semantics 上各自猜测。

## 验证

- [ ] `SP197-T5` Owner: verification-owner | Depends on: SP197-T1 SP197-T2 SP197-T3 SP197-T4 | Done when: PR #181/#186/#193 真实形态 fixture 的迁移前 block 与迁移后通过 forward test 全绿；覆盖全部既有 finding，并逐项覆盖 GH-213 三条与 `discussion_r3660108740/8753/8770/8782/8797`：本地 authorization/role-map 自证、provider/comment/permission 漂移、dry-run 缺 trusted identity、migration base 未持久化、legacy/current head 混用、错 ancestry 目标、#186 absent base 被新增、rollback 后跨 scope ID 复用、legacy classification 晚于 origin rule；`skills/specrail-pr-gate` 与 terminal forward path 明确；full suite、all-specs、depth/diff 全绿且 checks 文件 `<800` 行 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 | exact-head 证据；不 reply/resolve hosted threads。

## Handoff Notes

- 当前仅交付 spec packet；实现与 #181/#186/#193 的实际迁移操作等待本 spec 合并。
- 迁移 apply 必须消费 GitHub fresh provider 返回的 exact
  `migrate_legacy_round1_once`；本地 authorization/role map、CLI actor/source、自报角色、
  queue/auto/cap/merge 授权均不得代执行。
- 原始 artifact 字节在任何阶段都不修改；回滚 = 删除派生文件 + 记录 + manifest 条目。
- source truth 来自授权前已存在且可达的 Git commit/path/blob bytes；当前工作树与 record
  自报 digest 不能替代。
- `source_artifact_head_sha` 与 `authorized_pr_head_sha` 是不同 identity；
  `migration_base_sha` 必须持久化但不得作为 source ancestry 目标。
