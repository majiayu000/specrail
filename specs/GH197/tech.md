# Tech Spec

## Linked Issue

GH-197

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":197,"complete":true,"paths":[".specrail/review_legacy_round1_registry.json","CHANGELOG.md","checks/github_pr_evidence.py","checks/github_review_evidence.py","checks/github_review_migration_evidence.py","checks/pack_asset_validation.py","checks/pr_gate.py","checks/pr_review_contract.py","checks/rejection_items.py","checks/review_json_gate.py","checks/review_migration.py","checks/review_result_semantics.py","checks/review_round_semantics.py","schemas/pr_review_gate.schema.json","schemas/review_legacy_registry.schema.json","schemas/review_migration_authorization.schema.json","schemas/review_migration_record.schema.json","schemas/review_result.schema.json","skills/specrail-pr-gate/SKILL.md","skills/specrail-review-pr/SKILL.md","tests/test_github_pr_evidence.py","tests/test_github_review_migration_evidence.py","tests/test_pack_asset_validation.py","tests/test_pr_gate_terminal.py","tests/test_review_json_gate.py","tests/test_review_migration.py","tests/test_review_result_semantics.py","tests/test_specrail_schema.py","tools/migrate_review_round1.py"],"spec_refs":["specs/GH197/product.md","specs/GH197/tech.md","specs/GH197/tasks.md"]}
-->

## Product Spec

见 `product.md`，实现 B-001..B-026；既有四条 active review root 固定映射为
`discussion_r3652956666 → B-005`、`discussion_r3652956667 → B-002/B-011`、
`discussion_r3652956670 → B-006`、`discussion_r3652956671 → B-011/B-012`；
GH-213 三条依次映射 B-013、B-014、B-015；PR #206 current roots
`discussion_r3660108740/8753/8770/8782/8797` 依次映射
B-016/B-017/B-018/B-019/B-020。PR #214 current hosted roots 映射为：
`discussion_r3664438034`、`discussion_r3664529664 → B-021`；
`discussion_r3664438037`、`discussion_r3664529672 → B-022`；
`discussion_r3664529676 → B-023`、`discussion_r3664529680 → B-024`、
`discussion_r3664529688 → B-025`、`discussion_r3664529695 → B-026`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| v2 round 派生 | `checks/review_round_semantics.py:78-84` | round 1 的 `base_head_sha`/`diff_sha256` 非 null 直接 append error；`rounds[]` 逐字段与加载 artifact 比对（`checks/review_round_semantics.py:63-73`） | 存量 round-1 artifact 无法进入任何合法 v2 manifest，是本 bug 的直接拒绝点 |
| manifest v1/v2 路由 | `checks/review_result_semantics.py:551-567` | artifact 含 `round_policy_version`/`diff_sha256`/`round_cap_escalation` 任一字段时 v1 报 "migrate bounded rounds to v2"；v2 走 `validate_bounded_rounds()` | 两条路径都 block，形成无迁移出口的死锁 |
| bounded artifact 校验 | `checks/review_result_semantics.py:358-373` | 只对 `review_round >= 2` 要求 base/diff，round 1 非 null 值在 artifact 层不报错 | legacy 形态得以铸造的历史缺口；单文件层需保持与 manifest 层一致 |
| 单 artifact gate | `checks/review_json_gate.py:288-313` | bounded round >= 2 要求 base/diff；round 1 非 null 不拦截 | B-010 的实施点：新 artifact 在源头 block，停止继续产生 legacy 形态 |
| PR 终审合同 | `checks/pr_review_contract.py:55-98` | 从仓库安全路径重载 manifest，比对 trusted `round_audit` 与授权 | 迁移证据必须同样可信重载复核，不能信任 evidence 嵌入副本 |
| offline terminal gate | `checks/pr_gate.py:1-4` | gate 明确只消费本地 evidence，provider adapter 与 evaluator 分离 | caller 可伪造未认证 envelope；migration terminal evidence 必须增加 keyed authenticity，普通 evidence digest 不构成信任根 |
| 内容绑定 | `checks/review_content_binding.py:34-50` | artifact 的 content binding 从仓库路径加载并校验 | 派生 artifact 逐字段复制 binding 字段，绑定语义不变，篡改仍可检出 |
| 稳定 rejection | `checks/rejection_items.py:46-70` | `make_item(category, subject, expected, found)` 生成稳定 item id | 未迁移形态的 rejection 必须可定位、可复现（B-008） |
| GH-167 合同 | `specs/GH167/tech.md:135` | 明确"既有多轮流首次迁移到 v2 时显式 block"是预期行为，但未定义迁移载体 | 本规格补齐该合同缺口，不推翻 GH-167 语义 |
| caller role map | `checks/github_review_evidence.py:236-282` | `load_maintainer_role_map()` 只校验调用方 JSON 的闭集 shape，无法证明 actor 的真实仓库权限 | migration authorization 不得复用该输入作为信任根；它只可用于其它现有合同 |
| fresh PR identity | `checks/github_pr_evidence.py:68-72`、`checks/github_pr_evidence.py:448-514` | collector 已双读 GitHub PR view 并绑定 `baseRefOid`/`headRefOid`，主文件已达 800 行 | 新 migration provider 使用独立 helper，复用双读模式并保持主文件 one-in-one-out |
| loader 验证顺序 | `checks/review_result_semantics.py:424-525` | `load_review_manifest()` 先对 lane artifact 调用通用 `validate_review_artifact()`，之后才进入 bounded-round 派生 | trusted legacy identity 必须在 origin 规则前分类，否则稳定 migration rejection 不可达 |
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
  紧凑分隔符）中，仅在 `base_head_sha` 存在且 non-null 时将其置 null，仅在
  `diff_sha256` 存在且 non-null 时删除该字段，并新增 closed
  `migration_provenance` marker；`artifact_id` 与其余全部字段等价复制，round-2 的
  `prior_findings[].source_artifact_id` 引用因此保持有效。删除而非写 null 是因为
  `review_result.schema.json` 的 optional `diff_sha256` 只接受 64 hex；round audit 通过
  `.get()` 仍派生 null。marker closed shape：

