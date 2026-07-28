# Task Plan

## Linked Issue

GH-197

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP197-T1` Owner: migration-core | Depends on: approved spec | Done when: `checks/review_migration.py`、record/authorization schemas 与 `review_result.schema.json` closed `migration_provenance` marker 落地；受理域仅 round-1 bounded legacy；record/authorization 持久化 `migration_base_sha`、`source_artifact_head_sha`、`authorized_pr_base_sha`、`authorized_pr_head_sha`；source 必须匹配迁移前 Git commit/path/blob bytes；normalization 只对存在且 non-null 的 base 执行 `set_null`、对存在且 non-null 的 diff 执行 `delete`，absent/null shape 原样保留；authorization ID 从 canonical request/attestation digests 确定性派生，`migration_id` 从 authorization/source/path/policy closed inputs 派生且 CLI 不可选；request/attestation/IDs/derived/record 依赖严格单向，任一 canonical digest 不含自身或下游 digest；重放/摘要/marker/record cross-binding、非白名单差异与跨 scope 复用均 block | Verify: `python3 -m pytest -q tests/test_review_migration.py tests/test_specrail_schema.py -k "scope or git_blob or normalization or absent_base or migration_base or head_identity or authorization_id or migration_id or request_digest or attestation or self_hash or replay or tamper or reuse"` | Covers: B-001 B-002 B-003 B-004 B-005 B-007 B-015 B-016 B-018 B-019 B-024 | Git 命令使用参数数组，source/record 同提交重算不能过。
- [ ] `SP197-T2` Owner: migration-auth-cli | Depends on: SP197-T1 | Done when: 新增 `checks/github_review_migration_evidence.py`，fresh 双读 GitHub authorization comment、actor `maintain|admin` permission、repository immutable ID、PR base/head 与 default-base migration cutoff；comment `createdAt`/`updatedAt` 两次逐项稳定且 `createdAt=updatedAt=authorized_at`，收集前编辑也拒绝；`github_pr_evidence.py` 仅薄委托且保持 ≤800 行；CLI dry-run 只输出发布前可完整构造的 provider-bound `authorization_request`，目标路径先由稳定 path seed 派生，request 另绑定 manifest pre/result/entry digests，不含 comment 自身元数据、authorization/migration ID 或 derived/record digest；`--apply` 强制查询远端 exact decision并产生独立 `provider_attestation`，从 request/attestation digests 派生 authorization ID、再派生 migration ID 后才生成 derived 与 record receipt；拒绝本地 authorization/role map/actor/source 自证及 provider/comment/identity 漂移；source commit 必须是 `authorized_pr_head_sha` ancestor，`migration_base_sha` 只绑定 registry cutoff；`migrated_at=authorized_at`，record digest 对最终 bytes 外部重算，partial state fail closed、exact retry/reapply 幂等 | Verify: `python3 -m pytest -q tests/test_github_review_migration_evidence.py tests/test_review_migration.py tests/test_github_pr_evidence.py -k "provider or permission or comment or created_at or updated_at or precollection_edit or dry_run or request_digest or attestation or self_hash or migration_base or head_identity or ancestry or authorization_id or migration_id or rollback"` | Covers: B-002 B-003 B-007 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-019 B-023 B-024 | 工具不改 manifest；GitHub/provider 不可用时 fail closed。
- [ ] `SP197-T3` Owner: trusted-loader-terminal | Depends on: SP197-T1 SP197-T2 | Done when: generic closed registry schema 与 repo overlay `.specrail/review_legacy_round1_registry.json` 绑定 `terminal_attestation_key_id`，private HMAC key 只从 secret manager/env 取得；adapter/PR gate 只从 trusted `migration_base_sha` 的固定 path 加载 registry，校验 repo/cutoff/provider snapshot、expected identity exact-set 与 source Git objects；registry-covered PR 的 entries 与 loaded manifest lineage 做 artifact/source anchors 双向 one-to-one coverage，changed artifact_id、missing/duplicate/extra/subset lineage 在 origin 分类前拒绝；manifest v2 `migrations[]` + verifier 接入 loader；post-apply terminal provider 绑定 `authorized_pr_head_sha=H`、fresh `result_pr_head_sha=H'`、`result_pr_tree_oid`，要求 H strict ancestor H'，H..H' 每个 commit 及最终 tree 只改 derived/record/manifest 三路径且 digest/status exact；protected adapter 对 canonical terminal envelope 计算 HMAC-SHA256，offline `pr_gate.py` 在任何 auth reload 前验证 key ID/MAC，schema-valid 自洽伪造 envelope、缺 key/provider/MAC 全部 block | Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_github_review_migration_evidence.py tests/test_pack_asset_validation.py tests/test_review_result_semantics.py tests/test_review_migration.py tests/test_pr_gate_terminal.py -k "legacy_registry or lineage_coverage or changed_artifact_id or missing_lineage or duplicate_lineage or result_head or result_tree or migration_delta or terminal_mac or forged_envelope or key_id or trusted_reload"` | Covers: B-006 B-007 B-008 B-009 B-011 B-013 B-015 B-016 B-020 B-021 B-022 B-023 B-026 | 同步 PR evidence/registry schemas、`skills/specrail-pr-gate/SKILL.md` 与 pack ownership；HMAC secret 不进 repo/evidence/CLI/log；native v1/v2 零改动。
- [ ] `SP197-T4` Owner: origin-gate | Depends on: SP197-T3 | Done when: `review_json_gate.py` 对 `native_creation` 新 round-1 bounded artifact 的 non-null base/diff block；`review_result_semantics.py`、schema、loader 与 tests 的 closed `artifact_origin` 统一为 `native_creation | trusted_legacy_candidate | migrated_legacy`，旧 `creation` 不设 alias 且拒绝；仅 registry pre-classification 可进入 legacy mode；#186 absent/null base shape 不被新增字段；registry lineage exact-cover 在 origin 前完成，native、legacy candidate 与 migrated artifact 路由不混淆 | Verify: `python3 -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py tests/test_review_migration.py -k "round1 or native_creation or origin_alias or legacy_classification or lineage_coverage or absent_base"` | Covers: B-005 B-006 B-010 B-018 B-020 B-025 B-026 | 不追溯未命中 trusted registry 的普通 artifact。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4 → T5`：record/marker/auth/legacy identity 是同一
  trust chain，禁止由并行 lane 在共享 schema/semantics 上各自猜测。

