# Tech Spec

## Linked Issue

GH-180

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":180,"complete":true,"paths":["AGENT_USAGE.md","PLAN.md","README.md","checks/check_workflow.py","checks/duplicate_work_gate.py","checks/pack_asset_validation.py","checks/github_approved_spec_evidence.py","checks/github_duplicate_evidence.py","checks/github_issue_evidence.py","checks/route_gate.py","checks/runtime_invocation_context.py","checks/runtime_invocation_provider.py","checks/runtime_ledger_gate.py","checks/specrail_lib.py","evaluate.py","examples/fixtures/issue-body-hint-ready-to-implement.json","examples/fixtures/issue-ready-to-implement.json","examples/fixtures/issue-ready-to-spec.json","examples/fixtures/issue-reserved-internal.json","integrations/runtime-invocation-provider.md","labels.yaml","schemas/duplicate_work_evidence.schema.json","schemas/evaluation_result.schema.json","schemas/issue_evidence.schema.json","schemas/runtime_checkpoint.schema.json","schemas/runtime_invocation_context.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement/SKILL.md","skills/specrail-plan-tasks/SKILL.md","skills/specrail-workflow/SKILL.md","skills/specrail-write-product-spec/SKILL.md","skills/specrail-write-tech-spec/SKILL.md","templates/pull_request.md","templates/zh-CN/pull_request.md","tests/route_gate_test_support.py","tests/test_check_workflow.py","tests/test_check_workflow_paths.py","tests/test_configured_spec_path_review_regressions.py","tests/test_duplicate_work_gate.py","tests/test_evaluate.py","tests/test_github_duplicate_evidence.py","tests/test_github_issue_evidence.py","tests/test_github_issue_route_evidence.py","tests/test_issue_evidence_freshness.py","tests/test_pack_asset_validation.py","tests/test_route_gate.py","tests/test_route_gate_sensitive.py","tests/test_runtime_invocation_context.py","tests/test_runtime_invocation_provider.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py","workflow.yaml"],"spec_refs":["specs/GH180/bootstrap-evidence.json","specs/GH180/product.md","specs/GH180/tech.md","specs/GH180/tasks.md"]}
-->

## Product Spec

见 `specs/GH180/product.md`。本设计把 packet 的 artifact shape 与 GitHub readiness
拆成两个正交维度：离线 validator 可接受 `staged`，但只有可信生命周期和 route evidence
才能进入 spec-first task planning；该路径的生产代码仍要求有效 `tasks.md`，不改变
direct bug/mixed PR 的既有入口合同。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| packet validator | `checks/check_workflow.py:260-342` | product/tech 必须存在；`tasks.md` 缺失被无条件加入 errors | 这是 product/tech-only spec PR 无法通过 CI 的直接根因 |
| standalone evaluator | `evaluate.py:84-126`、`tests/test_evaluate.py:56-67` | `evaluate_spec()` 独立把缺 `tasks.md` 记为 `spec.tasks_present` failure | 只修 workflow checker 会让公开 evaluator 与 staged 合同继续冲突 |
| CLI aggregation | `checks/check_workflow.py:463-515` | `--all-specs` 只汇总 errors，成功时不报告 packet shape | 需要稳定区分 `staged` / `complete`，且不能暗示 readiness |
| validator unit tests | `tests/test_check_workflow_paths.py:407-585` | 明确断言缺 `tasks.md` 必须失败，并覆盖 packet/file identity 与 task 内容失败 | 必须翻转缺文件正例，同时保留存在但无效 task 的全部 fail-closed 负例 |
| CLI integration tests | `tests/test_check_workflow.py:214-272` | 覆盖 configured root 与 `--all-specs`，尚无 staged/complete 输出断言 | 可证明全量发现、稳定排序与 additive shape audit |
| issue evidence | `checks/github_issue_evidence.py:174-233`、`schemas/issue_evidence.schema.json` | label 来源可标为 trusted，但 evidence 没有必填采集时间或稳定内容摘要；非 sensitive implement 不采 spec approval | 无法拒绝过期 evidence，也会让仅有 readiness label 的普通 issue 绕过 workflow `spec_approval` human gate |
| lifecycle approval | `checks/github_approved_spec_evidence.py:151-315`、`labels.yaml`、`workflow.yaml:87-96` | 已有 helper 能查权限/label event，exact-head sensitive 流程也认识 spec lifecycle label，但普通 implement 没有通用的有序 lifecycle evidence；label timeline 也没有把 approval 绑定到同仓 spec PR revision，或证明 `ready_to_implement` event 晚于 approval | review/default implement 复用既有 GitHub 查询与权限判定，增加 same-repository spec PR exact-head approval 与严格的 `spec_approved < ready_to_implement` event ordering |
| implement artifact policy | `workflow.yaml:103-110` | `implement` action 无条件要求 `product_spec`/`tech_spec` 并创建 `task_plan` | `direct_bug` 合同要求无 spec packet 入场；不加条件 artifact 规则，direct route 会被 core action policy 永久阻断或被迫绕过 |
| authorization mode | `workflow.yaml:15-58`、`skills/implx/SKILL.md:53-109` | 持久化 baseline 是 review；只有当前用户明确发起的 `implx auto` invocation 可临时选择 auto，且 auto policy 明确 waive `spec_approval` | 实现必须消费而不是改写该 policy；review 要 exact-head lifecycle approval，auto 要 runtime-owned invocation grant，caller record 仅作 selector；二者都不能 waive readiness 或其它 current evidence |
| current invocation trust | search-first 未发现现有 route trust-anchor/provider adapter、runtime-owned grant registry 或 host integration contract；runtime checkpoint/tier authorization 只覆盖队列/merge，不证明 route caller 的 current invocation | caller record 可自报 `invocation_id`、grant 与 waived gates；若 provider 只签 caller digest，agent 可自行制造授权，旧同 issue/route record 与 saved result 也可跨 invocation 重放 | 新增 provider/context/integration assets；固定 authenticated IPC 查询 runtime-owned current-generation + grant registry，caller record 仅作 selector，runtime-owned portable verifier 校验 Ed25519/JCS/trust store |
| portable verification | fresh-checkout Python 环境没有可依赖的 `cryptography`、`nacl`、`jcs` 或 `rfc8785` manifest/安装合同 | 单靠 client spec 要求 Ed25519/RFC8785 无法保证普通 checkout 可运行 | host runtime package 必须提供固定 authenticated verifier interface；repo client 只做闭合 schema/binding 与 verifier IPC 调用，不 vendor 私钥/自选 backend，verifier 缺失时 auto fail closed |
| duplicate-work evidence | `checks/github_duplicate_evidence.py`、`checks/duplicate_work_gate.py:134-197`、`schemas/duplicate_work_evidence.schema.json` | collector/gate 能验证 open PR/remote branch 完整性，但无条件拒绝每个引用 issue 的 open PR 与匹配 branch，无法识别作为 approval source 的 exact spec-only PR；saved route consumer 也不要求 fresh duplicate evidence或限制 evidence 年龄 | 必须只排除 approval object 精确绑定的同仓 spec-only PR/head branch，其它候选与任何 identity/head/path/query 漂移继续 fail closed；saved result 后的新 PR/branch 也必须使旧成功失效 |
| route result contract | `checks/route_gate.py:513-516`、`schemas/evaluation_result.schema.json:6-89` | `allowed_actions` 仅按 lifecycle state 加入 `implement`，`decision=allowed` 不区分 staged task planning 与 complete production implementation | staged allowed result 可被旧 consumer 直接当成生产实现授权；必须增加闭合 scope/capability 并让 verify-result 按消费目的拒绝错用 |
| route gate | `checks/route_gate.py:240-405`、`SPEC.md`、`states.yaml` | readiness route 可接受 CLI `--state`，CLI `--label` 又在推断前并入 labels；当前仓库同时允许 accepted-small-bug 的 `triaged → ready_to_implement`，不能把 staged spec lifecycle 套到所有实现入口 | 两种自报入口都可绕过可信 label；新 gate 还必须从可信 evidence 区分 spec-first/direct-bug/mixed-PR，不能阻断已有合法入口或复用漂移后的 route success |
| mixed queue route | `skills/specrail-implement-queue/SKILL.md`、`schemas/runtime_checkpoint.schema.json`、`checks/runtime_ledger_gate.py` | standard/fastlane 允许同一个 `mixed_impl` PR 承载 spec/tasks/implementation，并无更早的独立 spec-only PR；checkpoint 的 `pr_tier` 由 agent 写入、schema `additionalProperties: true`，独立背书（CI tier-check / reviewer `tier_attestation`）目前只在 merge authorization 消费 | universal spec-PR prerequisite 会使既有 mixed route 永远无法入场；route 入场分类必须有闭合、gate 校验且带独立背书的 planning-evidence 来源，不能信任 caller-writable tier 字段 |
| sensitive enforcement | `checks/sensitive_enforcement.py`、`tests/test_route_gate_sensitive.py` | existing `approved_spec` 要求 approved revision 已 merge 到 trusted default base，并验证 `merged_at`、`merge_commit_sha` 与 ancestry | open exact-head approval 可建立 spec-first lifecycle，但不能替代 sensitive production 的 merge-first 追加门禁 |
| evidence regressions | `tests/test_github_issue_evidence.py:245-760`、`tests/route_gate_test_support.py:142-181`、`tests/test_configured_spec_path_review_regressions.py:155-345`、`examples/fixtures/issue-*.json` | 既有断言允许 readiness CLI state，trusted helper/fixtures 没有采集时间；主测试文件 851 行 | freshness 收紧会影响现有全量回归，必须纳入 manifest，并把超限文件按现有 route-evidence 模块拆分 |
| agent contract | `AGENT_USAGE.md:86-130` | Basic Flow 列出三种 artifact，却未说明 write_spec 与 implement 的分阶段所有权 | agent 容易把 validator 的完整性要求误读为提前生成 tasks |
| roadmap contract | `PLAN.md:98-108` | 非 sensitive plan 被描述为无需 approval timeline，sensitive approval source 限定为 merged default-branch PR | agent entry 要求读取 PLAN；应补齐 spec-first 的 open exact-head lifecycle，同时保留 direct/mixed route 及 sensitive merged-base production gate |
| shared runtime mapping | `checks/specrail_lib.py:35-49`、`tests/test_runtime_ledger_gate.py:34-51` | `needs_tasks` 仍映射到 `spec_approved`，shared regression 只检查 target 存在于 workflow state 集 | 新合同要求 fresh `ready_to_implement` 后才进入 task planning；mapping 与 exact-value regression 必须同步 |
| route router | `skills/specrail-workflow/SKILL.md:16-45` | 路由到 product、tech、tasks focused skill，但未明示 staged packet 的交接条件 | 需声明 product/tech 完成后等待真实 `ready_to_implement`，不能靠 shape 跳状态 |
| focused write/implement | `skills/specrail-write-product-spec/SKILL.md:12-23`、`skills/specrail-write-tech-spec/SKILL.md:12-21`、`skills/specrail-implement/SKILL.md:12-21` | focused skills 仍以 CLI `--state` 自报；direct implement 预读 tasks 且未定义缺 tasks 的交还顺序 | 新 route policy 会让真实入口自阻塞或绕过 staged handoff |
| task planning | `skills/specrail-plan-tasks/SKILL.md:12-29` | 读取 product/tech，运行 implement gate，再创建 tasks | 需改为 fresh issue evidence 入场，并明确 tasks 后重跑 complete snapshot |
| queue coverage | `skills/specrail-implement-queue/SKILL.md:48-70` | `needs_tasks` 与 `complete` 已分开，只有 complete 可进入生产实现候选 | 作为生产代码前的 deterministic enforcement，与新的结构 validator 对齐 |
| implx auto entrypoint | `skills/implx/SKILL.md:83-109`、`skills/specrail-implement-queue/SKILL.md:101-123` | shorthand 允许同轮 draft/implement，但没有完整写出 staged 后重采 evidence、tasks 后重验的顺序 | 顶层入口不能让 auto waiver 被误读为 freshness 或 snapshot waiver |
| public docs/templates | `README.md:89-101`、`templates/pull_request.md:10-14`、`templates/zh-CN/pull_request.md:10-14` | README 示例仍使用 CLI `--state`；PR 模板对 staged spec PR 也要求 `ready_to_implement` | 公开入口必须区分 spec PR 与 implementation PR readiness |
| distributed skills | `skills-lock.json:5-73` | 七个将修改的 skill 都由内容 hash 锁定 | 文档变化后必须只更新对应 hash，保持分发完整性 |