```text
migration_id, authorization_id, source_artifact_id, source_sha256,
source_artifact_head_sha, authorized_pr_head_sha, migration_base_sha,
source_git_commit_sha, source_git_blob_oid, authorization_provider_snapshot_sha256
```
- 迁移记录 `<name>.migration.json`，新增闭集 schema
  `schemas/review_migration_record.schema.json`：

```json
{
  "migration_version": 1,
  "migration_id": "MIG-181-round1",
  "source_artifact_path": ".../round1.json",
  "source_sha256": "<64hex>",
  "source_artifact_head_sha": "<40hex>",
  "authorized_pr_head_sha": "<40hex>",
  "authorized_pr_base_sha": "<40hex>",
  "migration_base_sha": "<40hex>",
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
  "authorization_id": "MRA-<canonical-scope-sha256>",
  "authorization_sha256": "<64hex>",
  "authorization_provider_snapshot_sha256": "<64hex>",
  "migrated_at": "<ISO-8601>"
}
```

`normalizations[]` 的 field/operation 对闭集为
`base_head_sha/set_null | diff_sha256/delete`；`original_value` 必须等于源值且源值
非 null；源值为 null/缺失的字段禁止出现，非 null 字段缺声明即 block（B-005）。
派生算法保留源字段的 absent/null 差异：#186 缺失 `base_head_sha` 时派生结果仍缺失，
禁止新增 `base_head_sha: null`（B-018）。`reason` 目前唯一合法值为
`pre_v2_round1_bounded_fields`。record/authorization 的
`source_artifact_head_sha`、`authorized_pr_head_sha`、`authorized_pr_base_sha` 与
`migration_base_sha` 均为不同语义的必填字段，不得折叠成 `head_sha/base_sha`
（B-015/B-016）。`authorization_sha256` 是最终 closed authorization envelope 的
外部 canonical digest；record 作为 apply receipt 包含该值与 `derived_sha256`，但不
包含自己的 `record_sha256`，后者只能由 verifier/loader 对最终 record bytes 重算。
`migration_id` 不接受 CLI/request 字段，统一按下式在 authorization 完成后、派生 bytes
生成前计算，并由 marker/record verifier 重算（B-024）：

```text
MIG-SHA256(canonical({
  authorization_id, repo_id, pr, artifact_id, source_sha256,
  derived_artifact_path, record_path, manifest_path,
  target_policy_digest, normalization_plan_sha256
}))
```

### 3. 确定性重放验证（不可伪造核心）

新模块 `checks/review_migration.py` 提供 `verify_migration_record()`：

1. 用参数数组执行 `git cat-file -e <source_git_commit_sha>^{commit}`、
   `git merge-base --is-ancestor <source_git_commit_sha> <authorized_pr_head_sha>`
   （source 提交在
   受影响 PR 的历史中，不要求它是 default-branch cutoff 的 ancestor）与
   `git show <source_git_commit_sha>:<source_artifact_path>`；commit 必须在授权前已存在且
   可达，返回 blob OID/原始 bytes 必须分别等于授权和记录的
   `source_git_blob_oid`/`source_sha256`，当前 source 文件 bytes 也必须相等。
   source artifact 内的 `head_sha` 必须等于 `source_artifact_head_sha`；apply 前
   fresh provider PR head 必须等于 `authorized_pr_head_sha = H`，二者允许不同。
   committed migration 的 terminal gate 另按第 7 节验证 `result_pr_head_sha = H'`，
   不再把 post-apply current head 错误地要求等于 H。`migration_base_sha`
   只与 trusted registry cutoff/default-base snapshot 比较，不参与 source ancestry
   （B-002/B-015/B-016/B-017）。
