# Tech Spec

## Linked Issue

GH-197

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":197,"complete":true,"paths":["checks/github_pr_evidence.py","checks/github_review_evidence.py","checks/review_migration.py","checks/review_result_semantics.py","checks/review_round_semantics.py","checks/review_json_gate.py","checks/pr_review_contract.py","schemas/pr_review_gate.schema.json","schemas/review_migration_authorization.schema.json","schemas/review_migration_record.schema.json","schemas/review_result.schema.json","tools/migrate_review_round1.py","skills/specrail-review-pr/SKILL.md","tests/test_github_pr_evidence.py","tests/test_review_migration.py","tests/test_review_result_semantics.py","tests/test_review_json_gate.py","tests/test_specrail_schema.py","CHANGELOG.md"],"spec_refs":["specs/GH197/product.md","specs/GH197/tech.md","specs/GH197/tasks.md"]}
-->

## Product Spec

见 `product.md`，实现 B-001..B-012；四条 active review root 固定映射为
`discussion_r3652956666 → B-005`、`discussion_r3652956667 → B-002/B-011`、
`discussion_r3652956670 → B-006`、`discussion_r3652956671 → B-011/B-012`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| v2 round 派生 | `checks/review_round_semantics.py:78-84` | round 1 的 `base_head_sha`/`diff_sha256` 非 null 直接 append error；`rounds[]` 逐字段与加载 artifact 比对（`checks/review_round_semantics.py:63-73`） | 存量 round-1 artifact 无法进入任何合法 v2 manifest，是本 bug 的直接拒绝点 |
| manifest v1/v2 路由 | `checks/review_result_semantics.py:551-567` | artifact 含 `round_policy_version`/`diff_sha256`/`round_cap_escalation` 任一字段时 v1 报 "migrate bounded rounds to v2"；v2 走 `validate_bounded_rounds()` | 两条路径都 block，形成无迁移出口的死锁 |
| bounded artifact 校验 | `checks/review_result_semantics.py:358-373` | 只对 `review_round >= 2` 要求 base/diff，round 1 非 null 值在 artifact 层不报错 | legacy 形态得以铸造的历史缺口；单文件层需保持与 manifest 层一致 |
| 单 artifact gate | `checks/review_json_gate.py:288-313` | bounded round >= 2 要求 base/diff；round 1 非 null 不拦截 | B-010 的实施点：新 artifact 在源头 block，停止继续产生 legacy 形态 |
| PR 终审合同 | `checks/pr_review_contract.py:55-98` | 从仓库安全路径重载 manifest，比对 trusted `round_audit` 与授权 | 迁移证据必须同样可信重载复核，不能信任 evidence 嵌入副本 |
| 内容绑定 | `checks/review_content_binding.py:34-50` | artifact 的 content binding 从仓库路径加载并校验 | 派生 artifact 逐字段复制 binding 字段，绑定语义不变，篡改仍可检出 |
| 稳定 rejection | `checks/rejection_items.py:46-70` | `make_item(category, subject, expected, found)` 生成稳定 item id | 未迁移形态的 rejection 必须可定位、可复现（B-008） |
| GH-167 合同 | `specs/GH167/tech.md:135` | 明确"既有多轮流首次迁移到 v2 时显式 block"是预期行为，但未定义迁移载体 | 本规格补齐该合同缺口，不推翻 GH-167 语义 |
| 外部 maintainer 授权 | `checks/github_review_evidence.py:236-404` | 已有 closed role map 与 exact `continue_once` 授权 loader；自由 actor/source 不构成授权 | 复用同一 role-map trust boundary，新增独立 migration decision/fields，不能把 cap/merge 授权当迁移授权 |
| artifact schema | `schemas/review_result.schema.json:269-277` | `base_head_sha` 可为 null；`diff_sha256` 若存在只能是 64 hex，不能为 null | 派生规则必须删除 `diff_sha256` 而非写 null；schema 只新增 closed provenance marker |

## 设计方案

### 1. 迁移合同 `legacy_round1_normalization_v1`

受理域收窄为唯一形态：`round_policy_version: 1` 且 `review_round: 1` 且
`base_head_sha`/`diff_sha256` 至少一个非 null 的已持久化 artifact（PR #181/#186/#193
的真实形态）。其余一律拒绝：round >= 2 缺字段属于证据缺陷不可补造；非 bounded
artifact 走 v1 原路径；字段已全 null 的 artifact 无需迁移。

### 2. 派生 artifact 与迁移记录

迁移不触碰原文件，只新增两个文件（默认与源同目录）：