## 设计方案

### 1. 纯 artifact shape 分类

在 `checks/check_workflow.py` 新增只读 helper：

```text
spec_packet_shape(spec_dir) -> invalid | staged | complete
```

- product 或 tech 文件任一缺失时返回 `invalid`；后续 validator 继续报告具体缺失项。
- product 与 tech 均存在、tasks 不存在时返回 `staged`。
- 三文件均存在时返回 `complete`；即使 tasks 内容无效，shape 仍是 `complete`，同时
  validation 失败，禁止把坏 task 静默降级成 staged。

shape 只描述当前 artifact presence，不读取 label、不接触 GitHub、不产生 readiness 或授权。
相同文件 snapshot 的分类稳定且幂等。

### 2. staged-aware 内容校验

保留 `validate_spec_packet(spec_dir) -> list[str]` 公共签名，避免改变所有调用方，并让
standalone `evaluate.py` 使用同一 staged/complete 语义：

- product/tech 的 identity、linked issue、非空与 planned-changes manifest 规则逐字保留；
- tasks 不存在时不再产生 `missing tasks.md` error；
- tasks 存在时仍执行 identity/symlink/非空、稳定 task ID、Owner/Done when/Verify 和重复 ID
  全部现有校验；任何错误都使整体命令非零；
- product/tech 任一缺失或无效时仍失败，不因 tasks 是否存在而降级。
- `evaluate_spec()` 对缺 tasks 输出可审计的 staged/optional 结果而非
  `spec.tasks_present` failure；tasks 存在时继续执行全部 task format checks。

`main()` 对显式或 `--all-specs` 选择出的 packet 按现有稳定路径顺序记录 shape，并在结果中
输出 `Spec packet <path>: shape=<staged|complete|invalid>; readiness=unproven`。该行在成功和失败
路径都输出；最终 `SpecRail check passed/failed` 与 exit code 保持兼容。离线命令没有 GitHub
evidence，因此 readiness 固定为 `unproven`，不会把三文件齐全冒充 implementation-ready。

### 3. 可信 lifecycle/readiness 与 snapshot-bound route gate

保持 `workflow.yaml` 的 auth policy（`workflow.yaml:15-58`）逐字节不变；`workflow.yaml`
仅新增一条按 `implementation_entry_kind` 的条件 artifact 规则：`implement` 对
`spec_first`/`mixed_impl` 继续要求 `product_spec`+`tech_spec` 并创建 `task_plan`，对
`direct_bug` 免除这三项（保留 `linked_issue` 与全部 human gates），使 accepted-small-bug
direct route 不再被无条件 artifact 要求阻断，也不需要绕过 core action policy。在此之上
收紧 issue/lifecycle/duplicate collectors 与 `route_gate`：