2. 从该 Git blob bytes 按同一规范化算法与 `normalizations[]` 重放派生结果，注入与
   exact authorization 一致的 closed `migration_provenance`，重放摘要必须
   同时等于 `derived_sha256` 与派生文件实际摘要（B-004）。
3. 校验记录/授权 schema 闭集、受理域、fresh authorization provider snapshot、
   deterministic authorization ID、deterministic migration ID 与全部 cross-binding
   （B-001/B-003/B-005/B-011..B-019/B-024）。

因为派生结果由源字节函数式决定，调用方对 finding、head、时间或任何非白名单
字段的增删改都会导致重放失配；同时篡改 source 和记录也会与迁移前 Git blob 及外部
authorization 失配。路径解析复用 `specrail_lib.resolve_path` 仓库安全路径，Git 命令
使用参数数组，拒绝越界、symlink、不可达 commit 与非 blob object。

### 4. manifest v2 `migrations[]` 与 loader 路由

manifest v2 增加可选闭集 `migrations[]`，每项 `{artifact_id, record_path}`。本仓库在
固定 conventional path `.specrail/review_legacy_round1_registry.json` 提供 closed
`review_legacy_registry`；PR gate/adapter 只能用 target base SHA 通过 `git show
<trusted_target_base>:.specrail/review_legacy_round1_registry.json` 加载，CLI/caller/
manifest 不能指定路径。registry 绑定：

```text
version, registry_id, repo_id, cutoff_base_sha, terminal_attestation_key_id,
coverage = expected_prs[], expected_identity_keys[], expected_entry_count,
           entries_digest, provider_snapshot_digest,
entries[] = pr, artifact_id, source_artifact_head_sha, source_artifact_path,
            source_git_commit_sha, source_git_blob_oid, source_sha256
```

validator 要求 `entries[]` 稳定排序、唯一，并重算 expected PRs/identity keys/count/
canonical entries digest；每个 source commit 必须可达且属于该 entry 所声明 PR 的历史——legacy artifact 通常就
提交在受影响的 open PR 分支上，其 `source_git_commit_sha` 在该 PR 历史中而**不是**
default-branch `cutoff_base_sha` 的 ancestor，因此不得用
`git merge-base --is-ancestor <source> <cutoff>` 作为通过条件（那会拒绝全部合法 source）。
判定改为：source commit 必须是该 entry 的 fresh
`authorized_pr_head_sha` 的 ancestor（`--is-ancestor <source>
<authorized_pr_head_sha>`），且该 PR 必须在 `migration_base_sha` 所绑定的 cutoff
provider snapshot 覆盖域内；entry 的 `source_artifact_head_sha` 只绑定 legacy
artifact 自身，不代替当前 PR head；
source 既不在 PR 历史也不在 cutoff 祖先链中时 fail closed。
blob/path/sha 必须匹配。registry 明确覆盖 PR #181/#186/#193 在 cutoff provider snapshot
中的全量已知 legacy identities；缺 registry、repo/cutoff/snapshot 不符、entries 子集/
多项或任一 coverage 派生字段漂移都 fail closed。generic schema 注册到 pack ownership，
repo-specific entries 留在 `.specrail` overlay，不硬编码进 evaluator。
`terminal_attestation_key_id` 只选择 protected runtime secret，不包含 secret 本身；
schema 拒绝缺失/未知 key ID，private key material 只能来自 secret manager/env
`SPECRAIL_MIGRATION_ATTESTATION_KEY`，不得进入仓库、CLI 参数、日志或 evidence。

`github_pr_evidence.py` 从该固定 registry + fresh PR/Git truth 产出 closed
`legacy_review_artifacts[]`：

```text
repo_id, pr, artifact_id, authorized_pr_base_sha, authorized_pr_head_sha,
migration_base_sha, source_artifact_head_sha, source_artifact_path,
source_git_commit_sha, source_git_blob_oid, source_sha256,
registry_id, registry_entries_digest, adapter_run_id, provider_as_of
```

该集合必须与 registry 中目标 PR 的 expected entries exact-set 相等并进入 PR evidence
closed schema；caller/manifest 不能自报、过滤、传空或选择 coverage scope。loader 对该
registry 覆盖的 PR 强制接收同一 non-empty verified 集合，不提供 optional/default empty
降级。除 adapter 集合自身 exact-set 外，loader 必须从已加载的 manifest
`artifact_paths`、round lineage 与 `migrations[]` 构造 `loaded_lineage_roots[]`，再与
目标 PR registry entries 做双向 one-to-one join：

```text
registry entry ↔ loaded source artifact or verified migrated derivative
join/cross-check = artifact_id, source_artifact_head_sha, source_artifact_path,
                   source_git_commit_sha, source_git_blob_oid, source_sha256
```

