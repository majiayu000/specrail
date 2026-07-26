# Tech Spec

## Linked Issue

GH-190

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":190,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/github_goal_evidence.py","checks/github_issue_evidence.py","checks/goal_contract.py","checks/pack_asset_validation.py","checks/route_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","examples/fixtures/goal-contract-vectors.json","examples/fixtures/issue-gh190-dependencies-ready.json","examples/fixtures/issue-gh190-dependency-open.json","examples/fixtures/issue-gh190-overlap-unrebased.json","schemas/goal_contract.schema.json","schemas/goal_evidence.schema.json","schemas/issue_evidence.schema.json","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","templates/tranche_checkpoint.md","templates/zh-CN/tranche_checkpoint.md","tests/test_check_workflow.py","tests/test_github_goal_evidence.py","tests/test_github_issue_evidence.py","tests/test_goal_contract.py","tests/test_pack_asset_validation.py","tests/test_route_gate.py","tests/test_runtime_ledger_gate.py","tests/test_runtime_ledger_queue.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH190/product.md","specs/GH190/tech.md","specs/GH190/tasks.md"]}
-->

<!-- specrail-implementation-dependencies-v1
{"version":1,"issue":190,"serial_order":[172,174,189,190],"dependencies":[{"issue":172,"required_stage":"implementation_merged","required_rebase":true},{"issue":174,"required_stage":"implementation_merged","required_rebase":true,"overlap_paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","tests/test_check_workflow.py"]},{"issue":189,"required_stage":"implementation_merged","required_rebase":true}]}
-->

## Product Spec

见 `specs/GH190/product.md`。实现 B-001..B-041，不选择 GH-160 的预算值。

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
| implementation route | `checks/github_issue_evidence.py:1-260`、`checks/route_gate.py:184-280` | issue adapter 收集 readiness，route gate 离线判断；当前没有 cross-issue merge/overlap dependency。 | 新增 generic dependency evidence 与 fail-closed route 分支，不能靠 handoff 手工门。 |
| checkpoint status | `schemas/runtime_checkpoint.schema.json:61-68`、`schemas/runtime_checkpoint.schema.json:225-227` | checkpoint status 与 stop_reason 已有闭集，但没有 Goal status 对照矩阵。 | 完整定义 B-040 的合法笛卡尔子集。 |
| queue-split dependency | GH-174 / PR #192 | fresh 2026-07-26 仍为 OPEN；其 manifest 与 GH-190 重叠七个 queue/lock paths。 | queue integration 必须等待 contract+runtime implementation 合并并 rebase。 |
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
`create_result_receipt`、`live_snapshot`、`monotonic_transition_anchor`、
`receipt_lookup_by_request_digest` 与 `idempotent_create_by_request_digest` 五项 feature。
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

`create_request_digest` 不复用 `contract_digest`，也不 hash 整个 allowed envelope。
builder 先构造唯一 closed `CreateRequestBinding`：

```text
domain:"specrail.goal.create-request", version:1,
operation:"create_goal", provider,
tool_args:{objective,token_budget},
repo_id, run_id, fencing_token,
build_artifact_id, goal_draft_digest
```

摘要字节固定为 ASCII `specrail.goal.create-request.v1\0` 加
`CreateRequestBinding` 的 RFC8785 bytes，再取 SHA-256。allowed build 的
`create_goal` 必须字节等于 `tool_args`；host receipt 的 `request_digest` 必须字节等于
该 `create_request_digest`。object 多字段/缺字段、domain/version 错、只 hash
`tool_args`、hash 整个 envelope 或 receipt 使用其它 canonicalization 都
`blocked: create_request_mismatch`。`contract_digest` 只引用已经算出的
`create_request_digest`，因此没有摘要环。

### 3. agent-facing CLI 与 complete initial bundle

agent-facing flow 固定为：