- 在应用 staged lifecycle 前，route gate 必须从 trusted issue transition、packet/PR relation
  与 queue-derived tier 计算闭合的
  `implementation_entry_kind: spec_first | direct_bug | mixed_impl`。`spec_first` 要求可信轨迹从
  `ready_to_spec` 开始并存在独立 exact-head spec PR；`direct_bug` 要求没有 spec packet，且有
  `SPEC.md` 已定义的 accepted-small-bug expected/actual evidence 和可信
  `triaged → ready_to_implement`；`mixed_impl` 必须仅从实现开始前即可取得的 trusted
  planning evidence 分类：queue-derived standard/fastlane tier、queue coverage 记录的
  single-PR 计划关系，且没有更早的独立 spec-only source。该 planning evidence 有明确定义的
  可信来源：`schemas/runtime_checkpoint.schema.json` 为 route 消费的 planning-evidence
  子对象收紧出闭合 shape（`additionalProperties: false` 的
  `pr_tier ∈ {standard, fastlane}`、`pr_tier_evidence`、single-PR relation 与独立背书引用），
  `checks/runtime_ledger_gate.py` 校验该 shape 后 route gate 才可读取；tier 必须带既有
  GH-143 独立背书之一——gate 可验证的 CI tier-check artifact 或 reviewer-lane
  `tier_attestation`——self-declared tier 或缺背书时该 route 以 `needs_human` fail closed，
  不得静默归入 `spec_first`、不得直接 allowed，也不得由 CLI/manifest/PR body 补供 tier。
  schema/ledger 校验只证明 checkpoint 的结构，不证明来源，因此 single-PR relation 与 tier
  受同等强度的 provenance 约束，不得作为 agent 自写的 checkpoint 值被信任：route gate 必须
  由 `checks/github_duplicate_evidence.py` 对该 issue 现采的 fresh GitHub 状态**独立重算**该
  relation——同一 issue 当前恰好只有这一个未关闭的 linked PR，且不存在更早的独立 spec-only
  PR/branch source——并要求重算结果与 checkpoint 记录逐字段相等；两者不一致、采集不完整或
  GitHub 侧无法判定时以 `needs_human` fail closed。等价地，若独立背书 artifact（CI
  tier-check 或 reviewer-lane `tier_attestation`）自身同时 attest 该 relation，也可作为可信
  来源；但仅有合法 tier 背书 + checkpoint 自写 relation 的组合永远不足以判定 `mixed_impl`。
  入场分类不得以"PR 已包含生产
  代码"为前提，同一 PR 真实承载 spec/tasks/implementation 的完成态 mixed relation 由该 PR
  既有的 final-review/merge gate 在实现完成后验证。该值不得由 CLI、manifest 或 PR body选择；
  缺失、矛盾或同时匹配多个 kind 时 fail closed。只有 `spec_first` 进入下述 staged spec
  approval lifecycle；direct/mixed 继续执行各自现有 duplicate、readiness、approval/final-review
  gate，且 `mixed_impl` 不生成 `approved_spec_pr_exemption`；
- issue evidence schema 新增必填 UTC `collected_at`；collector 在完成同一次 issue query 后写入，
  route gate 对 readiness-sensitive route 使用显式、可配置且有安全默认值的最大年龄，拒绝缺失、
  无效、未来或超窗时间。每次采集同时计算两个不同用途的摘要：
  `issue_evidence_envelope_sha256` 覆盖完整 canonical envelope（包含 `collected_at`）用于审计本次
  实际输入；`issue_evidence_snapshot_sha256` 从闭合对象中只删除顶层 `collected_at` 后再
  canonicalize/hash，用于 route 与 `--verify-result` 的跨 fresh-capture 语义比较。不得再用
  envelope hash 作跨采集 equality，也不得从 semantic snapshot 排除其它字段；
- 当 route 含 `readiness_label` human gate 时，只接受 `--evidence` 中
  `state_source=label`、`state_trusted=true` 且 issue 一致的状态；`--state` 只可用于不依赖
  readiness label 的 route/诊断，`--state ready_to_*` 与
  `--label ready_to_spec|ready_to_implement` 都必须明确拒绝，不能在 state inference 前注入可信状态；
- 在 `labels.yaml` 声明 `spec_pr_open`、`spec_review`、`spec_approved` lifecycle labels。
  `github_approved_spec_evidence.py` 复用现有 label timeline、default-base 与 permission 查询，
  为 `spec_first` review/default 路径的 trusted `ready_to_implement` issue 收集闭合的
  `spec_lifecycle_approval`：
  四个 transition `ready_to_spec → spec_pr_open → spec_review → spec_approved` 必须属于同一
  issue、按时间有序、终态为当前/latest `spec_approved`（缺少起始 `ready_to_spec` 事件即
  拒绝，否则直接跳到 `ready_to_implement` 后补三个 label 也能伪造出通过链，而 product
  invariant 要求完整生命周期）。approval actor 的 repository permission 必须满足现有
  maintainer policy，且 snapshot 前后 issue identity/labels 不得漂移。collector 还必须取得
  被接受 `ready_to_implement` label event 的 event id、actor 与 timestamp，并对该 actor 独立
  执行相同的 repository permission lookup/threshold；缺 actor、权限查询失败、unknown/none/read
  或低于 maintainer policy 均以 `readiness_actor_unauthorized` fail closed，不能以 label event
  存在、actor 能操作 label 或 approval actor 已获授权代替。该 timestamp 必须严格晚于 accepted
  `spec_approved` event。collector 必须把被接受 exact-head `APPROVED` review 的
  `submittedAt` 纳入 lifecycle ordering，并要求
  `approved_review.submittedAt < spec_approved_event.timestamp <
  ready_to_implement_event.timestamp`。对同一 exact head 有多个 APPROVED review 时，按
  `(submittedAt, review_id)` 稳定选择满足 maintainer policy 且早于 accepted
  `spec_approved` event 的最新一条；不存在这样的 review 时拒绝。被接受的 approval 还必须在
  采集与每次 `--verify-result` 复验时都保持该 PR 当前最新的有效 review decision：collector
  必须枚举同一 PR 上晚于 accepted approval `submittedAt` 的全部 review（不限 commit OID），
  只要存在任一 `CHANGES_REQUESTED`，或 accepted `APPROVED` review 已被 dismiss/撤回，即以
  `approval_superseded_by_change_request` fail closed——同一 exact head 上后续的阻断性
  review 表示当前评审状态已不再是 approved，早先的 approval 不得继续授权实现；该检查在
  consumer 消费/复验时必须重新执行，不能只依赖采集时刻的快照。仅仅在 approval 之后
  重新采集一个早已存在的 readiness label 必须以 `readiness_precedes_spec_approval` 拒绝；
  先打 `spec_approved`/`ready_to_implement`、后补 exact-head review 必须以
  `approval_review_after_lifecycle` 拒绝，不能追溯授权。

  approval source 必须是同一 repository 中绑定 GH-180 的 spec PR，而不是 fork、当前工作树或
  default-base 猜测。闭合 object 记录 repository id、PR number、base repository/ref、
  `approved_spec_head_sha`、maintainer approval review id/actor/timestamp/commit OID，以及
  lifecycle event id/timestamp；review 的 commit OID 与 PR exact head 必须相等，采集时 PR
  head 也必须仍等于该 SHA。lifecycle 事件链必须绑定该 selected source PR 的身份：closed
  object 额外记录 source PR 的 `createdAt`，被接受的 `spec_pr_open`、`spec_review`、
  `spec_approved` label events 必须全部严格晚于该 `createdAt`；早于它的 event 只能归属另一
  个（例如已关闭的）spec PR，必须以 `lifecycle_event_predates_source_pr` 拒绝，禁止把旧 PR
  的 open/review 事件与新 PR 的 approval/readiness 拼接成"一条完整生命周期"。source PR 的
  base 也必须绑定 trusted default base：collector 在同一采集轮次 fresh 查询 trusted default
  branch snapshot，要求 source PR 的 base repository 为同一 repository、base ref 精确等于该
  trusted default branch，并记录当时的 base OID；因此 `changed_paths` 的 spec-only 判定
  相对 trusted default base 成立，base 指向任意非默认分支（其上可能已含实现文件）、base
  repository 不同或 consumer 重验时该 binding 漂移，均以 `spec_pr_base_untrusted` fail
  closed。collector 用 GitHub blob API 从该不可变 SHA 读取配置路径下的
  product/tech bytes，按稳定路径与逐文件 sha256 生成 `approved_spec_snapshot_sha256`。
  route 对当前 product/tech 独立生成 `spec_snapshot_sha256` 并比较；不读取 tasks。任一来源
  不唯一、跨 repository、head 漂移、approval 不在 exact head、blob 缺失/不匹配，或当前
  `spec_snapshot_sha256` 改变，都以 `spec_approval_stale` fail closed。`github_issue_evidence.py`
  在 review/default implement evidence 中嵌入该对象；schema 禁止开放字段；