每个 registry entry 和 lineage root 的 join count 都必须为 1。先要求 registry 的原
artifact_id 在 lineage 中存在，再验证其它 anchors，禁止 changed artifact_id 的 copy
因 tuple miss 被分类为 native；missing/duplicate/extra/subset lineage 全部在 origin
classification 前 block（B-026）。

新增 `checks/github_review_migration_evidence.py` 使用 GitHub API/GraphQL
fresh 双读 authorization comment、repository immutable ID、PR base/head 与 actor
repository permission；只有 `maintain|admin` 权限的 actor 才能签发
`migrate_legacy_round1_once`。授权事件闭集限定为同仓库 GH-197 issue 上的单条
`IssueComment`：provider 以 node ID 取回 comment，要求 body 只含一个 closed
authorization JSON，且 REST collaborator permission 与 GraphQL comment actor 一致。
两次 read 都必须返回相同 `createdAt`/`updatedAt`，且
`createdAt == updatedAt == authorized_at`；因此收集前已编辑与收集中编辑都拒绝。
其它 issue/PR、跨仓库 URL、普通本地文件或多个候选 payload 均拒绝。
`github_pr_evidence.py` 只做薄委托，并输出 closed
`review_migration_authorizations[]` 与 provider snapshot；PR schema 和
`pr_review_contract.py` 要求每个 legacy identity 使用的 authorization 与该数组 exact
匹配。本地 authorization JSON、role map、actor/source CLI 字符串及
manifest/record 嵌入副本均不自证权限（B-013/B-014）：

- `load_review_manifest()`（`checks/review_result_semantics.py:424`）在调用通用
  `validate_review_artifact()` 的 origin rule 前，先用 trusted registry exact identity
  将 lane 分类为 `native_creation | trusted_legacy_candidate | migrated_legacy`。
  `trusted_legacy_candidate` 只延迟 round-1 origin rule，随后必须产生
  `legacy_round1_migration_required`；其它 schema/内容错误仍照常拒绝。
  `migrations[]` 在 `validate_bounded_rounds()` 前逐条 `verify_migration_record()`，
  并要求 `derived_artifact_path` 恰为该 `artifact_id` 在 lane `artifact_paths`
  中加载的路径；重复条目、未知 artifact_id、记录指向的路径与 manifest 不一致
  均 block（B-006/B-007）。
- 对每个 loaded round-1 artifact，以
  `(repo_id, pr, artifact_id, source_artifact_head_sha)` 匹配
  registry-derived legacy identity；命中时必须同时存在唯一 `migrations[]` 条目、
  marker、record 与 exact
  authorization。换路径、手工 normalized copy、删除 marker/条目或冒充 native artifact
  都仍命中 identity 并 block（B-006）。
- 对 registry-covered PR，先执行上述 registry ↔ loaded lineage one-to-one gate；
  registered artifact 缺失、artifact_id 被改、同一 root 重复加载、一个 entry 映射多个
  derivative 或额外 lineage 均不得进入 `native_creation` 路由（B-026）。
- 通过验证后按现有 v2 语义评估派生 artifact；round 派生、carry、escalation
  逻辑零改动（B-009）。
- 未迁移且 registry 命中的 legacy 形态在通用 origin rule 前即分类；无对应
  `migrations[]` 条目时只产生稳定
  rejection：category `legacy_round1_migration_required`、subject 为 artifact_id、
  expected 指向本合同（B-008/B-020）。该 category 当前不存在——
  `checks/rejection_items.py:18-27`
  的 `CATEGORIES` 是闭集且不含该值，构造会直接失败。因此 `checks/rejection_items.py`
  进入 planned changes，实现必须把 `legacy_round1_migration_required` 加入该闭集，并为
  新值补齐既有 category 的同等测试；未注册前 loader 不得改用近似 category 顶替，
  也不得降级为 warning。相同输入产生相同 items，`pr_gate.py` 直接透传。
- trusted reload：`checks/pr_review_contract.py` 复核 `round_audit` 时同样从仓库
  安全路径重载固定 base registry，并以同一 exact-set identity/auth/lineage 集合重验
  `migrations[]`；terminal authorization 只接受第 7 节 HMAC-authenticated envelope，
  evidence 嵌入或 manifest 自报的未认证副本不参与信任（B-009/B-022/B-026）。

### 5. 源头封口

`checks/review_json_gate.py::_validate_review_round` 增加：bounded 且
`review_round == 1` 时 `base_head_sha` 与 `diff_sha256` 必须缺失或为 null，否则
block（B-010）。`validate_review_artifact()` 增加显式闭集
`artifact_origin: native_creation | trusted_legacy_candidate | migrated_legacy`：
`native_creation` 应用同一 origin rule；legacy 两类只能由 loader 在 registry identity
预分类后传入，普通调用方不得选择。这样新 artifact 在源头被拒，而存量 candidate
仍能到达唯一稳定 migration rejection。旧 `creation` 不设 alias/normalization，
schema 与 validator 直接拒绝（B-020/B-025）。

