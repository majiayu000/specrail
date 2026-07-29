# Tech Spec

## Linked Issue

GH-166

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":166,"complete":true,"paths":["checks/check_workflow.py","checks/evidence_content_binding.py","checks/github_evidence_common.py","checks/github_pr_evidence.py","checks/pack_asset_validation.py","checks/pr_review_contract.py","checks/review_result_semantics.py","checks/review_round_semantics.py","checks/pr_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/schema_validation.py","schemas/pr_review_authorizations.schema.json","schemas/pr_review_gate.schema.json","schemas/review_result.schema.json","schemas/runtime_checkpoint.schema.json","schemas/runtime_thread_dispatch_gate.schema.json","schemas/runtime_tier_authorization.schema.json","tests/test_check_workflow.py","tests/test_github_pr_content_binding.py","tests/test_github_pr_evidence.py","tests/test_pack_asset_validation.py","tests/test_review_json_gate.py","tests/test_review_result_semantics.py","tests/test_pr_gate.py","tests/test_runtime_gate_rules.py","tests/test_runtime_ledger_gate.py","tests/test_runtime_ledger_review.py","tests/test_runtime_sensitive_routes.py","tests/test_spec_revision_route_end_to_end.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH166/product.md","specs/GH166/tech.md","specs/GH166/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Required change |
| --- | --- | --- | --- |
| collector snapshot | `checks/github_pr_evidence.py:291`、`checks/github_pr_evidence.py:518` | 读取 `headRefOid`，采集前后 head 漂移全量拒绝 | 在稳定 final head/base 上计算 current bindings，不混拼多 head hash |
| PR schema | `schemas/pr_review_gate.schema.json:25` | top-level `additionalProperties:false`，未知 binding 字段拒绝 | 声明 closed v1 snapshot/reuse audit |
| review schema/manifest | `schemas/review_result.schema.json:23`、`checks/review_result_semantics.py:385`、`checks/pr_review_contract.py:217` | terminal artifact/manifest exact-head | schema-backed covered categories；previous-head component 仅在 bindings 全匹配时可用 |
| runtime | `checks/runtime_gate_rules.py:278`、`checks/runtime_ledger_gate.py:683` | review/pr_gate head 都等于 item head | 只放宽组件 artifact；current pr_gate result 仍 exact-head |

## 设计方案

### 1. Canonical snapshot bindings

新增 `checks/evidence_content_binding.py` 作为单一实现源，避免继续膨胀多个接近 U-16 上限的 gate 文件：

```json
{
  "content_binding_version": 1,
  "snapshot": {"head_sha":"...","base_tree_oid":"...","algorithm":"sha256","normalization":"specrail-v1","collector":"github_pr_evidence"},
  "content_hashes": {"code_inputs":"...","spec_files":"...","pr_metadata":"..."}
}
```

- `code_inputs` 编码 `base_tree_oid + NUL + normalized code patch bytes`；默认分支推进/rebase 必然改变。
- `spec_files` 对 normalized repo-relative path 排序，逐项编码 `path + NUL + decimal byte length + NUL + raw bytes`。
- `pr_metadata` 对 title/body/base/head ref/verified issue relation 的 canonical JSON 编码。
- collector 在前后复核 head、base tree、file snapshot 与 issue relation；漂移即丢弃 current snapshot 重采，不部分拼接。

### 2. Per-component coverage

CI check 与 review artifact 使用同一 closed shape：

```json
{"covered_categories":["code_inputs","spec_files"],"content_bindings":{"code_inputs":"...","spec_files":"..."}}
```

coverage 非空、无重复、只允许三类，bindings keys 必须与 coverage 完全相等。CI coverage 从 repo-owned check mapping 推导；本 repo `workflow-check` 映射 `code_inputs + spec_files`。review coverage 由 reviewer artifact 声明并受 schema/manifest 语义校验；review body/issue relation 时加入 `pr_metadata`。

复用函数只在 component 原 bindings 与 current snapshot 对其全部 covered categories 相等时返回 allowed。未覆盖 spec 的 code review 不代表 spec review；覆盖 spec 的 terminal review 在 spec hash 变化后必失效。

### 3. Legacy and provenance

`content_binding_version` 缺失时，所有现有 exact-head checks 原样执行，不读取/要求 `sha_provenance`。v1 时 schema 必须同时要求 snapshot、三类 current hashes、component coverage/bindings 与 collector provenance；任何 partial v1 或 unsupported version blocked。PR body 中展示性 SHA 不作为 machine evidence，也不需要 provenance；只有 v1 machine fields 受此约束。

### 4. Review contract and PR gate