```text
python3 checks/github_goal_evidence.py collect \
  --repo . --github-repo OWNER/REPO --json
python3 checks/goal_contract.py build \
  --invocation-evidence <host-invocation-attestation.json> \
  --capability-evidence <host-capability-attestation.json> \
  --github-evidence <adapter-artifact.json> \
  --lease-evidence <GH189-evidence.json> --json
python3 checks/goal_contract.py bind \
  --build <allowed-build.json> \
  --create-result-evidence <host-create-receipt.json> \
  --live-goal-evidence <host-live-snapshot.json> --json
```

四个 build evidence reference 均是 closed `{artifact_id,path,sha256}`，CLI 分别加载并
校验 invocation、capability、GitHub 与 lease schema/issuer/repo/run；不得用一个
`--routing-evidence` 混装 invocation/capability，也不提供隐式 alias。active route 的
`build` allowed envelope 是
`{decision:"allowed",create_goal:{objective,token_budget},goal_draft,...}`；
verified review/bounded/capability-unavailable route 则在同一次 `build` 直接输出
`decision:"allowed"` + closed `binding_state:"disabled"` bundle；trusted
missing-budget 输出 `decision:"needs_human"` + closed disabled bundle。untrusted
routing/capability 或 invalid budget 输出 `decision:"blocked"`，其
`create_goal`/`goal_draft`/`goal_binding` 均为 null，skill 不得补写 disabled。
queue 只把 `create_goal` object 传给 Goal tool。host 必须把 result 导出为 attested
receipt：

```text
provider, operation:"create_goal", tool_call_id, receipt_id,
repo_id, run_id, request_digest, goal_id, goal_revision,
status:"active", transition_tail_digest, issued_at, attestation
```

`bind` 不再接受 `--goal-id`，create receipt 也不兼作 live state。它分别加载
create-result 与 bind-time live Goal evidence，验证 host attestation、exact request
digest、run/repo、goal ID、`live.goal_revision >= receipt.goal_revision`、active status
和 transition tail 一致后，一次输出 closed
`GoalCheckpointBinding`：

```text
binding_state:"active",
routing + budget selection,
goal: ActiveGoalContract,
queue_baseline + human_decisions_baseline,
queue_current,
queue_rebindings: [],
goal_transitions: [sequence-0 active event],
transition_anchor: attested live Goal tail,
binding_digest
```

为避免 sequence-0 自引用，binder 先构造 closed `InitialBindingProjection`，只包含
routing/budget evidence、ActiveGoalContract、queue/human baseline、current queue、
空 rebind、create receipt ref 与 live snapshot ref；它明确排除
`goal_transitions`、`transition_anchor`、`binding_digest` 及所有由 sequence-0 派生字段。
`initial_projection_digest` 固定为 ASCII
`specrail.goal.initial-projection.v1\0` + projection RFC8785 bytes 的 SHA-256。
sequence-0 evidence 只绑定 exact build、create receipt、live snapshot 和该 projection
digest。生成 event/anchor 后，`binding_digest` 才覆盖完整 bundle（排除自身）。
projection→event→final bundle 的顺序唯一，gate 按相同投影重算，不存在 digest 覆盖自身。

checkpoint v4 只持久化这个 bundle object，不散放需要 skill 组装的局部字段。
sequence-0 event、current snapshot、baseline/projection/final digest 都由 binder 重算并写入。
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

- sequence 0 `active`: exact build envelope、attested create receipt、bind-time live snapshot
  与上一节的 `initial_projection_digest`；
- `complete`: content-bound pre-update GitHub queue artifact 证明 empty/fully blocked/only
  human decisions，绑定 attested `update_goal(complete)` result，并另有因果上晚于该
  receipt 的 content-bound post-update queue artifact；
- `exhausted`: attested live usage/budget snapshot、content-bound checkpoint/handoff artifact
  与 attested terminal result；
- `interrupted`: runtime-owned interrupt attestation、latest checkpoint/handoff digest 与
  attested interrupted result；
- `blocked`: schema-valid gate rejection/blocker artifact、reason IDs 与 attested blocked
  result。

agent-facing terminal flow 是固定两阶段命令：