### 6. CLI：`tools/migrate_review_round1.py`

```
python3 tools/migrate_review_round1.py --repo . \
  --github-repo <owner/repo> --artifact <path> --pr <number> \
  [--authorization-comment <github-url-or-node-id> --apply]
```

- 默认 dry-run：fresh 查询 repository immutable ID、PR base/head 与 default-base
  migration cutoff，从 pre-migration Git object 打印受理域、将写入路径、
  source/policy/request digests、deterministic derived/record paths 与 provider-bound
  `authorization_request`，不落盘；最终 derived/record digest 尚未产生，不得预填。
  request 明确标记 `authorized: false`，没有远端 authorization event 时绝不输出
  可供 apply 消费的完整 authorization（B-011/B-014/B-015）。
- `schemas/review_migration_authorization.schema.json` 把可预先发布的 request 与发布后
  provider attestation 分开。GitHub comment body 只含下列 closed
  `authorization_request`：

```text
authorized = false, decision = migrate_legacy_round1_once,
repo_id, pr, artifact_id,
source_artifact_head_sha, authorized_pr_base_sha, authorized_pr_head_sha,
migration_base_sha, source_artifact_path,
source_git_commit_sha, source_git_blob_oid, source_sha256,
derived_artifact_path, record_path,
manifest_path, manifest_source_sha256, manifest_result_sha256,
manifest_entry_sha256, target_policy_digest, normalization_plan_sha256
```

  目标路径先由 `(repo_id, pr, artifact_id, source_sha256, target_policy_digest)`
  等发布前稳定字段的 canonical path seed 派生，再填入 request；
  manifest 三个 digest 分别绑定 H 上的原始 manifest bytes、确定性插入唯一
  `{artifact_id, record_path}` 后的目标 bytes 与该 entry 的 canonical bytes；
  `request_sha256 = SHA256(canonical(authorization_request))` 在此之后计算。request 不含自己的
  digest，也不含 comment identity/time、authorization ID、provider attestation、
  `derived_sha256` 或 `record_sha256`。路径不依赖 request digest 或
  authorization ID，因此可在发布前固定；其 bytes/digest 只能在 authorization 完成后
  产生。
  `checks/github_review_migration_evidence.py` fresh 双读 comment body/node/url/time、
  actor login、repository permission、repo/PR identity；前后任一漂移即拒绝，只有
  `maintain|admin` 权限可授权。双读稳定后 provider 形成 closed
  `provider_attestation`：

```text
provider = github, authorization_comment_node_id, authorization_comment_url,
authorization_payload_sha256 = request_sha256,
provider_snapshot_sha256, actor_login, actor_permission,
comment_created_at, comment_updated_at, authorized_at
```

  provider 要求 `comment_created_at == comment_updated_at == authorized_at`，且两次
  read 的三个值逐项一致。`attestation_sha256 =
  SHA256(canonical(provider_attestation))`，attestation 不含自身
  digest 或 `authorization_id`。完整 `migration_authorization` 是 closed envelope：
  exact request + request digest + exact attestation + attestation digest +
  `authorization_id`；其中 ID 定义为
  `MRA-SHA256(canonical({request_sha256, attestation_sha256}))`。verifier 分别重算
  两个 digest 与 ID；comment 不需要也禁止预言自身 node/URL/time。不同
  comment/scope 必须得到不同 ID（B-019）。本地 authorization/role-map 文件、CLI
  actor/source、cap/merge/auto 授权均拒绝（B-013）。
- `--apply` 强制提供远端 authorization comment；provider 解析 exact decision、验证
  actor permission，将 comment body 与 dry-run request 全字段匹配，并返回上述
  attestation/envelope。provider 不可用、comment
  被编辑/删除、PR/base/head H 漂移或 migration base 与 trusted registry cutoff 不一致
  均在写入前 fail closed。通过后先按 B-024 重算 `migration_id`，再将 migration/
  authorization ID 与 provider digest 注入 marker，
  计算最终 derived bytes/digest，再生成绑定该 digest 的 record receipt；record 本身
  不含 `record_sha256`，verifier 对最终 record bytes 外部重算该值。随后将
  派生与 record 写入同目录 temp、fsync，再按 request 派生的唯一目标路径
  create-only publish；任何只发布一侧的中断状态均不被 loader 接受，retry 只能补全同一
  exact bytes。已存在同 ID 只在 record/derived bytes 完全相同时作为 response-loss retry；
  写后自验 `verify_migration_record()`；
  自验失败删除新写文件并非零退出。manifest `migrations[]` 条目由操作者按 dry-run
  输出显式加入，工具不改 manifest。