- `spec_lifecycle_approval` 同时提供 duplicate gate 唯一可用的
  `approved_spec_pr_exemption`：闭合字段为 immutable `repository_id`、canonical
  `repository`、`pr_number`、`head_repository_id`、`head_ref`、`approved_spec_head_sha`、
  `changed_paths_complete: true` 与排序后的 `changed_paths`。在读取 caller-controlled
  manifest `spec_refs` 前，shared `specrail_lib` 必须先从 `workflow.yaml` 的 artifact templates
  与 closed role table 派生 issue-bound allowlist：通用 classifier 只返回
  `product_spec | tech_spec | task_plan | invalid`，不得硬编码 `bootstrap-evidence.json` 或公开
  `packet_evidence` role；CLI、manifest、PR body 与 collector caller 都不能添加 role/path。
  GH-180 approval/duplicate consumer 另有窄化 overlay：仅当 issue 精确为 180、路径精确为
  `specs/GH180/bootstrap-evidence.json`，且 JSON 同时满足 `version: 2`、`issue: 180`、
  顶层 `authorization_effect: none`、`observed.authorization_effect: none`、
  `evidence_verdict.authorization_effect: none` 与
  `evidence_verdict.status: partial_unproven`，且候选文件原始 bytes 的 sha256 精确等于
  实现中 pinned 的 canonical tracked `specs/GH180/bootstrap-evidence.json` 全文件 digest
  时，才返回不可复用的 `gh180_bootstrap_audit`。字段谓词只用于诊断性报错，不是接受条件的
  全部：全文件 digest 才是 classification 的接受边界，因此谓词未覆盖字段的改写（例如把
  `reported.authorization_claim.claim_status` 从 `reported_unproven` 改成 `proven`）或删除
  `unproven` 段落同样 `invalid`。它只让本 PR 的 exact changed-path equality 可验证，不产生
  readiness/approval/waiver；复制到其它 issue、错误路径或任一字节级内容漂移均为 `invalid`。
  manifest `spec_refs` 必须是通用 allowlist 加该精确 overlay 结果的
  无重复子集、必须含 product/tech，并与 manifest implementation `paths` 完全 disjoint；
  不满足即 source classification invalid，不能进入 exemption 判断。changed paths 必须精确等于
  source PR 的完整 path 集并全部属于 validated `spec_refs`；因此正常 staged PR 可只有
  product/tech，GH-180 bootstrap 可包含经分类的 tasks/evidence，但把 `src/change.py` 等实现
  文件移入 `spec_refs`、遗漏/伪造 role、同时放入 paths/spec_refs 或出现未声明 path 都使
  exemption 失效。collector 从同一 exact-head PR 查询得到 path 集与 head identity，caller
  不能自报 `spec_only`。route 把该闭合对象交给 duplicate gate，gate 仅从 open-PR
  candidates 排除 repository id + PR number + head repository/ref/SHA + 完整 path 集全部相等的
  那一项，并仅从 remote-branch candidates 排除该 exact head repository/ref/SHA。每次 fresh
  collection 都必须重查 source PR 的当前状态：仅 open 或可验证 merged（`merged_at` 与
  `merge_commit_sha` 存在且一致）的 PR 是有效 approval source；closed-unmerged 的 PR 以
  `spec_approval_source_abandoned` fail closed，即使 issue lifecycle labels 未同步清理，其
  approval 与 exact-head branch exemption 一并失效。source PR 已 merged 时，其同一
  exact-head branch 仍可按该 binding 排除。任何字段缺失、查询不完整、
  fork、额外 path、head/branch 漂移或第二个引用 issue 的 PR/branch 均不享受 exemption，继续
  `blocked`/`needs_human`。auto 路径没有 human approved spec PR，因此没有该 exemption；
- `workflow.yaml` 进入 planned changes，但改动严格限于上述 `implement` 条件 artifact
  规则；auth policy 保持原样：persisted/default
  `auth_mode` 是 review；只有当前用户明确发起的 auto invocation 才能选择 transient auto 并
  waive `spec_approval`。`route_gate` 为 review/default 路径离线重验完整 lifecycle object；
  auto 路径要求 `--auth-mode auto --auth-evidence <invocation-authorization.json>`，随后由
  `checks/runtime_invocation_provider.py` 内部连接固定 runtime service 并执行 challenge-response；
  CLI 没有 endpoint、provider、verifier、trust-root、keyset 或 signed-context 参数。caller
  authorization record 必须只包含 runtime registry `grant_id` 与待匹配的
  invocation/repository id + canonical name/issue/route selectors；其 `auth_mode`、waived
  gates、actor/source 或 digest 都不能成为 authority。
  provider 先通过 authenticated transport session 确定 current invocation/generation，再用
  `grant_id` 查询 runtime-owned、caller 不可写的 authorization-grant registry；只有 registry
  中由用户授权、active、未撤销、未过期且与 current invocation/immutable repository id +
  canonical name/issue/route、`auth_mode: auto` 和精确
  `waived_human_gates: ["spec_approval"]` 匹配的 grant 才可签发 response。response 绑定
  runtime canonical grant 的 `authorization_grant_sha256`，而不是签任意 caller record digest。
  missing/unknown/revoked/expired/mismatched grant 一律拒绝。

  `checks/runtime_invocation_context.py` 按闭合 schema 校验 response shape/binding，并把完整
  envelope 连同期望 challenge 交给 runtime package 保证提供的固定 authenticated verifier
  interface；verifier 独占 RFC8785-JCS bytes、Ed25519、OS/runtime trust-store keyset、
  not_before/not_after/revoked_at 与 rotation 规则。repo 不假设 fresh checkout 存在未声明的
  Python crypto/JCS module，也不接受 caller backend。provider/verifier 不可达、peer 不可信、
  unknown key、签名/JCS 错误、过期/未来 response、非 current generation 或任一 binding 不匹配
  均 fail closed。route result 绑定 `authorization_grant_sha256`、
  `runtime_invocation_context_binding_sha256`、invocation id/generation、repository identity 与
  authorization kind；
  context 原文、signature、`key_id` 或 trust root 不写进 saved result。

  `runtime_invocation_context_binding_sha256` 只覆盖 **challenge-independent、rotation-stable**
  字段：current invocation id、generation、immutable repository id、canonical repository
  name、issue、route、`auth_mode`、精确 waived gates、runtime-owned `grant_id` 与
  `authorization_grant_sha256`。grant 的 canonical digest 本身也必须含相同 repository identity。
  它显式排除 request id/challenge、
  `issued_at`、`expires_at`、signature、`key_id` 与其它 envelope-only 字段。初次 route 和
  consumer 的每个 fresh response 仍必须分别由 verifier 校验自己的 `key_id` 在该次签发时
  active/non-revoked；两个有效重叠 key 之间的合法 rotation 不改变 stable binding。用完整
  context 或 `key_id` 作跨 challenge equality 会错误拒绝合法 fresh response，因此禁止；
- 对 spec-first route，无论 authorization kind 是 `human_lifecycle` 还是
  `invocation_auto_waiver`，route 都必须
  验证 fresh trusted `ready_to_implement` event。review 路径还验证该 event 严格晚于 accepted
  approval；auto 路径验证它晚于 runtime grant 的 `authorized_at`。auto waiver 不替代 duplicate
  gate、packet validation、freshness 或 saved-result binding。对 sensitive spec-first，
  open exact-head review 只证明 lifecycle/order；生产实现前还必须等待该 exact revision merge
  到 trusted default base，fresh 重采并通过 existing sensitive `approved_spec` 的
  `merged_at`、`merge_commit_sha` 与 ancestry 校验。direct/mixed sensitive 入口同样保留该
  evaluator；无法产生 merged-base evidence 即 `blocked`/`needs_human`，不得因 auto waiver 或
  route kind 放宽；
- route 分别计算两类 artifact snapshot：`spec_snapshot_sha256` 只覆盖 product/tech，专用于
  exact-head approval 比较；`packet_snapshot_sha256` 覆盖实际发现的 product/tech/tasks，专用于
  saved-result 与 artifact drift。二者都按稳定 repository-relative path + 内容 sha256 聚合。
  合法创建 tasks 只改变 packet snapshot，不改变 spec snapshot；