`review_result.schema.json` 增加 optional v1 coverage binding；`review_result_semantics.py` 校验 shape。`pr_review_contract.py` 接受 current-head artifact，或接受 previous-head artifact + current snapshot + 全 covered binding match；manifest v2 只允许最后声明的 bounded round 成为 current/reusable terminal conclusion，较旧 clean round 不得越过较新 blocking round，复用时必须保留 original artifact ID/head。

`pr_gate` 每个 current head 重新收集 CI status、threads、merge state、review decision、authorization 与 query freshness。它只把 coverage-matched prior CI/review artifact作为组件输入，输出 current-head gate result，并记录 reuse audit。旧 head 的 `pr_gate` decision 本身不可作为 current decision。

### 5. Schema and runtime

- `pr_review_gate.schema.json` 声明 v1 snapshot、component bindings、reuse audit；closed schema 拒绝 unknown/partial/mixed version。
- `runtime_checkpoint.schema.json` 声明 current snapshot 与 component reuse audit；v1 item 使用覆盖全部 production runtime consumer（含 GH143 六个 tier/重授权字段）的显式 closed field set，legacy item 保持可扩展，真正未知字段仍拒绝。
- 两个主 schema 把独立授权与 thread dispatch shape 抽到 pack-owned schema asset；`schema_validation.load_json_schema` 仅解析 schema 目录内的相对 `$ref`，pack gate 校验引用完整性并对全部 schema 执行 800 行硬上限。
- `review_result_semantics.py` 的 bounded-round helper 属于生产运行时依赖，必须登记在 `check_workflow.REQUIRED_FILES`；consumer pack 缺失 helper 时在完整性检查阶段直接失败。
- `runtime_gate_rules.py` 使用共享 binding helper校验 previous-head terminal review，而不是仅比较 `code_diff_hash`。
- `runtime_ledger_gate.py` 保留 `item.pr_gate.head_sha == item.head_sha` 和 loaded gate result exact-head；它验证 current gate 内的 reused components audit，而非给旧 gate decision 增加 head exception。这消除 hosted finding 指出的 dead path，同时保持 merge-time freshness。

## Product-to-Test Mapping

| Invariant | Implementation | Verification |
| --- | --- | --- |
| B-001 | base tree + code patch binding | base advance/rebase same patch invalidates test |
| B-002 | path/length/content spec encoding | rename/split/order/concatenation collision tests |
| B-003 B-004 | component coverage + trusted CI mapping | workflow-check spec change invalidates test |
| B-005 B-006 | review artifact coverage | spec/metadata covered vs uncovered cases |
| B-007 B-008 | legacy/v1 conditional | legacy no provenance passes exact-head; partial v1 blocked |
| B-009 | stable final snapshot | head/base/files/relation drift restart tests |
| B-010 | three schemas + semantic validators | unknown/mixed/partial negative matrix |
| B-011 | review contract/runtime rules | previous-head component all-category match only |
| B-012 | current gate exact-head | old pr_gate result rejected; current wrapper with reused component allowed |
| B-013 | sensitive route | all actual categories + independent terminal review required |
| B-014 | audit | remove each audit field => blocked |

## 数据流

Stable current GitHub snapshot → canonical three hashes → current component evidence plus optional prior component artifacts → shared coverage matcher → current-head `pr_gate` re-evaluates live gates → current-head gate result + reuse audit → runtime ledger exact-head validates gate result and component audit。

## 备选方案

- 仅比 normalized patch：拒绝；base tree 改变会复用未在相同依赖/配置上测试的证据。
- terminal review 只绑定 code：拒绝；spec packet 变化可能漏审。
- spec hash 只拼内容：拒绝；path/identity/边界存在碰撞语义。
- 复用旧 pr_gate decision：拒绝；threads、merge/auth/query freshness 必须 current-head。
- v1 provenance 无条件施加 legacy：拒绝；会破坏兼容承诺。

## 风险与约束

- Security：coverage 少报可绕过重跑；因此 CI coverage 来自 repo config，review coverage schema-backed，敏感面要求所有实际类别。
- Compatibility：legacy 无 v1 字段 exact-head 原样通过，不要求 provenance。
- File size：新增共享 helper/round/schema asset；`github_pr_evidence.py`、`review_result_semantics.py`、`runtime_ledger_gate.py` 与全部 pack-owned schema 均须 ≤800 行。

## Test Plan

- Focused：canonical hash、coverage matcher、schema、review contract、runtime exact-head wrapper。
- End-to-end：spec-only、metadata-only、base-advance-same-patch、mixed change；确认仅覆盖匹配组件复用且 current gate重跑。
- Submission：`/usr/bin/python3 -m pytest -q`、all-spec workflow、GH166 depth gate、受限文件 line checks。

## 回滚方案

删除 v1 collector/schema/matcher 分支即可恢复 exact-head；legacy 数据无需迁移。