- 同一 exact authorization 的 response-loss retry 只返回既有同 digest 文件/record；
  record path 由 request scope 唯一派生，`migrated_at` 固定等于 `authorized_at`，
  canonical record 的外部重算 digest 必须匹配 loader/evidence receipt。任一 bytes
  不同或跨
  PR/base/head/migration-base/artifact/source/derived/record scope 均 block；rollback
  后的 exact reapply 可重新发布相同 bytes。authorization ID 从完整 trusted scope
  确定性派生，不依赖可被 rollback 删除的本地 consumption 状态；相同授权输出逐字节
  确定，不同 scope 无法复用同一 ID（B-012/B-019/B-024）。

### 7. Post-apply terminal head/tree 与认证

apply 的输出在 H 工作树生成后，由操作者只提交 derived artifact、record 与 manifest
entry，得到 H'。`result_pr_head_sha`/`result_pr_tree_oid` 不写入 request、derived 或
record，避免 commit 自引用；它们只存在于 post-commit terminal evidence。受保护
`github_review_migration_evidence.py` 在 H' fresh 双读 GitHub PR/comment/permission，
并构造 closed `terminal_provider_envelope`：

```text
version, repo_id, pr, authorized_pr_base_sha,
authorized_pr_head_sha = H, result_pr_head_sha = H', result_pr_tree_oid,
authorization_id, migration_id, request_sha256, attestation_sha256,
authorization_comment_node_id, comment_created_at, comment_updated_at,
provider_collected_at, adapter_run_id,
file_delta[] = {path, status, sha256}
```

terminal verifier 要求 fresh current head 等于 H'、`H != H'`、
`git merge-base --is-ancestor H H'` 成功，并用
`git diff --name-status --no-renames H H'` 验证最终 tree delta 恰为：

```text
A derived_artifact_path = derived_sha256
A record_path           = externally recomputed record_sha256
M manifest_path         = manifest_result_sha256
```

source path 与其它路径不得变化；每个 H..H' commit 的 touched-path union 也只能是这三
条，rename、missing/extra path、错误 status/digest、H 不可达或仍要求 current head=H
均 block。manifest H preimage 必须等于 `manifest_source_sha256`，H' bytes 必须等于
request 中预计算的 `manifest_result_sha256`，且只新增 exact entry（B-021）。

为让 offline `pr_gate.py` 能区分 protected adapter 输出与 caller JSON，adapter 使用
secret manager 提供的 `SPECRAIL_MIGRATION_ATTESTATION_KEY` 计算：

```text
terminal_attestation_mac =
  HMAC-SHA256(key,
    "specrail.review-migration-terminal.v1\\0" + canonical(terminal_provider_envelope))
```

evidence 只携带 envelope、trusted registry 指定的 `terminal_attestation_key_id` 与 MAC，
不携带 key。`pr_gate.py` 在调用 `pr_review_contract.py` 前，用同一受保护 runtime key
和 `hmac.compare_digest()` 验证；migration evidence 缺 key/MAC、key ID 不匹配、
provider/secret 不可用或 MAC 错误即 block。即使 caller 构造 schema-valid envelope 并
重算所有普通 SHA-256，也无法产生 MAC。普通非 migration PR 仍走既有纯 offline 路径；
registry-covered migration 的 terminal invocation 必须由 protected adapter 收集后立即
运行 offline evaluator（B-022/B-023）。

### 8. 回滚与兼容

