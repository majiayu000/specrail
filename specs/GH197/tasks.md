# Task Plan

## Linked Issue

GH-197

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP197-T1` Owner: migration-core | Depends on: approved spec | Done when: `checks/review_migration.py`、record/authorization schemas 与 `review_result.schema.json` closed `migration_provenance` marker 落地；受理域仅 round-1 bounded legacy；source 必须同时匹配迁移前可达 Git commit/path/blob bytes、record 与 exact authorization；normalization 只允许 base `set_null`、diff `delete`；重放/摘要/marker/record cross-binding、非白名单差异与记录复用均 block | Verify: `python3 -m pytest -q tests/test_review_migration.py tests/test_specrail_schema.py -k "scope or git_blob or normalization or diff_field or provenance or record or replay or tamper or reuse"` | Covers: B-001 B-002 B-003 B-004 B-005 B-007 | Git 命令使用参数数组，source/record 同提交重算不能过。
- [ ] `SP197-T2` Owner: migration-auth-cli | Depends on: SP197-T1 | Done when: `github_review_evidence.py` 复用 closed maintainer role map 验证 `migrate_legacy_round1_once` exact authorization；`tools/migrate_review_round1.py` dry-run 只输出 authorization candidate，`--apply` 强制加载授权+role map并匹配 repo/PR/fresh base/head/artifact/commit/blob/source/derived/policy，source commit 必须是授权 base 的 ancestor；create-only 写入且 partial state fail closed、exact response-loss retry/rollback reapply 幂等；CLI actor/source、cap/merge/auto 授权、错 scope 或同 ID 不同 bytes 均拒绝 | Verify: `python3 -m pytest -q tests/test_review_migration.py tests/test_github_pr_evidence.py -k "migration_authorization or cli or role_map or ancestry or replay or rollback"` | Covers: B-002 B-003 B-011 B-012 | 工具不改 manifest。
- [ ] `SP197-T3` Owner: trusted-loader-routing | Depends on: SP197-T1 SP197-T2 | Done when: protected `github_pr_evidence.py` adapter 从 fresh PR/Git truth 输出 closed `legacy_review_artifacts[]`，caller 不可自报；manifest v2 `migrations[]` + `verify_migration_record()` 接入 loader；命中 `(repo_id,pr,artifact_id,head_sha)` 的 legacy identity 时 marker/record/auth/entry 全部 mandatory，手工 copy/改路径/省略 marker 仍 block；未迁移形态稳定 `legacy_round1_migration_required`，迁移后按既有 v2 语义；`pr_review_contract.py` 用同一 trusted identity/auth reload | Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_review_result_semantics.py tests/test_review_migration.py -k "legacy_identity or migration or provenance or trusted_reload"` | Covers: B-006 B-007 B-008 B-009 B-011 | 同步 `pr_review_gate.schema.json`，v1 与既有 native v2 零改动。
- [ ] `SP197-T4` Owner: origin-gate | Depends on: SP197-T3 | Done when: `review_json_gate.py` 与 `review_result_semantics.py` 对新产出 round-1 bounded artifact 的非 null base/diff 一致 block，规则常量共享；派生 artifact 的 `diff_sha256` 删除后仍通过现有 optional-string schema，native artifact 与 marker-bearing migrated artifact 路由不混淆 | Verify: `python3 -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py -k "round1 or migration"` | Covers: B-005 B-006 B-010 | 不追溯存量文件。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4 → T5`：record/marker/auth/legacy identity 是同一
  trust chain，禁止由并行 lane 在共享 schema/semantics 上各自猜测。

## 验证

- [ ] `SP197-T5` Owner: verification-owner | Depends on: SP197-T1 SP197-T2 SP197-T3 SP197-T4 | Done when: PR #181/#186/#193 真实形态 fixture 的迁移前 block 与迁移后通过 forward test 全绿；逐项证明 `discussion_r3652956666` 的 diff 字段删除可过现有 schema、`discussion_r3652956667` 的 pre-migration Git blob/authorization anchor、`discussion_r3652956670` 的 trusted legacy identity + mandatory marker/record、`discussion_r3652956671` 的 external role-mapped exact authorization；覆盖同提交重算 source digest、手工 copy/改路径、省略 marker/entry、CLI 自报 actor、错 role/scope/重复 auth、response-loss retry；full suite、all-specs、depth/diff 全绿且 checks 文件 `<800` 行 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 | exact-head 证据；不 reply/resolve hosted threads。

## Handoff Notes

- 当前仅交付 spec packet；实现与 #181/#186/#193 的实际迁移操作等待本 spec 合并。
- 迁移 apply 必须消费 exact `migrate_legacy_round1_once` + explicit maintainer role map；
  CLI actor/source、自报角色、queue/auto/cap/merge 授权均不得代执行。
- 原始 artifact 字节在任何阶段都不修改；回滚 = 删除派生文件 + 记录 + manifest 条目。
- source truth 来自授权前已存在且可达的 Git commit/path/blob bytes；当前工作树与 record
  自报 digest 不能替代。
