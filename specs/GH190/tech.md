# Tech Spec

## Linked Issue

GH-190

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":190,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/github_goal_evidence.py","checks/goal_contract.py","checks/pack_asset_validation.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","schemas/goal_contract.schema.json","schemas/goal_evidence.schema.json","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","templates/tranche_checkpoint.md","templates/zh-CN/tranche_checkpoint.md","tests/test_check_workflow.py","tests/test_github_goal_evidence.py","tests/test_goal_contract.py","tests/test_pack_asset_validation.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH190/product.md","specs/GH190/tech.md","specs/GH190/tasks.md"]}
-->

## Product Spec

见 `specs/GH190/product.md`。实现 B-001..B-028，不选择 GH-160 的预算值。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Goal guidance | `skills/specrail-implement-queue/SKILL.md:575-605` | 用 prose 要求 objective/预算/终止，但没有 builder。 | 转为唯一 payload 来源。 |
| checkpoint schema | `schemas/runtime_checkpoint.schema.json:269-320` | `goal` 无 required/closed/status enum；candidate 较严格。 | active Goal 需要 closed contract。 |
| gate dispatch | `checks/runtime_ledger_gate.py:473-523` | 调 `_validate_goal_candidate`，不验证 active goal。 | 新增分支与 binding。 |
| current validation | `checks/runtime_gate_rules.py:761-785` | 只检查 candidate 字符串/list 非空。 | 共享 builder/validator，避免重复。 |
| template | `templates/tranche_checkpoint.md:19-23` | 建议记录 Goal 与“保守默认”，没有来源或 digest。 | 输出完整 canonical payload。 |
| content binding | `checks/evidence_content_binding.py:126-174` | 已有 trusted collector identity 与 path+sha sidecar 模式。 | Goal remote/tool evidence 沿用 closed reference，不接受裸 digest。 |
| maintainer provenance | `checks/github_approved_spec_evidence.py:121-215` | 已绑定 default branch、maintainer actor 与 approval timestamp。 | pack default 复用 remote approval 模式。 |
| content recheck | `checks/sensitive_enforcement.py:360-429` | 从 trusted base Git object 重算 approved content。 | 重算 `workflow.yaml` policy bytes，拒绝 caller 摘要。 |
| active-run dependency | GH-189 / PR #193 | fresh 2026-07-26 仍为 OPEN，合同不在 default branch。 | GH-190 实现必须显式等待合并/rebase。 |

## 设计方案

### 1. trusted evidence boundary

新增 closed `schemas/goal_evidence.schema.json` 与只读
`checks/github_goal_evidence.py`。证据分成三个不可互换的来源：

```text
InvocationAttestation = runtime-owned auth_mode/queue_mode/user-budget receipt
CapabilityAttestation = runtime-owned Goal API/features/host receipt
GitHubGoalEvidence = adapter-owned repo policy + complete queue snapshot
```

`InvocationAttestation` 必须绑定 invocation/thread/run、repo immutable ID、用户消息摘要、
`auth_mode`、`queue_mode`、可选 user token budget、issued_at 与 detached attestation。
`CapabilityAttestation` 必须绑定同一 host/run，并列出
`create_result_receipt`、`live_snapshot`、`monotonic_transition_anchor` 三项 feature。
只有 host 提供的 verifier 能按 checkpoint/repo 之外的 trust root 验证 attestation 时，
builder 才接受这些字段。缺失/签名无效时返回 `blocked: untrusted_routing`，而不是把
caller 自报的 `review`/`bounded_tranche`/`unavailable` 当成合法 disabled 分支；只有
**已验证** capability receipt 声明 unavailable 时才能导出
`capability_unavailable`。

`github_goal_evidence.py` 沿用仓库现有 GitHub adapter 模式，固定输出 collector identity、
repository node ID、default ref/SHA、可信 `as_of`、规范化 payload 与完整 artifact
digest。它有两个 closed section：