删除派生 artifact、迁移记录与 manifest `migrations[]` 条目即回到迁移前状态：
legacy artifact 原样保留并继续 fail closed（B-012）。v1 单轮证据、既有 v2 合法
manifest、GH-167 全部语义零改动；`migrations[]` 缺省为空列表时行为与现状一致。
回滚不改变 authorization/migration ID 的 canonical 算法：同一远端授权只能 exact
reapply，修改任何 scope/bytes 必须重新取得不同的 ID。terminal envelope 不进入仓库
产物与 ID 输入，回滚/reapply 后由 protected adapter 对新的 H' fresh 重签；旧 envelope
因 result head/tree 不同不能复用（B-019/B-021/B-022/B-024）。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-005 | 受理域 + set-null/delete normalization 白名单 | `python3 -m pytest -q tests/test_review_migration.py -k "scope or normalization or diff_field"` |
| B-002 B-004 B-007 | pre-migration Git blob anchor + 摘要绑定与确定性重放 | `python3 -m pytest -q tests/test_review_migration.py -k "git_blob or replay or tamper or reuse"` |
| B-003 B-006 | record/marker schema + trusted legacy identity + manifest `migrations[]` | `python3 -m pytest -q tests/test_review_migration.py tests/test_review_result_semantics.py -k "record or provenance or legacy_identity or manifest"` |
| B-008 B-009 | loader 路由与稳定 rejection、trusted reload | `python3 -m pytest -q tests/test_review_result_semantics.py -k migration` |
| B-010 | 单 artifact gate 源头封口 | `python3 -m pytest -q tests/test_review_json_gate.py -k round1` |
| B-011 B-012 | provider exact authorization + CLI dry-run/apply/幂等/回滚 | `python3 -m pytest -q tests/test_review_migration.py tests/test_github_pr_evidence.py -k "migration_authorization or cli or rollback or replay"` |
| B-013 B-014 | fresh GitHub authorization provider + provider-bound dry-run request | `python3 -m pytest -q tests/test_github_review_migration_evidence.py tests/test_review_migration.py -k "provider or permission or comment or dry_run"` |
| B-015 B-016 B-017 | migration base、legacy/current PR head 闭集 identity 与 ancestry | `python3 -m pytest -q tests/test_review_migration.py tests/test_github_review_migration_evidence.py -k "migration_base or head_identity or ancestry"` |
| B-018 | absent/null normalization shape 保持 | `python3 -m pytest -q tests/test_review_migration.py -k "absent_base or null_base or normalization_shape"` |
| B-019 | request/attestation digest-derived authorization ID、无循环摘要与 rollback reapply | `python3 -m pytest -q tests/test_review_migration.py tests/test_github_review_migration_evidence.py -k "authorization_id or request_digest or attestation or self_hash or cross_scope or rollback"` |
| B-020 | trusted legacy pre-classification 与 native_creation origin mode | `python3 -m pytest -q tests/test_review_result_semantics.py tests/test_review_json_gate.py -k "legacy_classification or migration_required or native_creation"` |
| B-021 | pre-authorization H → post-apply H' ancestry、tree 与 exact delta | `python3 -m pytest -q tests/test_github_review_migration_evidence.py tests/test_pr_gate_terminal.py -k "result_head or result_tree or migration_delta or extra_path"` |
| B-022 | HMAC-authenticated terminal provider envelope | `python3 -m pytest -q tests/test_github_review_migration_evidence.py tests/test_pr_gate_terminal.py -k "terminal_mac or forged_envelope or missing_secret or key_id"` |
| B-023 | immutable comment createdAt/updatedAt 双读 | `python3 -m pytest -q tests/test_github_review_migration_evidence.py -k "created_at or updated_at or precollection_edit"` |
| B-024 | deterministic migration ID | `python3 -m pytest -q tests/test_review_migration.py -k "migration_id or response_loss or rollback"` |
| B-025 | closed native_creation origin ID | `python3 -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py -k "native_creation or origin_alias"` |
| B-026 | registry ↔ loaded manifest lineage exact one-to-one coverage | `python3 -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate_terminal.py -k "lineage_coverage or changed_artifact_id or missing_lineage or duplicate_lineage"` |

## 数据流

`fixed base registry exact-set → protected adapter: pre-migration commit/path →
Git blob + source artifact identity → fresh GitHub PR/default-base identity →
CLI dry-run stable authorization_request → maintainer GitHub comment →
provider double-read + permission query → post-publication provider_attestation →
request/attestation digests derive authorization_id → --apply builds
deterministic migration_id → marker-bearing derived artifact → record receipt →
manifest v2 migrations[] → commit H' → protected provider validates H..H' tree/delta
→ signs terminal envelope → offline gate verifies HMAC →
loader: registry ↔ manifest lineage exact-cover + auth + Git blob replay →
validate_bounded_rounds() → pr_review_contract trusted reload → pr_gate`。
任一层验证失败均 fail closed，未迁移/手工复制形态得到指向本合同的稳定 rejection。

## 备选方案

- 就地改写旧 artifact 把字段置 null：破坏不可变审查证据与摘要，拒绝。
- 放宽 `validate_bounded_rounds()` 允许 round-1 非 null base/diff：等于让全部
  新 artifact 永久携带无法验证的字段，掩盖 GH-167 修复的缺口，拒绝。
- 按 artifact 时间戳自动豁免"历史文件"：时间可自报、不可信，拒绝。
- 手工复制删字段、不留记录：与任意篡改不可区分，拒绝。
- 只在派生 artifact 加自报 marker：调用方仍可省略 marker 冒充 native artifact，拒绝；
  必须由 fixed base registry 的 exact-set legacy identity 强制要求 marker/record。
- 让同一提交里的 record 自报 `source_sha256`：source 与 record 可一起篡改，拒绝；
  必须绑定迁移前可达 Git commit/blob 和外部 exact authorization。
- 在 evidence JSON 里内嵌迁移证明：嵌入副本不可信，必须仓库安全路径重载，拒绝。
- 用 `implx auto` 授权批量迁移：违反 issue 非目标，人工 actor 不可代填，拒绝。
- 复用本地 `maintainer_role_map` + authorization JSON：两份文件均由调用方控制，
  无法证明真实人工决定，拒绝；migration authorization 必须来自 fresh GitHub event
  与 permission 查询。
- 把 `migration_base_sha` 留作 CLI 参数：调用方可任选且 replay 无 durable 值，拒绝；
  必须由 provider/registry 取得并进入 record/authorization。
- 用一个 `head_sha` 同时表示 legacy artifact 与当前 PR：真实 round-2 流两者不同，
  合同不可满足，拒绝；使用两个具名字段。