## 验证

- [ ] `SP197-T5` Owner: verification-owner | Depends on: SP197-T1 SP197-T2 SP197-T3 SP197-T4 | Done when: PR #181/#186/#193 真实形态 fixture 的迁移前 block 与迁移后通过 forward test 全绿；覆盖全部既有 finding、GH-213 roots、PR #206 roots，以及 PR #214 current roots：`discussion_r3664438034/3664529664` 的 H→H' exact tree delta、`discussion_r3664438037/3664529672` 的 forged self-consistent offline envelope、`discussion_r3664529676` 的 pre-collection edit、`discussion_r3664529680` 的 caller-chosen migration ID、`discussion_r3664529688` 的旧 `creation` spelling、`discussion_r3664529695` 的 changed artifact_id/missing/duplicate lineage；同时保留 stable request → attestation → authorization ID → migration ID → derived → record 的无循环构造；`skills/specrail-pr-gate` 与 authenticated terminal forward path 明确；full suite、all-specs、depth/diff 全绿且 checks 文件 `<800` 行 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 | exact-head 证据；不 reply/resolve hosted threads。

## Handoff Notes

- 当前仅交付 spec packet；实现与 #181/#186/#193 的实际迁移操作等待本 spec 合并。
- 迁移 apply 必须消费 GitHub fresh provider 返回的 exact
  `migrate_legacy_round1_once`；本地 authorization/role map、CLI actor/source、自报角色、
  queue/auto/cap/merge 授权均不得代执行。
- 原始 artifact 字节在任何阶段都不修改；回滚 = 删除派生文件 + 记录 + manifest 条目。
- source truth 来自授权前已存在且可达的 Git commit/path/blob bytes；当前工作树与 record
  自报 digest 不能替代。
- 授权构造顺序固定为 stable request → GitHub comment → provider attestation →
  authorization ID → deterministic migration ID → derived artifact → record receipt；
  禁止上游对象预含自身或下游摘要。
- `source_artifact_head_sha` 与 `authorized_pr_head_sha` 是不同 identity；
  `migration_base_sha` 必须持久化但不得作为 source ancestry 目标。
- `authorized_pr_head_sha=H` 是 pre-migration head；提交产物后的 H' 只进入 protected
  terminal envelope，必须由 H ancestor、exact tree delta 与 HMAC 共同证明。
- registry-covered PR 必须 registry entries ↔ loaded manifest lineage exact-cover；
  `artifact_origin` 唯一 native spelling 是 `native_creation`。