```text
python3 checks/goal_contract.py prepare-transition \
  --binding <active-binding.json> --to <terminal-status> \
  --transition-evidence <canonical-prerequisite.json> \
  --action-attestation <runtime-action.json> --json
python3 checks/goal_contract.py finalize-transition \
  --binding <transition-pending-binding.json> \
  --update-result-evidence <host-update-receipt.json> \
  --live-goal-evidence <host-live-snapshot.json> \
  [--post-update-queue-evidence <github-artifact.json>] --json
```

`prepare-transition` 先输出含 `pending_transition` 的完整、schema-valid active binding，
其 closed 字段为 transition ID/from/to、prior revision/tail/binding digest、prerequisite
refs/digests、action sequence、exact update request digest 与 provider idempotency key。
checkpoint writer 必须在调用 `update_goal` 前持久化该 bundle；pending 期间不得开 lane、
rebind、发其它 remote write 或进入第二个 transition。CLI 只输出 exact `update_goal`
object，不自行调用 Goal tool。

`finalize-transition` 只接受 exact pending 对应的 update receipt/live snapshot；它从
provider 以 request digest 查回 immutable receipt，验证 revision/status/tail 后追加唯一
event、清除 pending 并输出完整 bundle。若 tool 已成功但本地写入前崩溃，resume 对同一
pending 重跑此命令即补写相同 event；若 event 已存在则返回字节不变的 bundle。没有
pending、receipt/revision/tail 不匹配或 provider 不支持 receipt lookup 时
`blocked: terminal_reconciliation_invalid`，不得恢复 active 或创建新 Goal。

`complete` 的 finalize 额外要求 `post_update_queue_evidence` 和 runtime-owned causal
order attestation，证明 collection 在 update receipt 后开始。post snapshot 仍有
actionable item 时不得写 complete checkpoint；命令保留 external complete receipt 与
pending audit，返回 `needs_human: queue_changed_after_goal_complete`，等待人工决定新
Goal，不把已 terminal Goal 反激活。

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
action_sequence, action_attestation_ref,
prev_event_digest, event_digest
```

唯一 producer 是：

```text
python3 checks/goal_contract.py rebind \
  --binding <active-binding.json> \
  --github-evidence <fresh-adapter-artifact.json> \
  --live-goal-evidence <host-live-snapshot.json> \
  --action-attestation <runtime-action.json> --json