- `pack_default`: 从 trusted default branch 的 canonical
  `workflow.yaml#/goal_policy/token_budget` 读取值，绑定 config blob OID/bytes digest、
  source commit、唯一 merged default-branch PR、exact merge SHA，以及在 exact config
  commit 上的 maintainer approval review（review ID、actor、timestamp、permission）。
  adapter 自行查询并验证这些字段；CLI 不接受 `approval_ref` 或 `source_digest`。
  配置不存在时也由 exact default-branch blob 证明 absent。
- `queue_snapshot`: 通过固定 versioned query 完整分页收集 actionable issues/PRs、
  heads、states、skip/draft/human-decision 分类；分页中 repo/default-base identity
  漂移或达到 limit 未完成时收集失败。

artifact 以 `{artifact_id,path,sha256}` 引用，loader 校验 closed schema、collector
identity、raw file SHA，再从 local trusted default-base Git object 重算 policy bytes 和
approval lineage。裸 `remote_truth_digest`、caller 手写 GitHub JSON 或 agent 可替换的
checkpoint 副本均不构成 trusted evidence。

### 2. canonical builder 与 immutable contract

新增 `checks/goal_contract.py`：

```text
build_goal_contract(
  routing_evidence_ref, capability_evidence_ref,
  github_goal_evidence_ref, run_lease_evidence_ref
) -> GoalBuildEnvelope
```

builder 不接受 raw `auth_mode`、`queue_mode`、`goal_capability`、`budget_source`、
disabled reason 或预计算 digest；这些全部从上节的已验证 evidence 导出。
`run_lease_evidence_ref` 必须引用 GH-189 提供的 active-run lease/fencing evidence。
builder 从 GitHub queue snapshot 的原始 records 自行稳定排序并生成 RFC8785 canonical
JSON，再取 SHA-256 得到不可变的 `queue_baseline_digest` 与
`human_decisions_baseline_digest`。

创建前 `GoalDraft` 是独立 closed type，不含 `goal_id`、`status`、`tokens_used` 或
transition；它只作为 `create_goal` 输入，不能被 checkpoint schema 引用。创建后的
`ActiveGoalContract` 是另一个 closed type，下列字段全部 required：

```text
version, goal_id, objective, objective_digest, contract_digest,
constraints[], termination_conditions[4], reanchor_contract,
token_budget, budget_source, budget_selection_digest,
tokens_used, status, repo_id, run_id, fencing_token,
queue_baseline_digest, human_decisions_baseline_digest,
create_request_digest, create_receipt_id
```

`budget_selection_evidence` 不再携带 caller 字段，而是 closed references：

```text
user_input = invocation_attestation_ref + bound value/absence
pack_default = github_goal_evidence_ref + bound value/absence + approval event
```

`budget_source` 只能由 builder 按 verified user budget 优先、approved pack default
次之的固定顺序导出。builder 不定义 default 数值。两个 trusted 输入都明确缺失时导出
`missing_budget`；声明值存在但 policy/approval/content binding 非法时返回
`blocked: invalid_budget`，不创建 active Goal。缺 trusted evidence 与“可信地证明
absent”不同，前者一律 blocked。

objective 由固定模板渲染，明确全队列目标、四终止条件、checkpoint+remote re-anchor、
不替代 gates 与禁止越权。`objective_digest` 只覆盖 UTF-8 objective；
`contract_digest` 精确定义为以下 object 的 RFC8785 bytes 的 SHA-256：

```text
{
  version, objective, objective_digest, constraints,
  termination_conditions, reanchor_contract,
  token_budget, budget_source, budget_selection_digest,
  repo_id, run_id, fencing_token,
  queue_baseline_digest, human_decisions_baseline_digest,
  create_request_digest
}
```

生命周期可变字段 `goal_id`、`tokens_used`、`status`、current queue 与 transition
events 不参与该摘要，但 `goal_id` 只能由匹配 `create_request_digest` 的 runtime
receipt 引入。

### 3. agent-facing CLI 与 complete initial bundle

agent-facing flow 固定为：

```text
python3 checks/github_goal_evidence.py collect \
  --repo . --github-repo OWNER/REPO --json
python3 checks/goal_contract.py build \
  --routing-evidence <host-attestation.json> \
  --github-evidence <adapter-artifact.json> \
  --lease-evidence <GH189-evidence.json> --json
python3 checks/goal_contract.py bind \
  --build <allowed-build.json> \
  --create-result-evidence <host-create-receipt.json> --json
```