- spec-first route 在计算 snapshot 前调用 staged-aware packet validator，确保 product/tech 内容有效，
  已存在的 tasks 也有效；其 implement 入场允许 tasks 缺失，但 tasks 创建后必须重跑 route。
  `schemas/evaluation_result.schema.json` 收紧 implement result：staged packet 固定输出
  `authorization_scope: "task_planning"`、`allowed_actions: ["plan_tasks"]`，并把 `implement`
  放入 `blocked_actions`；complete packet 只有在全部 gate 通过时才输出
  `authorization_scope: "production_implementation"` 与 `allowed_actions: ["implement"]`。
  通用 `decision` 继续使用闭集 `allowed|warn|needs_human|blocked`，但 `decision: allowed`
  单独不是生产授权。scope、shape 与 allowed/blocked actions 的非法组合必须 schema/gate
  拒绝，不能为了兼容旧 consumer 同时发出两个 capability；
- duplicate evidence schema 将 `collected_at` 收紧为可解析 UTC 时间；`duplicate_work_gate`
  使用与 issue evidence 同样显式、可配置且有安全默认值的最大年龄，重新验证 immutable
  repository id + canonical name、issue、complete open-PR/changed-path query、open PR refs 与
  matching remote branches；只应用上一段 exact `approved_spec_pr_exemption`，并把排除的
  PR/branch identity 记录在 satisfied audit 中。collector 测试固定顺序和 canonical JSON。
  route result 记录包含 `collected_at` 的
  `duplicate_work_evidence_envelope_sha256`，以及只删除 `collected_at` 的
  `duplicate_work_evidence_snapshot_sha256`、采集时间与 decision；前者审计本次输入，后者才
  跨 fresh capture 比较，freshness 独立重验；
- `route_gate --verify-result <saved-route.json> --consume-for
  task_planning|production_implementation --evidence <fresh-issue-evidence.json>
  --duplicate-evidence <fresh-duplicate-evidence.json>` 作为确定性 consumer gate；
  `--verify-result` 缺 `--consume-for` 必须拒绝，且要求 saved `authorization_scope`、
  packet shape 和 allowed/blocked actions 与 requested consumption exact match；特别是
  `--consume-for production_implementation` 对 staged、`task_planning`、缺 scope 或 legacy
  result 一律以 `authorization_scope_mismatch` 拒绝，不得靠 `decision: allowed` 通过。auto 路径
  还必须追加 `--auth-mode auto --auth-evidence <same-invocation-authorization.json>`；consumer
  内部再次通过 provider adapter 发出新的 challenge，禁止调用方重供或复用 signed context。
  consumer
  先对 fresh issue
  evidence 重做 identity/source/trust/freshness 校验，比较 semantic snapshot 而非带新
  `collected_at` 的 envelope hash，再按 saved authorization kind 重验 ordered exact-head
  lifecycle/readiness event；auto 则用 selector 重新查询 runtime-owned grant、发起新 challenge，
  由 runtime-owned verifier 验证**新返回的** response 与其独立 active key，再比较
  rotation-stable binding digest。随后 fresh duplicate evidence 重做 freshness/open PR/branch
  检查并比较 semantic snapshot，重算当前 `spec_snapshot_sha256` 与
  `packet_snapshot_sha256`，最后匹配 saved result 的 issue、route、authorization/context/
  evidence/artifact 摘要、repository identity、authorization scope/capability 与 allowed
  decision。不得把 saved hash 与 saved result 自身比较，也
  不得把 saved context 副本或 caller record 当作 live trust anchor/authorization。新
  invocation/generation/repository/grant、PR/branch、文件、label/lifecycle/readiness ordering、
  consumer purpose 或 semantic
  evidence 变化都使旧结果确定性失效；只有 `collected_at` 或 active signing `key_id` 合法变化
  且各自 fresh/active 校验通过时不得误报 drift。
- 更新四个 shipped issue fixtures，使其结构包含 `repository` 与 `collected_at`；固定时间 fixture
  只作为 schema/陈旧证据样本。需要 allowed 结果的测试必须复制 fixture 后注入测试时钟对应的
  current timestamp，不能扩大 production freshness 窗口掩盖陈旧输入。
- 将 `tests/test_github_issue_evidence.py` 中 route/fixture 集成回归迁移到已有的
  `tests/test_github_issue_route_evidence.py`，并同步 `route_gate_test_support.py` 与 configured-path
  回归；两个修改后的测试文件都必须 `<800`，不得删除覆盖或弱化断言。

#### 3.1 Runtime invocation provider integration contract

`integrations/runtime-invocation-provider.md` 是 host/runtime 与本仓库之间的版本化集成合同：

- **所有权**：runtime owner 独占 provider service、authenticated session/current-generation
  registry、用户授权写入的 grant registry、Ed25519 issuer/private keys、OS/runtime-owned
  public-key trust store、portable verifier、部署/rotation/revocation；agent/caller 对这些状态
  均只读。SpecRail client owner 独占 `checks/runtime_invocation_provider.py` adapter、
  `checks/runtime_invocation_context.py` closed-envelope/binding validator、schema、`route_gate`
  binding、fail-closed 行为与 client tests。runtime server、grant issuance、crypto/JCS verifier
  与 private-key 实现不进入本仓库，但 provider + registry + verifier 部署是宣称 auto available
  的联合前置条件；
- **传输边界**：adapter 只连接 integration contract 固定的 logical local IPC service
  `specrail.runtime.invocation.v1`。service endpoint 由 OS service registry/runtime package
  解析，adapter API 与 route CLI 均不接受 endpoint/provider 参数；environment、repo config、
  caller record 与 saved result 也不能覆盖。连接后双方验证 OS peer credential 与
  固定 runtime service identity，provider 再由 transport-associated session 选择 current
  invocation；request 中的 claimed invocation id/grant id 不参与 endpoint、provider、session
  或 authorization 创建，只用于和 runtime-owned state 做 fail-closed selector matching；
- **challenge request**：adapter 必须用 CSPRNG 为每次 route/`--verify-result` 独立生成
  32-byte challenge（base64url、无 padding）和 16-byte request id，禁止从 CLI/env/record/result
  接收。闭合 request 仅含 `protocol_version: 1`、`request_id`、`challenge`、
  `claimed_invocation_id`、caller record 中的 `grant_id` selector、fresh trusted evidence
  得到的 immutable `repository_id` + canonical `repository`、`issue`、`route` 与
  `auth_mode: "auto"`；request 不携带可由 caller 定义的 grant digest、actor/source 或
  `waived_human_gates`。provider 必须从 runtime registry 读取 grant 后自行决定并返回这些
  authority fields，绝不签任意 caller-supplied waiver；
- **signed response**：provider 在同一次 authenticated session/current-generation 查询中返回
  闭合 payload：request 的全部 binding、`current_invocation_id`、正整数
  `current_generation`、runtime registry 的 `grant_id`、`authorization_grant_sha256`、
  `grant_authorized_at`、精确 `waived_human_gates: ["spec_approval"]`、
  `server_instance_id`、`issued_at`、`expires_at`、`key_id`、
  `signature_algorithm: "Ed25519"`、`canonicalization: "RFC8785-JCS"` 与 `signature`。
  `authorization_grant_sha256` 来自 runtime-owned canonical grant entry，且该 canonical entry
  必须含 response/request 相同的 repository id + name；grant 必须 active、未撤销/未过期，并与
  current invocation/generation/repository/issue/route/auth mode 精确匹配；
  `expires_at - issued_at` 不得超过 60 秒；client 只接受当前时间位于该区间且 challenge/request
  id 精确匹配的单次响应；
- **签名字节**：移除顶层 `signature` 后按 RFC 8785 JSON Canonicalization Scheme 生成 UTF-8
  bytes，签名输入固定为 ASCII domain separator
  `SpecRail-Runtime-Invocation-v1\0` 后直接拼接该 JCS bytes；只允许 Ed25519，不允许 algorithm
  negotiation、非 JCS JSON、字段缺失/额外字段或替代编码；
- **portable verifier boundary**：runtime package 必须保证固定 logical local IPC verifier
  `specrail.runtime.invocation-verifier.v1` 在所有受支持 host 可用。SpecRail adapter 向它提交
  完整 response bytes、domain separator 与本次 expected request binding；verifier 通过
  authenticated peer 自证固定 service identity，并独占 RFC8785 canonicalization、Ed25519
  verification 及 OS/runtime-owned `specrail.runtime.invocation.v1` trust-store 读取。CLI、
  environment、repo、record/selector、response 与 saved result 都不能选择 verifier/backend、
  root/keyset 或宣称 verified。缺 verifier、peer 验证失败或 verifier 返回非闭合 success
  attestation 时 auto fail closed；因此 repo manifest 不需要添加未声明的 Python crypto/JCS
  dependency，也不能用“本机碰巧安装”替代 host prerequisite；