```

它只输出 `{decision,reason_ids,goal_binding,errors}` closed envelope；allowed 时
`goal_binding` 是包含新 event/current snapshot/final binding digest 的完整 bundle，
blocked 时为 null 且 exit 1。没有其它 transition/rebind command 名、隐式参数或
skill-side event composition。

第一次 `prior_digest` 等于 baseline，之后等于前一 event 的 current digest。loader
必须校验 `github_goal_evidence` collector/schema/file SHA，重算 artifact digest、
records/current digest，并要求 repo/default-base 与 stable scope 匹配、完整分页且
`as_of` 不早于前一 rebind。caller 自报 digest 或只有内部链一致性不算 remote truth。
GitHub item state/head 变化、新增或移出 actionable 集合是合法同-scope rebind，不修改
contract digest；repo/run/fencing/scope 变化、直接改 current、evidence reuse、断链或
snapshot digest 不匹配必须阻断并要求新 Goal/人工决策。

每次 resume、pre-lane、checkpoint write、rebind、prepare/finalize transition 与其它
remote write 前，受保护 runtime 必须出具单调 `ActionAttestation`：

```text
action_sequence, action_id, action_type,
prior_checkpoint_digest, github_evidence_ref, live_goal_evidence_ref,
repo_id, run_id, fencing_token, prior_action_digest, action_digest,
issued_at, attestation
```

queue binding 持久化完整 `action_reanchors[]`；sequence 从 1 连续递增，一个
attestation 只能绑定一个 action/type/目标 digest。gate 不尝试数 chat turn，也不读
session transcript，而是要求每个可从 checkpoint/queue/remote evidence 观察到的受保护
action 都有相邻 re-anchor。缺号、reuse、fresh evidence 早于前一 action、action 没有
对应 attestation 或 attestation 没有动作都 fail closed。

### 6. schema 与 runtime gate

`schemas/goal_contract.schema.json` 定义 active contract/binding state；
`schemas/goal_evidence.schema.json` 定义 routing/capability/GitHub/tool/transition
evidence 与 references。`schemas/runtime_checkpoint.schema.json` v4 通过 `$ref`
要求恰好一个 closed `goal_binding`，其 `binding_state` 是：

```text
active | disabled | migration_pending
```

`disabled` 只能由 verified invocation/capability/budget evidence导出：
`review_mode`、`bounded_tranche`、`capability_unavailable` 或可信 evidence 同时证明
user/pack budget 均 absent 的 `missing_budget`。前三者的 build decision 是
`allowed`，`missing_budget` 是 `needs_human`；两者都返回完整 disabled binding。
`invalid_budget`、missing/invalid attestation 或声明存在但不可验证的 budget 是
`blocked` 且不返回 binding，不等于 disabled。
auto + full_queue_drain + verified capability available +合法预算要求 `active`；
已存在 active bundle 不允许通过后来声称 review/bounded/unavailable 移除 Goal。

active binding 的 checkpoint/Goal status 只允许下表，不做 literal equality，也不允许
ad hoc fallback；`schemas/runtime_checkpoint.schema.json` 同步扩展两个 queue terminal
stop reason：

| Goal status | checkpoint `status` | `budget.stop_reason` |
| --- | --- | --- |
| `active` | `planning` / `running` / `handoff` | `null` |
| `complete` | `complete` | `queue_empty` / `queue_fully_blocked` / `only_human_decisions` |
| `exhausted` | `handoff` | `budget_exhausted` |
| `interrupted` | `handoff` | `user_interrupt` |
| `blocked` | `blocked` | `blocked` |

disabled binding 不包含 Goal status，沿用 routing 对 checkpoint 的既有规则。
`pending_transition` 在 local active + external terminal 的窗口只允许
`finalize-transition` recovery，不按普通 active 行放行。terminal+running、
complete+null、active+任一 stop reason、exhausted+complete 等所有表外组合稳定
`blocked: goal_checkpoint_status_mismatch`。

runtime gate 调用共享 `validate_goal_contract()`，一次性交叉校验：

- routing/capability/tool receipt attestation 与 repo/run binding；
- policy bytes、merged PR/approval event、budget selection 与 contract digest；
- immutable queue baseline、content-bound current/rebind chain；
- canonical transition evidence、local chain 与 external live anchor；
- repo/run/fencing 与 GH-189 lease evidence；
- action re-anchor sequence、tokens/status/terminal prerequisite，以及上表的
  checkpoint status/Goal status/stop_reason。

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
pending_build_digest, create_request_digest, create_idempotency_key,
create_state:"create_required" | "create_inflight",
allowed_recovery_actions:["create_goal_from_pending","finalize_goal_migration"]
```

该分支 schema-valid；runtime gate 稳定返回
`blocked: goal_migration_pending`，禁止 lane/checkpoint completion 与无关 remote writes。
唯一创建路径是：

```text
python3 checks/goal_contract.py create-goal-from-pending \
  --pending <migration-pending-binding.json> \
  --capability-evidence <host-capability-attestation.json> --json
```

命令验证 exact pending/build/request digest 后，先输出需持久化的
`create_state:"create_inflight"` pending bundle，再输出唯一 `create_goal` args、
`create_request_digest` 与 provider `create_idempotency_key`；CLI 本身不调用 Goal tool。
host 必须按 `(repo_id,run_id,migration_id,pending_build_digest)` 幂等创建，并支持从
request digest 查回同一 receipt。相同 pending 重试只能得到相同 key/receipt/goal ID；
request 漂移或第二个 goal ID 阻断。

随后唯一完成路径是：

```text
python3 checks/goal_contract.py finalize-goal-migration \
  --pending <create-inflight-binding.json> \
  --create-result-evidence <host-create-receipt.json> \
  --live-goal-evidence <host-live-snapshot.json> \
  --github-evidence <fresh-adapter-artifact.json> --json
```