`build` allowed envelope 是
`{decision:"allowed",create_goal:{objective,token_budget},goal_draft,...}`；
blocked envelope 的 `create_goal`/`goal_draft` 为 null 且稳定返回 reason/errors。
queue 只把 `create_goal` object 传给 Goal tool。host 必须把 result 导出为 attested
receipt：

```text
provider, operation:"create_goal", tool_call_id, receipt_id,
repo_id, run_id, request_digest, goal_id, goal_revision,
status:"active", transition_tail_digest, issued_at, attestation
```

`bind` 不再接受 `--goal-id`。它验证 host attestation、exact request digest、run/repo、
revision/status 与 fresh live Goal snapshot后，一次输出 closed
`GoalCheckpointBinding`：

```text
binding_state:"active",
routing + budget selection,
goal: ActiveGoalContract,
queue_baseline + human_decisions_baseline,
queue_current,
queue_rebindings: [],
goal_transitions: [sequence-0 active event],
transition_anchor: attested create receipt tail
```

checkpoint v4 只持久化这个 bundle object，不散放需要 skill 组装的局部字段。
sequence-0 event、current snapshot 与 baseline digest 都由 binder 重算并写入。
queue/implx skill 只能把完整 bind bundle 原样交给 checkpoint writer；缺 ID、裸 ID、
异常、取消、旧/跨 run receipt、request mismatch 或 live snapshot mismatch 时 `bind`
exit 1 且不输出可写 bundle。

### 4. canonical transition evidence 与 external anchor

active status enum 保持：

```text
active → complete | exhausted | interrupted | blocked
```

每个 immutable transition event required：

```text
sequence, from, to, occurred_at,
evidence_ref:{artifact_id,path,sha256,type,source},
evidence_digest, goal_revision,
prev_event_digest, event_digest, external_tail_digest
```

`evidence_digest` 必须由 loader 读取 `evidence_ref` 的 closed canonical object 后重算，
不是仅检查非空。各分支 prerequisite：

- sequence 0 `active`: exact build envelope、attested create receipt 与 initial bundle digest；
- `complete`: content-bound fresh GitHub queue artifact证明 empty/fully blocked/only human
  decisions，并绑定 attested `update_goal(complete)` result；
- `exhausted`: attested live usage/budget snapshot、content-bound checkpoint/handoff artifact
  与 attested terminal result；
- `interrupted`: runtime-owned interrupt attestation、latest checkpoint/handoff digest 与
  attested interrupted result；
- `blocked`: schema-valid gate rejection/blocker artifact、reason IDs 与 attested blocked
  result。

Goal runtime 是 checkpoint 外的 immutable anchor provider。每次 create/update 都必须
返回不可回退的 monotonic `goal_revision`、status 与 `transition_tail_digest`；resume
前另收集 attested live Goal snapshot。gate 将本地 chain tail 与 external revision、
status、tail digest 逐项对账。host 不提供这些 feature 时 active Goal capability 不成立。
因此删除 terminal event、重算 checkpoint 链并改回 active 仍会与 external terminal
status/revision/tail 冲突；active contract 已存在后，缺 live snapshot 不得降级成
`capability_unavailable`，只能 `blocked: goal_anchor_unavailable`。

### 5. content-bound queue rebind

`GoalCheckpointBinding.queue_current` 保存 canonical records 与摘要。
`queue_rebindings[]` 每项 required：

```text
sequence, prior_digest, current_digest,
remote_evidence_ref:{artifact_id,path,sha256},
remote_artifact_digest, as_of,
repo_id, run_id, fencing_token, scope_digest,
prev_event_digest, event_digest
```