- **trust 与 rotation**：verifier 对每份 fresh response 独立读取/刷新 trust-store keyset；
  每个 public key 记录 `key_id`、`not_before`、`not_after` 与可选 `revoked_at`。unknown、
  尚未生效、过期或已撤销 key 一律拒绝，revocation 立即优先于缓存。rotation 可在有效期内
  重叠，route response 与 consumer response 可以由不同 active key 签名；`key_id` 不进入
  cross-challenge binding digest，但每次都必须独立通过 key activity 与 signature 校验；
- **current/replay**：provider 必须以 authenticated transport session 的 current invocation/
  generation 为权威，并把 fresh challenge、repository id + name、issue、route、runtime grant digest 与精确 waived
  gates 一并签名。client 要求 claimed/current invocation 与 selected/runtime grant 均相等，
  只在本次调用内消费 challenge 一次；route 与 consumer 使用不同 challenge。旧 response
  无法回答新 challenge，旧 selector/旧 saved result 即使 issue/route 相同，也因 current
  invocation/generation/repository 或 runtime grant digest 不匹配而确定性拒绝；
  generation/repository/grant 在 route 与 consumer 之间改变同样拒绝。仅 active signing key
  rotation 不构成 grant/invocation 漂移；
- **可用性**：provider/grant registry/verifier 未部署或不可达、transport peer 不可信、
  trust store 不可读、unknown/revoked/expired key 或 grant、JCS/signature/时间/challenge/
  binding 错误、generation 改变时，auto route 必须以明确 reason fail closed。operator 可以
  显式改走正常 ordered human-lifecycle review route；不得自动改变 auth mode、silent
  downgrade、回退到 caller-supplied context/crypto，或在任一 host prerequisite 未满足时声称
  auto available。

`spec_first` 对应交接顺序为：

1. `ready_to_spec` + allowed write_spec → 写 product/tech → staged validator pass；
2. review/default 路径采集同仓 spec PR immutable exact-head maintainer approval 及有序
   `spec_pr_open → spec_review → spec_approved` lifecycle evidence；明确 auto invocation
   则用 caller selector 查询 runtime-owned active grant，并通过 provider + portable verifier
   的 fresh challenge-response 形成限于 current invocation/repository/issue/route 的
   `spec_approval` waiver；
3. 两条路径都在 authorization 之后取得 event timestamp 严格更晚的 fresh trusted
   `ready_to_implement`，并独立验证该 event actor 的 maintainer permission；review 路径还须
   证明被接受的 exact-head `APPROVED submittedAt < spec_approved event <
   ready_to_implement event`，先打 lifecycle/readiness label、后补 review 一律拒绝；其
   duplicate gate 只排除 exact approved spec-only PR/head branch，再用 fresh issue + fresh
   duplicate evidence 令 implement route 对 staged packet 输出
   `authorization_scope=task_planning`、只允许 `plan_tasks`；freshness 单独校验，跨采集比较排除
   且只排除 `collected_at` 的 semantic snapshot；
4. `specrail-plan-tasks` 创建并验证 tasks，packet 变为 complete；
5. 对 complete snapshot 重跑 implement route，并立即用
   `--verify-result <result> --consume-for production_implementation --evidence <fresh-evidence>
   --duplicate-evidence <fresh-duplicate-evidence>`（auto 重供同一 grant selector，client
   adapter 自动发出新的 provider challenge 并调用 portable verifier）对当前
   `spec_snapshot_sha256`、`packet_snapshot_sha256`、fresh semantic evidence、
   repository identity、approval-or-grant、scope/capability 与 freshness 分别验证；
6. 若为 sensitive，等待该 exact approved revision merge 到 trusted default base，fresh 重采
   existing `approved_spec`，验证 `merged_at`、`merge_commit_sha` 与 ancestry；merge 会改变
   default base 与 open-PR/branch evidence，按 B-014 使第 5 步 merge 前的 route/consumer
   结果失效，因此 ancestry 校验通过后必须以 fresh issue/duplicate evidence 重跑第 5 步的
   implement route 与 production-scoped consumer gate；
7. `specrail-implement-queue` 只有在 `spec_status=complete`、consumer gate（sensitive 时为
   merge 后重跑的那一次）以及适用的 sensitive merged-base gate 都通过时才允许生产代码 lane。

因此 implement route 入场不循环要求它将创建的 tasks，但生产代码也不能从 staged packet
开始。ready_to_implement 后 tasks 被删除或损坏时，queue coverage 重新分类为 `needs_tasks`，
旧 readiness/验证不可继续授权代码。shared runtime ledger 必须把
`RUNTIME_STATE_MAPPING["needs_tasks"]` 精确设为 `("ready_to_implement",)`；回归须同时断言
`spec_approved` 不映射 `needs_tasks`，而 fresh `ready_to_implement` 才能记录 task-planning
checkpoint，避免 runtime ledger 把尚未获实现 readiness 的 packet 推入 tasks lane。
`direct_bug` 与 `mixed_impl` 不执行上述独立 spec-PR staged handoff：前者按 `SPEC.md`
accepted-small-bug direct contract，后者按 standard/fastlane single-PR contract；二者仍须
trusted `ready_to_implement`、各自 duplicate/approval/final-review gates，且 sensitive 时同样
执行第 6 步。route classification 缺失或歧义时不得退回 spec-first 或自动选一条路径。

### 4. GH-180 bootstrap 与在途纠偏

GH-180 修复前的 validator 仍要求三文件，因此本 issue 历史上使用一次性
`auth_mode: auto` old-validator bootstrap exception：

- live `ready_to_spec` label 可观察；coordinator 报告 `write_spec: allowed` 后写
  product/tech，但原 issue-evidence runtime 文件未 tracked，不能称为可独立恢复的证据；
- 主 agent 报告本次使用 invocation-scoped `auth_mode: auto` waiver，maintainer 把 live label
  直接从 `ready_to_spec` 切到 `ready_to_implement`；该 transition 没有经过正常的
  `spec_pr_open → spec_review → spec_approved`，不得描述为 review lifecycle。tracked checkout
  没有 invocation id、route、精确 `waived_human_gates`、exact `implx auto` trigger 或独立
  runtime-owned current-invocation context，因此历史 waiver 的成立状态只能是
  `reported_unproven`，不能断言它已覆盖当次 `spec_approval`；
- coordinator 报告重新采集 issue/duplicate evidence 且 implement gate 为 `allowed` 后写
  GH-180 tasks，使旧 CI 可验证完整 packet；但原 issue-evidence runtime 文件不在 tracked
  checkout，`collected_at`/hash 无法恢复，因此 tracked JSON 将这部分和 normal lifecycle
  明确标成 `unproven`，不得从 duplicate timestamp、label timeline 或文件名推断。

tracked `specs/GH180/bootstrap-evidence.json` 只审计 observed direct transition、reported
decisions/waiver claim 与 unproven 证据缺口；它不得保留 `invocation_scoped: true`、
`spec_approval_waived...: true` 或其它 proven=true 语义，且 `authorization_effect` 为 `none`，
不充当未来 route 授权。这一
spec PR 不包含生产实现。

该文件不是通用 packet artifact。shared classifier 不认识它；仅 GH-180 consumer overlay
在 exact issue/path、`version/issue/authorization_effect/status` 全部满足 B-020，且文件
bytes 与 pinned canonical 全文件 sha256 digest 精确相等时返回
`gh180_bootstrap_audit`，作用只限于本 spec PR 的 changed-path equality。其它 issue 的副本、
改名文件、缺字段、把 `partial_unproven`/`none` 改成更强结论或任何其它字节级漂移都必须
classification invalid。

PR #179 已随 commit `5db6971` 合入 `main`，其原分支再推送也不会改变默认分支，因此提前生成的
`specs/GH165/tasks.md`（在 `main` 上仍然存在）必须改由一个以 `main` 为 base 的独立 follow-up
PR 删除；该 PR 是 B-012 迁移的交付载体，删除后 `specs/GH165` 的 product/tech 以 staged 形态
通过新 validator。本实现 PR 不承担该删除，也不得把它记为已完成。GH-180 bootstrap evidence
不可复制到其它 issue；后续 ready_to_spec packet 一律走 staged 路径。