- 派生 artifact `<name>.migrated.json`：源 JSON 的规范化序列（UTF-8、排序键、
  紧凑分隔符）中，仅把 `base_head_sha` 置 null、删除 `diff_sha256`，并新增 closed
  `migration_provenance` marker；`artifact_id` 与其余全部字段等价复制，round-2 的
  `prior_findings[].source_artifact_id` 引用因此保持有效。删除而非写 null 是因为
  `review_result.schema.json` 的 optional `diff_sha256` 只接受 64 hex；round audit 通过
  `.get()` 仍派生 null。marker closed shape：

```text
migration_id, authorization_id, source_artifact_id, source_sha256,
source_git_commit_sha, source_git_blob_oid
```
- 迁移记录 `<name>.migration.json`，新增闭集 schema
  `schemas/review_migration_record.schema.json`：

```json
{
  "migration_version": 1,
  "migration_id": "MIG-181-round1",
  "source_artifact_path": ".../round1.json",
  "source_sha256": "<64hex>",
  "source_git_commit_sha": "<40hex>",
  "source_git_blob_oid": "<git-object-id>",
  "derived_artifact_path": ".../round1.migrated.json",
  "derived_sha256": "<64hex>",
  "target": {"manifest_version": 2, "round_policy": {"name": "bounded_diff_v1", "cap": 3}},
  "normalizations": [
    {"field": "base_head_sha", "operation": "set_null", "original_value": "<40hex>"},
    {"field": "diff_sha256", "operation": "delete", "original_value": "<64hex>"}
  ],
  "reason": "pre_v2_round1_bounded_fields",
  "authorization_id": "MRA-181-round1",
  "migrated_at": "<ISO-8601>"
}
```

`normalizations[]` 的 field/operation 对闭集为
`base_head_sha/set_null | diff_sha256/delete`；`original_value` 必须等于源值且源值
非 null；源值为 null/缺失的字段禁止出现，非 null 字段缺声明即 block（B-005）。
`reason` 目前唯一合法值为 `pre_v2_round1_bounded_fields`。

### 3. 确定性重放验证（不可伪造核心）

新模块 `checks/review_migration.py` 提供 `verify_migration_record()`：

1. 用参数数组执行 `git cat-file -e <source_git_commit_sha>^{commit}`、
   `git merge-base --is-ancestor <source_git_commit_sha> <migration_base_sha>` 与
   `git show <source_git_commit_sha>:<source_artifact_path>`；commit 必须在授权前已存在且
   可达，返回 blob OID/原始 bytes 必须分别等于授权和记录的
   `source_git_blob_oid`/`source_sha256`，当前 source 文件 bytes 也必须相等（B-002）。
2. 从该 Git blob bytes 按同一规范化算法与 `normalizations[]` 重放派生结果，注入与
   exact authorization 一致的 closed `migration_provenance`，重放摘要必须
   同时等于 `derived_sha256` 与派生文件实际摘要（B-004）。
3. 校验记录/授权 schema 闭集、受理域、authorization consumption 与全部 cross-binding
   （B-001/B-003/B-005/B-011/B-012）。

因为派生结果由源字节函数式决定，调用方对 finding、head、时间或任何非白名单
字段的增删改都会导致重放失配；同时篡改 source 和记录也会与迁移前 Git blob 及外部
authorization 失配。路径解析复用 `specrail_lib.resolve_path` 仓库安全路径，Git 命令
使用参数数组，拒绝越界、symlink、不可达 commit 与非 blob object。

### 4. manifest v2 `migrations[]` 与 loader 路由

manifest v2 增加可选闭集 `migrations[]`，每项 `{artifact_id, record_path}`；同时，
`github_pr_evidence.py` 的受保护 adapter 从 fresh PR/Git truth 收集 closed
`legacy_review_artifacts[]`：

```text
repo_id, pr, artifact_id, base_sha, head_sha, source_artifact_path,
source_git_commit_sha, source_git_blob_oid, source_sha256,
adapter_run_id, provider_as_of
```

该集合由 exact Git object bytes 派生并进入 PR evidence 的 closed schema；
caller/manifest 不能自报或删减。loader 接口对启用 GH197 migration 的 PR 强制接收同一
verified 集合，不提供 optional/default empty 降级。`github_pr_evidence.py` 还输出由
role-map loader 规范化的 closed `review_migration_authorizations[]`；PR schema 和
`pr_review_contract.py` 要求每个 legacy identity 使用的 authorization 与该数组 exact
匹配，manifest/record 嵌入副本不自证权限：

- `load_review_manifest()`（`checks/review_result_semantics.py:424`）在
  `validate_bounded_rounds()` 前解析 `migrations[]`：逐条 `verify_migration_record()`，
  并要求 `derived_artifact_path` 恰为该 `artifact_id` 在 lane `artifact_paths`
  中加载的路径；重复条目、未知 artifact_id、记录指向的路径与 manifest 不一致
  均 block（B-006/B-007）。