- rollback 时删除任意 authorization consumption state：会恢复 ID 跨 scope 复用窗口，
  拒绝；authorization ID 必须由 canonical request/attestation digests 确定性派生。
- 让 authorization comment 预含自身 node/URL/time 或最终 derived/record digest：
  发布前无法取得这些值，并与含 authorization ID 的下游 bytes 形成循环，拒绝；
  comment 只发布稳定 request，provider attestation 与 apply receipt 分阶段形成。
- 让 post-apply current head 继续等于 authorization head：提交迁移产物必然产生 H'，
  合同不可满足，拒绝；H 是受权前 ancestor，H' 与其 tree/delta 由 terminal envelope
  单独绑定。
- 信任 caller evidence 中自洽的 provider digest：普通 SHA-256 可由 caller 重算，
  无法证明 provider 查询，拒绝；terminal envelope 必须使用 protected secret 的 HMAC。

## 风险

- Security: 记录与派生文件路径经 repo 安全解析；迁移前 Git blob 与 fresh GitHub
  authorization event/permission 双读共同构成信任根，本地 role map 不参与 migration
  授权；terminal envelope 以 secret-manager HMAC 认证，secret 不进入 repo/evidence/
  CLI/log；所有 Git 命令使用参数数组，无 shell 拼接。
- Compatibility: `migrations[]` 可选且缺省为空；v1、既有 v2、GH-167 语义零改动。
  首次部署后 #181/#186/#193 需一次人工迁移，这是预期操作而非回归。
- Correctness: 规范化序列算法必须单一实现并被 CLI 与验证方共享，防止重放漂移；
  测试覆盖键序、Unicode、嵌套结构。
- Data integrity: Git blob/source/derived 声明/derived 实际摘要 + marker + 逐字段
  normalization + fixed registry/loaded-lineage exact-set + H..H' tree delta + record
  digest，防止丢字段、改字段、手工复制、空集合降级与记录复用。
- Operations: dry-run 先产出 provider-bound stable request，maintainer 在 GitHub
  发布 exact decision；provider 随后证明 comment node/url/actor
  permission/`authorized_at`，apply record receipt 的 `migrated_at` 与之相等，使审计
  可追且构造有限。GitHub/provider 不可用时预期 fail closed。
- Maintenance: 新逻辑集中在 `checks/review_migration.py`；
  `checks/review_result_semantics.py`（当前 702 行）只增薄路由，实现后
  `wc -l` 断言相关文件均小于 800 行。

## 测试计划

- [ ] Unit: 受理域、set-null/delete 白名单、record/request/attestation/authorization/
  marker schemas、
  pre-migration Git blob、absent/null shape、双 head、migration base、重放算法
  （含键序/Unicode/嵌套）、摘要失配、request/attestation-derived ID、无自哈希/
  下游反向绑定、deterministic migration ID 与记录复用。
- [ ] Integration: PR #181/#186/#193 三种真实形态的迁移前 block（稳定 rejection）
  与迁移后全链路通过；篡改派生文件、替换源文件、同提交重算 source digest、
  手工 copy 省略 marker/record、manifest 条目缺失/重复、registry 缺失/子集/空集合/
  cutoff/digest 漂移、changed artifact_id、missing/duplicate lineage 负例；
  `specrail-pr-gate` + `pr_gate.py` terminal forward test 以 fixed-base registry、
  authenticated identity/auth 复核。
- [ ] CLI: dry-run 无副作用且 request 可在 comment 发布前完整构造；comment 不含自身
  provider 元数据或下游摘要；apply 缺/错 provider attestation、错 commit/blob/
  source/derived/record scope 或 digest、`migrated_at` 漂移、同 ID 不同 bytes 拒绝；
  fresh GitHub comment createdAt/updatedAt/permission/provider 前后漂移负例；
  pre-head H/result-head H' ancestry、tree、exact delta；伪造自洽 envelope、错误/缺失
  HMAC/key/provider；exact retry/reapply 幂等；自验失败清理。
- [ ] Full: `python3 -m pytest -q`、`python3 checks/check_workflow.py --repo .
  --all-specs`、`python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate`、
  `git diff --check`。

## 回滚方案

回滚实现即删除 migration 模块/CLI/schema 与 loader 路由；已生成的派生 artifact
与记录会被回滚后的 loader 当作普通 v2 输入中的未知形态拒绝，不会静默放行。
运维层回滚只需删除派生 artifact、迁移记录与 manifest `migrations[]` 条目，
原始 artifact 从未被改动，队列回到迁移前的 fail-closed 状态；remote authorization
event 与 canonical authorization/migration IDs 不被回滚，之后只能对同一 exact scope
重放。terminal envelope 只认证某个 H' tree，不作为 durable consumption state；回滚或
reapply 后必须 fresh 收集并对新的 H' 重签，provider/key 不可用时保持 blocked。