### 5. 文档、分发与审计一致性

`AGENT_USAGE.md`、`PLAN.md`、`README.md`、两份 PR template、implx、router、两个 focused write skill、
task-planning、direct implement 与 queue skill 使用相同术语：shape 是
`staged|complete|invalid`，queue spec status 是 `needs_tasks|complete|needs_spec`，readiness
来自 fresh trusted GitHub evidence；spec approval 在 review/default 路径来自同仓 spec PR
immutable exact-head maintainer approval 与有序 lifecycle，且满足
`APPROVED submittedAt < spec_approved < ready_to_implement`；readiness actor 必须满足
maintainer policy。该 staged 合同只应用于被 trusted evidence 判为 `spec_first` 的入口；
`PLAN.md` 必须同时保留 `SPEC.md` accepted-small-bug direct route 与 queue standard/fastlane
single-PR `mixed_impl` route，并说明 caller 不能自报 route kind。对 sensitive spec-first，
open same-repository exact-head APPROVED PR 只完成 lifecycle，production 仍须等精确 revision
merge 到 trusted default base 并通过 existing sensitive `approved_spec` ancestry gate；
direct/mixed sensitive 同样不绕过该 evaluator。duplicate exemption 只覆盖
由 repo-owned closed artifact-role allowlist 分类、且与 implementation paths disjoint 的 exact
approved spec-only PR/head；在
明确 auto invocation 中来自 caller selector、runtime-owned grant registry 与 verified live
current-invocation context 的联合验证，且整条链绑定 immutable repository identity。
staged 写作完成后必须等待 review approval，或在 auto 合同下记录 waiver 并真实设置/重采
readiness；staged result 只能 `plan_tasks`，tasks 完成后必须重跑 route，并以
`--consume-for production_implementation` 通过 consumer gate。七个 skill 修改后只更新其
`skills-lock.json` hash；不修改 skill 集合、顺序、路径或其它 hash。

审计由同一当前 packet 上的两份互补证据组成：`check_workflow` 输出 artifact
shape/validation/packet snapshot，`route_gate` 输出 linked issue、trusted state source、
采集时间、完整 evidence envelope audit hash、排除且只排除 `collected_at` 的 semantic
snapshot、`spec_snapshot_sha256`、`packet_snapshot_sha256`、repository identity、
approval-or-grant、`authorization_scope`、allowed/blocked actions、decision 与
missing/reasons。生产消费者必须用
`--verify-result <result> --consume-for production_implementation --evidence <fresh-evidence>
--duplicate-evidence <fresh-duplicate-evidence>`（auto 重供 grant selector，由 client adapter
内部发出新的 provider challenge 并调用 portable verifier）重算语义/文件摘要、分别重验
freshness 与 key activity 并重跑 duplicate gate，不得拼接不同 snapshot 的成功结果或把 saved
hash 自比较后声称 implementation-ready。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-010 | shape helper、staged-aware validator、standalone evaluator、CLI audit | 两个 CLI 对 staged/complete fixtures 分别成功，check_workflow 输出对应 shape 与 `readiness=unproven` |
| B-003 | CLI wording、public docs/templates、七个 skill | 文档一致性断言禁止 shape 被表述为 readiness/approval |
| B-004 | product/tech 现有校验 | 缺失、空、bad issue token、bad manifest fixtures 继续非零 |
| B-005 | present-task validation | 无效 task fixture 输出 `shape=complete` 且非零，绝不输出 staged success |
| B-006 | workflow/router/focused write docs + write_spec regression | write_spec route 只要求 product/tech，focused skills 使用 fresh label evidence |
| B-007 B-013 | route gate、evaluation-result schema、shared runtime mapping/ledger regression、plan-tasks、direct implement、implx 与 queue coverage | staged result 只含 `task_planning`/`plan_tasks` 且阻断 implement；`needs_tasks` 精确映射 `ready_to_implement` 而非 `spec_approved`；production `--consume-for` 确定性拒绝 staged/legacy/missing-scope result；tasks 后以 complete `production_implementation` scope 才能进代码 lane |
| B-008 B-009 | issue/lifecycle/spec-PR evidence collector、closed artifact-role classifier、duplicate collector/gate、runtime provider/grant registry/portable verifier integration、context schema、route gate、PLAN/docs、labels 与 fixtures/tests | review 验证 same-repo exact-head maintainer approval、`APPROVED submittedAt < spec_approved < ready_to_implement`、readiness actor permission，并只排除 deterministic allowlist 中且与 implementation paths disjoint 的 exact spec-only source PR/head；source PR base 必须绑定 fresh trusted default base（`spec_pr_base_untrusted` 负例），lifecycle label events 必须晚于 selected source PR `createdAt`（`lifecycle_event_predates_source_pr` 负例）；PLAN 与正常 lifecycle 一致；auto 只接受 repository-bound runtime registry active grant 和 fixed authenticated provider/verifier IPC |
| B-011 | all existing packets + full suite | `--all-specs` 中既有三文件 packet 全部 `complete`，无需迁移 |
| B-012 | 以 `main` 为 base 的 GH165 follow-up PR fixture/verification | 该 follow-up PR 删除 `specs/GH165/tasks.md` 后新 validator 报 staged 且 CI 绿，issue 仍非 implementation-ready |
| B-014 B-015 | validator/route authorization/runtime challenge-response/evidence/spec+packet snapshots + scoped `--verify-result` | repository id+name 贯穿 selector/grant/request/response/digests/result；fresh envelope 与 semantic snapshot、spec 与 packet snapshot、task-planning 与 production scope 分别校验；合法 key rotation只排除 `key_id` |
| B-016 B-017 | tracked bootstrap evidence | direct transition、reported decisions/waiver claim 与 unproven invocation/route/waived gates/exact trigger/collected_at/hash 分栏；authorization_effect=none |
| B-018 | CLI + route evidence pair | shape 行含 path/shape/readiness/snapshot；route JSON 含 issue/state/auth_mode/authorization kind 与 hash/evidence hashes/decision/reasons |
| B-019 | partial-file fixtures | 半写/空 product 或 tech 失败；中断后只按当前文件重新分类 |
| B-020 | shared classifier + GH180 approval/duplicate consumer overlay | 通用 role 闭集仅有 product/tech/tasks；只有 exact GH180 path 且全文件 bytes 等于 pinned canonical digest 才返回 `gh180_bootstrap_audit`，跨 issue/改名/提权内容与谓词外字段改写均 invalid 且不产生授权 |
| B-021 | route gate、`workflow.yaml` 条件 artifact 规则、runtime checkpoint schema/ledger gate、SPEC/state compatibility、queue route tests/docs | trusted evidence 确定性产出 `spec_first|direct_bug|mixed_impl`；`direct_bug` 在条件 artifact 规则下无 packet 也可入场，mixed planning evidence 必须来自 ledger-gate 校验且带独立 tier 背书的闭合 checkpoint 子对象，self-declared tier `needs_human`；direct bug 与 standard/fastlane mixed PR 正例保留，caller 自报、歧义/冲突证据 fail closed |
| B-022 | existing sensitive evaluator、route integration、PLAN 与 sensitive regressions | open PR 只能完成 spec-first lifecycle；production 正例还须 exact revision merged-base/ancestry evidence，direct/mixed sensitive 也不能绕过 |

## 数据流