- 对每个 loaded round-1 artifact，以 `(repo_id, pr, artifact_id, head_sha)` 匹配 verified
  legacy identity；命中时必须同时存在唯一 `migrations[]` 条目、marker、record 与 exact
  authorization。换路径、手工 normalized copy、删除 marker/条目或冒充 native artifact
  都仍命中 identity 并 block（B-006）。
- 通过验证后按现有 v2 语义评估派生 artifact；round 派生、carry、escalation
  逻辑零改动（B-009）。
- 未迁移的 legacy 形态触发 `validate_bounded_rounds()` 的 round-1 非 null 错误时，
  loader 检测该 artifact 满足受理域且无对应 `migrations[]` 条目，则替换为稳定
  rejection：category `legacy_round1_migration_required`、subject 为 artifact_id、
  expected 指向本合同（B-008）。相同输入产生相同 items，`pr_gate.py` 直接透传。
- trusted reload：`checks/pr_review_contract.py` 复核 `round_audit` 时同样从仓库
  安全路径重载并以 protected adapter 的同一 legacy identity/auth 集合重验
  `migrations[]`，evidence 嵌入或 manifest 自报副本不参与信任（B-009）。

### 5. 源头封口

`checks/review_json_gate.py::_validate_review_round` 增加：bounded 且
`review_round == 1` 时 `base_head_sha` 与 `diff_sha256` 必须缺失或为 null，否则
block（B-010）。该 gate 只在 artifact 产出时运行，不追溯存量文件；
`checks/review_result_semantics.py:358-373` 的 artifact 层校验同步补齐同一规则，
两处共享常量避免漂移。

### 6. CLI：`tools/migrate_review_round1.py`

```
python3 tools/migrate_review_round1.py --repo . \
  --artifact <path> --pr <number> --migration-base <sha> \
  [--authorization <json> --maintainer-role-map <json> --apply]
```

- 默认 dry-run：从 pre-migration Git object 打印受理域、将写入路径、source/derived/
  policy digests 与完整 authorization candidate，不落盘（B-011）。
- `schemas/review_migration_authorization.schema.json` 的 exact decision shape：

```text
authorization_id, decision = migrate_legacy_round1_once,
repo_id, pr, artifact_id, base_sha, head_sha, source_artifact_path,
source_git_commit_sha, source_git_blob_oid, source_sha256,
derived_artifact_path, derived_sha256, target_policy_digest,
actor, source, authorized_at
```

  `checks/github_review_evidence.py` 复用 closed maintainer role map 验证 actor，并拒绝
  CLI 自报角色、cap/merge 授权、错 scope、未知字段和重复 ID。
- `--apply` 强制加载 authorization + role map；exact fields/digests 全匹配后，先将
  派生与 record 写入同目录 temp、fsync，再按 authorization ID 派生的唯一目标路径
  create-only publish；任何只发布一侧的中断状态均不被 loader 接受，retry 只能补全同一
  exact bytes。已存在同 ID 只在 record/derived bytes 完全相同时作为 response-loss retry；
  写后自验 `verify_migration_record()`；
  自验失败删除新写文件并非零退出。manifest `migrations[]` 条目由操作者按 dry-run
  输出显式加入，工具不改 manifest。
- 同一 exact authorization 的 response-loss retry 只返回既有同 digest 文件/record；
  任一 bytes 不同或跨 PR/base/head/artifact/source/derived scope 均 block；rollback
  后的 exact reapply 可重新发布相同 bytes。记录的 actor/source/time 只来自授权，因此
  相同授权输出逐字节确定（B-012）。

### 7. 回滚与兼容

删除派生 artifact、迁移记录与 manifest `migrations[]` 条目即回到迁移前状态：
legacy artifact 原样保留并继续 fail closed（B-012）。v1 单轮证据、既有 v2 合法
manifest、GH-167 全部语义零改动；`migrations[]` 缺省为空列表时行为与现状一致。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-005 | 受理域 + set-null/delete normalization 白名单 | `python3 -m pytest -q tests/test_review_migration.py -k "scope or normalization or diff_field"` |
| B-002 B-004 B-007 | pre-migration Git blob anchor + 摘要绑定与确定性重放 | `python3 -m pytest -q tests/test_review_migration.py -k "git_blob or replay or tamper or reuse"` |
| B-003 B-006 | record/marker schema + trusted legacy identity + manifest `migrations[]` | `python3 -m pytest -q tests/test_review_migration.py tests/test_review_result_semantics.py -k "record or provenance or legacy_identity or manifest"` |
| B-008 B-009 | loader 路由与稳定 rejection、trusted reload | `python3 -m pytest -q tests/test_review_result_semantics.py -k migration` |
| B-010 | 单 artifact gate 源头封口 | `python3 -m pytest -q tests/test_review_json_gate.py -k round1` |
| B-011 B-012 | role-mapped exact authorization + CLI dry-run/apply/幂等/回滚 | `python3 -m pytest -q tests/test_review_migration.py tests/test_github_pr_evidence.py -k "migration_authorization or cli or rollback or replay"` |