finalize 消费 exact pending 与 attested create/live receipts，原子输出完整 active
`GoalCheckpointBinding`；tool 成功后崩溃的重试从 provider lookup 复用同一 receipt，
不得再创建 Goal。
unsupported source、证据缺失或 final bundle 非法时 exit 1 且 pending 保持不变。

### 8. upstream dependency route gate 与 queue 集成

fresh GitHub truth 显示 GH-172/PR #186、GH-174/PR #192、GH-189/PR #193 均仍 OPEN、
`mergedAt=null`，origin default branch 没有其最终 runtime assets。GH-174 与 GH-190
planned manifests 精确重叠以下七个路径：

```text
AGENT_USAGE.md
CHANGELOG.md
checks/check_workflow.py
skills-lock.json
skills/implx/SKILL.md
skills/specrail-implement-queue/SKILL.md
tests/test_check_workflow.py
```

因此本文件顶部新增 `specrail-implementation-dependencies-v1` closed marker；
`checks/check_workflow.py` 验证 issue 唯一、依赖无重复、serial order 完整、overlap path
精确存在于两份 trusted manifest，未知 stage/path 或漏掉实际 overlap fail closed。
`checks/github_issue_evidence.py` 对每个 dependency 完整分页收集 issue、spec PR、实现
PR、mergedAt/merge commit、target default-base ancestry 与 head/base；closed
`schemas/issue_evidence.schema.json` 保存 adapter-owned evidence，不接受 caller
`merged:true`。`checks/route_gate.py` 对 `implement` 离线要求：

```text
GH-172 contract + runtime implementation merged into target default base
→ GH-174 在其后 rebase，contract + runtime implementation merged
→ GH-189 在 GH-174 后 rebase，contract + runtime implementation merged
→ GH-190 branch base/head ancestry 证明已在三者之后 rebase
```

这里的顺序是七个共享资产与 lease/queue layout 的集成串行门，不声称 GH-189 issue 在
产品语义上依赖 GH-174。open/closed-unmerged PR、只合并 spec、实现 PR 未覆盖声明资产、
merge commit 不在 trusted target base、实际 overlap 与 marker 不同、相邻 rebase
缺失或 branch head 基于旧 base 均 `blocked: upstream_dependency_not_ready`。只有
`issue-gh190-dependencies-ready.json` 正例可进入 implement；open 与 overlap-unrebased
fixtures 必须 schema-valid 但被 route gate 拒绝，不能把人工 handoff 当机械门。

rebase 后 GH-190 只引用 GH-189 提供的 repo identity、`run_id`、`fencing_token`、lease
evidence/schema/helper，并在 GH-174 canonical phase/reference layout 上接入 Goal CLI；
不复制字段、queue reference 或另建 fallback。contract/path 冲突必须回到 spec review，
不得由实现者静默择一。

queue 与 implx 两个入口只调用 evidence adapter + `build`/`bind`/`rebind`/
`prepare-transition`/`finalize-transition`/migration CLI，不再拼 objective、Goal ID、
routing、remote digest、event/bundle 或 conservative default。主 Skill 在 GH-174
完成后的 canonical layout 保留不可绕过 marker，详细操作放其 runtime reference。

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
| B-029 | non-circular initial projection/sequence-0/final digest | `python3 -m pytest -q tests/test_goal_contract.py -k "initial_projection or sequence_zero or binding_digest"` |
| B-030 | four distinct build evidence inputs | `python3 -m pytest -q tests/test_goal_contract.py -k "invocation_input or capability_input or evidence_separation"` |
| B-031 | separate bind-time live snapshot | `python3 -m pytest -q tests/test_goal_contract.py -k "bind and live_snapshot"` |
| B-032 | migration one-shot idempotent Goal create | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "migration_create or idempotency or receipt_reuse"` |
| B-033 | adapter-owned upstream route evidence | `python3 -m pytest -q tests/test_github_issue_evidence.py tests/test_route_gate.py -k "dependency or implementation_merged"` |
| B-034 | domain-separated create request digest | `python3 -m pytest -q tests/test_goal_contract.py -k "create_request_digest or request_mismatch"` |
| B-035 | closed rebind/transition CLI | `python3 -m pytest -q tests/test_goal_contract.py -k "rebind_cli or prepare_transition or finalize_transition"` |
| B-036 | complete post-update causal queue recheck | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "post_update_queue or false_complete or queue_changed"` |
| B-037 | terminal receipt-bound reconciliation | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "terminal_reconciliation or post_update_crash or finalize_idempotent"` |
| B-038 | deterministic disabled binding producer | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "disabled_binding or missing_budget"` |
| B-039 | action-sequence re-anchor audit | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k "action_sequence or action_reanchor"` |
| B-040 | checkpoint/Goal status/stop-reason matrix | `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_queue.py -k "goal_status_matrix or stop_reason"` |
| B-041 | GH-174 merge/rebase/overlap serialization | `python3 -m pytest -q tests/test_check_workflow.py tests/test_github_issue_evidence.py tests/test_route_gate.py -k "GH190 or overlap or serial_order or rebase"` |

## 数据流

```text
trusted dependency evidence → implement route gate
runtime invocation + distinct capability attestations + GitHub policy/queue evidence + GH189 lease
  → `build` CLI → GoalDraft + exact create_goal args
  → attested create result + separate live snapshot → `bind` CLI → complete v4 bundle
  → action re-anchor → `rebind` or prepare transition → host tool receipt
  → post-update evidence + idempotent finalize/reconcile → complete bundle
  → offline runtime gate