trusted transition + packet/PR relation + queue tier → deterministic
`implementation_entry_kind`。对于 `spec_first`：Git tree 中的 packet paths →
`spec_packet_shape` → `validate_spec_packet` 内容错误集合 →
`check_workflow` 稳定 shape/validation/packet snapshot 输出。live GitHub issue evidence、同仓
spec PR exact-head review lifecycle/readiness actor authority 或 repository-bound runtime-owned
grant + verified current-invocation anchor、
duplicate-work evidence → route gate 分别校验 freshness、semantic snapshot、readiness event
ordering、authorization kind、exact spec-source duplicate exemption、open PR/branch、spec
snapshot 和 packet snapshot → 带 repository/grant/runtime-context/evidence
envelope+semantic/artifact 摘要及 authorization scope 的 decision JSON。
对 sensitive，open exact-head lifecycle 后还需 merged-base `approved_spec`/ancestry evidence。
`direct_bug` 与 `mixed_impl` 跳过 spec-first packet lifecycle，但继续执行各自既有 route/queue
gates，sensitive 时仍执行同一 merged-base evaluator。queue 在 task planning 前校验 staged snapshot，tasks 写入后再用 validator、route gate 和 spec
coverage 重跑，再用 production-scoped `--verify-result` 与 fresh issue/duplicate evidence 同时匹配 complete
snapshot；生产实现只消费 fresh 且全部摘要、human gates 和 duplicate gate 均匹配的结果。

## 备选方案

- 继续要求所有 spec PR 提前写 tasks：拒绝；它越过 workflow 的 route/readiness 所有权。
- 让 implement route 入场前要求 tasks：拒绝；会形成“进入 route 前先有该 route 产物”的循环。
- 从 workflow 把 task_plan 移到 write_spec：拒绝；会把任务规划提前到未批准设计，扩大 issue 范围。
- 对所有 implement 强制独立 spec-only PR：拒绝；会破坏 `SPEC.md` 的 accepted-small-bug
  direct route 与 standard/fastlane 的 single-PR `mixed_impl` route。
- 让 sensitive open PR approval 取代 merged-base evidence：拒绝；会削弱现有 ancestry enforcement。
- 用 issue label 传给 `check_workflow --all-specs`：拒绝；CI 的离线结构校验不应依赖网络或可变状态。
- 删除 task 内容校验：拒绝；只允许文件缺失代表 staged，存在但无效必须 fail closed。

## 风险

- Security: shape、route kind 与 readiness label 都不得被 caller 当作 spec approval；spec-first review 验证同仓
  spec PR immutable exact-head maintainer approval、readiness actor authority 与 exact-source
  duplicate exemption，auto implement 只接受 repository-bound runtime-owned active grant +
  authenticated challenge-response；runtime grant registry、
  private key/issuer/verifier 由 host owner 管理，不进入 repo，client 不允许 endpoint/verifier/
  root 注入；两者都验证可信 readiness、duplicate、spec/packet snapshot 与 consumer evidence。
  sensitive production 另需现有 merged-base/ancestry evidence；GH180 overlay 永不授权。
- Compatibility: CLI 新增确定性 shape/scope 行但保留既有最终消息与 exit code；旧 saved result
  缺 scope 时 fail closed，必须重跑，不能兼容成 production authorization；旧完整 packet 无需改写。
- Availability: host provider + grant registry + portable verifier 是 auto 的显式前置条件；任一
  未部署或不可达时 auto reason 为 blocked，正常 review route 不受影响，且绝不自动从 auto
  改成 review。
- Race: route JSON 显式绑定 repository、auth mode、approval-or-grant、runtime generation、issue/duplicate
  semantic snapshot、spec 与 packet snapshot；生产操作前必须查询 live runtime、重采 evidence、
  单独验 freshness/key activity并重算匹配。`collected_at` 与 active `key_id` 的预期变化不误判
  drift，其它语义、repository、grant、spec-source head/path、readiness ordering、consumer
  purpose 或 artifact 变化均拒绝。freshness 是 bounded
  staleness，不宣称消除 GitHub 查询后的瞬时竞态。
- Maintenance: `validate_spec_packet` 保持 list 返回值，新增 helper 避免大规模 API 迁移；修改后
  `checks/check_workflow.py` 与所有 touched files 仍须 `<800` 行。

## 测试计划

- [ ] Unit: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py`，
  覆盖 standalone evaluator 与 workflow validator 的 staged/complete/invalid、present-invalid
  tasks、symlink/identity 与 partial files。
- [ ] CLI: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py`，覆盖显式与 all-specs 的
  稳定 shape 行、配置 root、成功/失败 exit code和 readiness=unproven。
- [ ] Workflow/skill regression: README、双语 PR template、implx、focused write/plan/direct
  implement/queue 入口与 PLAN 均不再自报 route/readiness，且同时保留 direct-bug、
  standard/fastlane mixed route 和 sensitive merged-base gate；skill lock 只更新七个目标 hash。
- [ ] Evidence/route: `/usr/bin/python3 -m pytest -q tests/test_issue_evidence_freshness.py
  tests/test_route_gate.py tests/test_runtime_invocation_context.py
  tests/test_runtime_invocation_provider.py tests/test_duplicate_work_gate.py
  tests/test_github_duplicate_evidence.py tests/test_specrail_schema.py`，覆盖 review same-repo
  exact-head approval、`APPROVED submittedAt < spec_approved < ready_to_implement`、label
  早于 review 的拒绝、repo-owned closed artifact-role allowlist、manifest `spec_refs` 与
  implementation `paths` disjoint、实现文件伪装 spec ref 的拒绝、只排除 exact spec-only
  PR/head branch、其它 PR/branch 与 source
  identity/head/path/query 漂移阻断、完整 lifecycle、readiness actor permission fail-closed 与
  `spec_approved < ready_to_implement`；覆盖 staged/production scope/action 闭合组合和 production
  verify-result 拒绝 staged/legacy result；auto grant-selector + runtime-owned registry/provider/
  verifier 正负例、固定 endpoint/peer identity、Ed25519/JCS signing bytes、active/rotated/revoked
  keyset 及跨 challenge 合法 key rotation、
  CLI state/readiness label self-report、缺失/未来/超窗 issue/duplicate evidence、错误 issue、
  新 PR/branch、provider unavailable、endpoint/root 注入尝试、challenge/response replay、
  缺/伪造/过期/旧 generation context、caller 自造/旧/revoked grant、旧 selector 与 saved result
  跨 repository/invocation 重放、缺失/错误/rename-drift repository id/name、只变化
  `collected_at` 的 fresh recapture、semantic evidence 漂移、
  spec/packet snapshot 分离与 artifact 漂移；source PR base 非 trusted default base 的
  `spec_pr_base_untrusted` 负例、lifecycle event 早于 source PR `createdAt` 的
  `lifecycle_event_predates_source_pr` 负例；通用 classifier 拒绝 bootstrap role，
  GH180-only overlay 的 exact-path/全文件 digest 正例及跨 issue/改名/提权/谓词外字段改写
  负例，route kind 的 spec-first/direct-bug/mixed-impl 正负例（含 `direct_bug` 条件
  artifact 规则正例、mixed self-declared tier / 缺独立背书的 `needs_human` 负例）。
- [ ] Runtime ledger: `/usr/bin/python3 -m pytest -q tests/test_runtime_ledger_gate.py`，精确断言
  `RUNTIME_STATE_MAPPING["needs_tasks"] == ("ready_to_implement",)`，覆盖 planning-evidence
  子对象闭合 shape 的 schema/gate 正负例，并覆盖
  `spec_approved` 不能产生 task-planning checkpoint、`ready_to_implement` 可以产生该 checkpoint。
- [ ] Regression migration: `/usr/bin/python3 -m pytest -q tests/test_github_issue_evidence.py tests/test_github_issue_route_evidence.py tests/test_configured_spec_path_review_regressions.py tests/test_route_gate_sensitive.py`，覆盖拆分后的原有断言、shipped fixtures、configured paths、direct/mixed compatibility 与 sensitive open-PR negative + merged-base positive/ancestry-drift negative；所有修改文件 `<800`。
- [ ] Submission: `/usr/bin/python3 -m pytest -q`、
  `/usr/bin/python3 checks/check_workflow.py --repo . --all-specs`、
  `/usr/bin/python3 tools/spec_depth_audit.py --spec-dir specs/GH180 --gate`、`git diff --check`、
  touched-file `<800`；修改前已为 799 行的 queue skill 必须通过删减重复文字保持在上限内。

## 回滚方案

回滚 `spec_packet_shape`、optional-tasks validator 分支、CLI shape 行、对应测试/文档/skill hash，
即可恢复旧的三文件强制合同；无数据迁移。回滚后 product/tech-only spec PR 会重新 CI 失败，
必须同时重新开放 GH-180，而不能以提前写 tasks 或跳过 CI 作为替代。