## 数据流

`protected adapter: pre-migration commit/path → Git blob + legacy identity →
CLI dry-run authorization candidate → maintainer role-map exact decision →
--apply consumes authorization → marker-bearing derived artifact + record →
manifest v2 migrations[] → loader: legacy identity + auth + Git blob replay →
validate_bounded_rounds() → pr_review_contract trusted reload → pr_gate`。
任一层验证失败均 fail closed，未迁移/手工复制形态得到指向本合同的稳定 rejection。

## 备选方案

- 就地改写旧 artifact 把字段置 null：破坏不可变审查证据与摘要，拒绝。
- 放宽 `validate_bounded_rounds()` 允许 round-1 非 null base/diff：等于让全部
  新 artifact 永久携带无法验证的字段，掩盖 GH-167 修复的缺口，拒绝。
- 按 artifact 时间戳自动豁免"历史文件"：时间可自报、不可信，拒绝。
- 手工复制删字段、不留记录：与任意篡改不可区分，拒绝。
- 只在派生 artifact 加自报 marker：调用方仍可省略 marker 冒充 native artifact，拒绝；
  必须由 protected adapter 的 legacy identity 强制要求 marker/record。
- 让同一提交里的 record 自报 `source_sha256`：source 与 record 可一起篡改，拒绝；
  必须绑定迁移前可达 Git commit/blob 和外部 exact authorization。
- 在 evidence JSON 里内嵌迁移证明：嵌入副本不可信，必须仓库安全路径重载，拒绝。
- 用 `implx auto` 授权批量迁移：违反 issue 非目标，人工 actor 不可代填，拒绝。

## 风险

- Security: 记录与派生文件路径经 repo 安全解析；迁移前 Git blob 与 role-mapped exact
  authorization 共同构成信任根，所有 Git 命令使用参数数组，无 shell 拼接。
- Compatibility: `migrations[]` 可选且缺省为空；v1、既有 v2、GH-167 语义零改动。
  首次部署后 #181/#186/#193 需一次人工迁移，这是预期操作而非回归。
- Correctness: 规范化序列算法必须单一实现并被 CLI 与验证方共享，防止重放漂移；
  测试覆盖键序、Unicode、嵌套结构。
- Data integrity: Git blob/source/derived 声明/derived 实际摘要 + marker + 逐字段
  normalization + legacy identity，防止丢字段、改字段、手工复制与记录复用。
- Operations: dry-run 先产出 exact candidate，maintainer 再授权；授权的
  `authorized_at`/actor/source 与 apply 的 `migrated_at` 使审计可追。
- Maintenance: 新逻辑集中在 `checks/review_migration.py`；
  `checks/review_result_semantics.py`（当前 702 行）只增薄路由，实现后
  `wc -l` 断言相关文件均小于 800 行。

## 测试计划

- [ ] Unit: 受理域、set-null/delete 白名单、record/authorization/marker schemas、
  pre-migration Git blob、重放算法（含键序/Unicode/嵌套）、摘要失配、记录复用。
- [ ] Integration: PR #181/#186/#193 三种真实形态的迁移前 block（稳定 rejection）
  与迁移后全链路通过；篡改派生文件、替换源文件、同提交重算 source digest、
  手工 copy 省略 marker/record、manifest 条目缺失/重复负例；`pr_review_contract`
  以 trusted legacy identity/auth 复核。
- [ ] CLI: dry-run 无副作用；apply 缺/错 role-mapped authorization、错 commit/blob/
  source/derived scope、重复 ID 拒绝；exact retry 幂等；自验失败清理。
- [ ] Full: `python3 -m pytest -q`、`python3 checks/check_workflow.py --repo .
  --all-specs`、`python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate`、
  `git diff --check`。

## 回滚方案

回滚实现即删除 migration 模块/CLI/schema 与 loader 路由；已生成的派生 artifact
与记录会被回滚后的 loader 当作普通 v2 输入中的未知形态拒绝，不会静默放行。
运维层回滚只需删除派生 artifact、迁移记录与 manifest `migrations[]` 条目，
原始 artifact 从未被改动，队列回到迁移前的 fail-closed 状态。