```

## 备选方案

- 继续自然语言拼 objective：不可验证，拒绝。
- schema 只要求非空字符串：无法证明终止/re-anchor，拒绝。
- 在本 issue 硬编码默认预算：越过 GH-160/维护者决策，拒绝。
- 用 Goal status 代替 queue truth：违反既有边界，拒绝。
- 接受 caller 的 mode/capability/Goal ID/digest：无法证明 runtime/GitHub truth，拒绝。
- 让 create receipt 兼作 bind-time live snapshot：不能证明 bind 时仍 active，拒绝。
- 让 sequence-0 evidence 覆盖最终 bundle digest：形成不可计算自引用，拒绝。
- 直接调用 terminal update 再写 checkpoint：崩溃窗口与 false-complete race 不可恢复，拒绝。
- 用“每 chat turn”做 re-anchor 合规单位：gate 不读 transcript，无法验证，拒绝。
- 用 handoff 写“等待 GH-174/GH-189”却不改 route gate：实现仍可启动，拒绝。
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
- Maintenance: evidence adapter、builder、schema、template、queue、GH-174 reference layout
  与 GH-189 lease contract 必须由同一 fixture matrix 对账。

## 测试计划

- [ ] Unit: canonicalization、四终止、attested routing/create receipts、approved policy、
      create-request/initial-projection/final bundle digest、distinct capability/live inputs、
      complete/disabled bind bundle、closed rebind/transition CLI、canonical evidence、
      action sequence、external anchor、content-bound rebind 与稳定错误。
- [ ] Integration: draft/active/disabled/migration-pending schema、runtime gate、
      terminal pending/reconciliation/post-update queue race、status/stop-reason matrix、
      queue/run/GH-189 binding、v1–v3 create/finalize migration。
- [ ] Fixtures: `goal-contract-vectors.json` 至少含 12 个以 hosted root comment ID 命名的
      正反 vectors；三个 `issue-gh190-*` fixtures 分别证明 dependency open、
      exact seven-path overlap 未 rebase 时 blocked，以及
      `GH172→GH174→GH189→GH190` 按序 merged/rebased 时 allowed。所有负例先通过
      schema，再由 evaluator 拒绝。
- [ ] Regression: full pytest、all-specs、depth/diff/hash。
- [ ] Forward-use: dry-run evidence → build → attested fake tool receipt → complete bundle
      → rebind/terminal → live-anchor resume；测试不调用真实 Goal API。

## 回滚方案

回滚 evidence adapter、builder、schema/gate、queue/template、tests/docs/lock 同一实现
提交。不得删除 external terminal anchor 或保留新 active checkpoint 却回滚 validator；
回滚后 Goal 只能视为 candidate/人工状态，GH-189 lease 资产保持其 own rollback policy。
