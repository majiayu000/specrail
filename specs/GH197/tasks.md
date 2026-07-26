# Task Plan

## Linked Issue

GH-197

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP197-T1` Owner: migration-core | Depends on: approved spec | Done when: `checks/review_migration.py` + `schemas/review_migration_record.schema.json` 落地；受理域（仅 round-1 bounded 非 null 形态）、闭集 record、normalization 白名单、三重摘要与确定性重放全覆盖，非白名单差异与记录复用均 block | Verify: `python3 -m pytest -q tests/test_review_migration.py -k "scope or normalization or record or replay or tamper or reuse"` | Covers: B-001 B-002 B-003 B-004 B-005 B-007 | 新增共享验证模块与 schema。
- [ ] `SP197-T2` Owner: migration-cli | Depends on: SP197-T1 | Done when: `tools/migrate_review_round1.py` 默认 dry-run 无副作用、`--apply` 原子写 + 写后自验 + 失败清理、`--actor`/`--source` 必填、重复 apply 逐字节幂等 | Verify: `python3 -m pytest -q tests/test_review_migration.py -k "cli or rollback"` | Covers: B-011 B-012 | 工具不改 manifest。
- [ ] `SP197-T3` Owner: loader-routing | Depends on: SP197-T1 | Done when: manifest v2 `migrations[]` 解析 + `verify_migration_record()` 接入 `load_review_manifest()`；未迁移 legacy 形态产出稳定 `legacy_round1_migration_required` rejection；迁移后按既有 v2 语义评估；`pr_review_contract.py` trusted reload 复核 | Verify: `python3 -m pytest -q tests/test_review_result_semantics.py -k migration` | Covers: B-006 B-008 B-009 | v1 与既有 v2 行为零改动。
- [ ] `SP197-T4` Owner: origin-gate | Depends on: SP197-T1 | Done when: `review_json_gate.py` 与 `review_result_semantics.py` 对新产出 round-1 bounded artifact 的非 null base/diff 一致 block，规则常量共享 | Verify: `python3 -m pytest -q tests/test_review_json_gate.py -k round1` | Covers: B-010 | 不追溯存量文件。

## 并行拆分

- T1 先行；T2/T3/T4 可并行，文件集互不重叠（T2: tools/，T3: semantics/contract，T4: json gate）。

## 验证

- [ ] `SP197-T5` Owner: verification-owner | Depends on: SP197-T1 SP197-T2 SP197-T3 SP197-T4 | Done when: PR #181/#186/#193 真实形态 fixture 的迁移前 block 与迁移后通过 forward test 全绿；full suite、all-specs、depth gate、`git diff --check` 全绿且相关 checks 文件 `wc -l < 800` | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 | exact-head 证据。

## Handoff Notes

- 当前仅交付 spec packet；实现与 #181/#186/#193 的实际迁移操作等待本 spec 合并。
- 迁移 apply 是显式人工动作（actor/source 必填）；queue/auto 不得代执行。
- 原始 artifact 字节在任何阶段都不修改；回滚 = 删除派生文件 + 记录 + manifest 条目。