第一次 `prior_digest` 等于 baseline，之后等于前一 event 的 current digest。loader
必须校验 `github_goal_evidence` collector/schema/file SHA，重算 artifact digest、
records/current digest，并要求 repo/default-base 与 stable scope 匹配、完整分页且
`as_of` 不早于前一 rebind。caller 自报 digest 或只有内部链一致性不算 remote truth。
GitHub item state/head 变化、新增或移出 actionable 集合是合法同-scope rebind，不修改
contract digest；repo/run/fencing/scope 变化、直接改 current、evidence reuse、断链或
snapshot digest 不匹配必须阻断并要求新 Goal/人工决策。

### 6. schema 与 runtime gate

`schemas/goal_contract.schema.json` 定义 active contract/binding state；
`schemas/goal_evidence.schema.json` 定义 routing/capability/GitHub/tool/transition
evidence 与 references。`schemas/runtime_checkpoint.schema.json` v4 通过 `$ref`
要求恰好一个 closed `goal_binding`，其 `binding_state` 是：

```text
active | disabled | migration_pending
```

`disabled` 只能由 verified invocation/capability/budget evidence导出：
`review_mode`、`bounded_tranche`、`capability_unavailable`、`missing_budget` 或
`invalid_budget`。missing/invalid attestation 是 `blocked`，不等于 disabled。
auto + full_queue_drain + verified capability available +合法预算要求 `active`；
已存在 active bundle 不允许通过后来声称 review/bounded/unavailable 移除 Goal。

runtime gate 调用共享 `validate_goal_contract()`，一次性交叉校验：

- routing/capability/tool receipt attestation 与 repo/run binding；
- policy bytes、merged PR/approval event、budget selection 与 contract digest；
- immutable queue baseline、content-bound current/rebind chain；
- canonical transition evidence、local chain 与 external live anchor；
- repo/run/fencing 与 GH-189 lease evidence；
- tokens/status/terminal prerequisite，以及 checkpoint status 与 Goal status。

gate 本身只读，不调用 Goal API/网络/session；fresh runtime/GitHub adapter artifacts
必须在调用 gate 前收集并作为显式输入。

### 7. checkpoint v4 迁移

v1–v3 仍可读取诊断，但 resume/continue 或 legacy `goal` 非空时稳定返回
`blocked: legacy_checkpoint_requires_migration`。`migrate-checkpoint` 对 v1/v2/v3
分别保留原合法字段、budget/telemetry 与
`legacy_goal_provenance`，不把旧 goal 或 tranche budget 推断为 active Goal budget。

对 verified disabled routing，迁移可直接输出 final v4 `binding_state:"disabled"`。
对 auto/full/available/valid-budget routing，迁移输出专用
`binding_state:"migration_pending"`，而不是普通 `goal:null`：

```text
migration_id, source_version, legacy_checkpoint_digest,
legacy_goal_provenance, routing/lease/remote evidence refs,
pending_build_digest, allowed_recovery_action:"finalize_goal_migration"
```

该分支 schema-valid；runtime gate 稳定返回
`blocked: goal_migration_pending` 并只允许 `finalize_goal_migration` recovery，
禁止 lane/checkpoint completion/remote writes。finalize 命令消费 exact pending
digest、fresh GitHub evidence 与 attested create/live receipts，原子输出完整 active
`GoalCheckpointBinding`；崩溃重试必须复用同一 receipt/goal ID，不得再创建 Goal。
unsupported source、证据缺失或 final bundle 非法时 exit 1 且 pending 保持不变。

### 8. GH-189 dependency 与 queue 集成

fresh GitHub truth 显示 GH-189 与 spec PR #193 仍 OPEN，origin default branch 没有其
active-run lease contract/runtime assets。因此 GH-190 **所有实现任务**以“GH-189
contract 与 runtime implementation 均已合并到目标 default branch并完成 rebase”为
implementation gate；只合并 spec PR #193 仍不满足，不能再声称 GH-189 已落地。
rebase 后 GH-190 只引用 GH-189 提供的 repo identity、`run_id`、`fencing_token`、lease
evidence/schema/helper，不复制字段或另建 fallback。contract/path 冲突必须回到 spec
review，不得由实现者静默择一。

queue 与 implx 两个入口只调用 evidence adapter + `build`/`bind`/transition/finalize
CLI，不再拼 objective、Goal ID、routing、remote digest 或 conservative default。
GH-172 仍是 queue/lock integration dependency；GH-174 合并后详细操作放 canonical
runtime reference，主 Skill 保留不可绕过 marker。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-004 B-005 B-019 | builder/CLI/template | `python3 -m pytest -q tests/test_goal_contract.py -k "builder or cli"` |
| B-003 B-015 B-021 | trusted budget evidence/selection | `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "budget or policy or approval"` |
| B-006 B-011 B-017 B-022 B-023 | create receipt/checkpoint/run/bundle binding | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "receipt or binding or bundle"` |
| B-007 B-020 | attested routing/capability branches | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "routing or capability or attestation"` |
| B-008 B-009 B-010 B-016 B-024 B-025 | canonical transitions/external anchor | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "transition or evidence or anchor or reactivation"` |
| B-012 | closed schema/gate | `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k goal` |
| B-013 B-014 | purity/failure | `python3 -m pytest -q tests/test_goal_contract.py -k "pure or failure"` |
| B-018 B-027 | v1–v3 migration pending/finalize | `python3 -m pytest -q tests/test_goal_contract.py tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k migration` |
| B-026 | content-bound GitHub queue rebind | `python3 -m pytest -q tests/test_github_goal_evidence.py tests/test_runtime_ledger_gate.py -k "queue or rebind or remote"` |
| B-028 | GH-189 merge/rebase dependency | manual/fresh check: PR #193 merged into trusted default base before any GH-190 implementation task starts; dependency fixture keeps route blocked otherwise |

## 数据流

```text
runtime invocation/capability attestations + GitHub policy/queue evidence + GH189 lease
  → `build` CLI → GoalDraft + exact create_goal args
  → attested create result/live snapshot → `bind` CLI → complete v4 bundle
  → content-bound rebinds + canonical transition evidence + external Goal anchor
  → offline runtime gate
```

## 备选方案

- 继续自然语言拼 objective：不可验证，拒绝。
- schema 只要求非空字符串：无法证明终止/re-anchor，拒绝。
- 在本 issue 硬编码默认预算：越过 GH-160/维护者决策，拒绝。
- 用 Goal status 代替 queue truth：违反既有边界，拒绝。
- 接受 caller 的 mode/capability/Goal ID/digest：无法证明 runtime/GitHub truth，拒绝。
- 只把 transition hash chain 放 checkpoint：自洽截断后可伪造 active，拒绝。
- 在 GH-189 合并前复制 run/fencing fields：产生双重 ownership/migration，拒绝。

## 风险

- Security: objective 不含 session/secret/raw issue body；attestation trust root 在
  checkpoint/repo 外，artifact 只保存 ID、必要 payload 与 digest。
- Compatibility: v1–v3 只能诊断或进入 recovery-only `migration_pending` 后 finalize；
  旧 active goal 不能静默 grandfather。
- Availability: runtime 缺少 attested receipts/live anchor 时 active Goal fail closed；
  已存在 active Goal 不允许伪装 unavailable。
- Performance: builder/gate 是小型本地纯函数。
- Maintenance: evidence adapter、builder、schema、template、queue 与 GH-189 lease
  contract 必须由同一 fixture 对账。

## 测试计划

- [ ] Unit: canonicalization、四终止、attested routing/create receipts、approved policy、
      完整 contract digest、complete bind bundle、canonical transition evidence、
      external anchor、content-bound rebind 与稳定错误。
- [ ] Integration: draft/active/disabled/migration-pending schema、runtime gate、
      terminal-reactivation、queue/run/GH-189 binding、v1–v3 prepare/finalize migration。
- [ ] Regression: full pytest、all-specs、depth/diff/hash。
- [ ] Forward-use: dry-run evidence → build → attested fake tool receipt → complete bundle
      → rebind/terminal → live-anchor resume；测试不调用真实 Goal API。

## 回滚方案

回滚 evidence adapter、builder、schema/gate、queue/template、tests/docs/lock 同一实现
提交。不得删除 external terminal anchor 或保留新 active checkpoint 却回滚 validator；
回滚后 Goal 只能视为 candidate/人工状态，GH-189 lease 资产保持其 own rollback policy。
