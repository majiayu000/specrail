# Tech Spec

## Linked Issue

GH-168

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":168,"complete":true,"paths":["checks/spec_revision_evidence.py","checks/sensitive_enforcement.py","checks/pr_gate.py","checks/github_pr_evidence.py","checks/github_approved_spec_evidence.py","checks/runtime_sensitive_routes.py","checks/runtime_ledger_gate.py","schemas/pr_review_gate.schema.json","schemas/runtime_checkpoint.schema.json","tests/test_sensitive_enforcement.py","tests/test_pr_gate.py","tests/test_github_pr_evidence.py","tests/test_github_pr_evidence_approval.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py","skills/specrail-pr-gate/SKILL.md"],"spec_refs":["specs/GH168/product.md","specs/GH168/tech.md","specs/GH168/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| approved_spec 死锁点 | `checks/sensitive_enforcement.py:411-429` | 要求 default-base 与 gated-head spec digest 相等 | spec revision 按定义无法满足 |
| 可信 file snapshot | `checks/sensitive_enforcement.py:519-573` | 重算 `changed_paths`/matched sets 并校验 count/hash | route 资格的唯一输入 |
| live evidence adapter | `checks/github_pr_evidence.py:474-561`、`checks/github_approved_spec_evidence.py:95-222` | 只构造 approved_spec；没有 exact-head spec approval | 手写 evidence 与线上采集会漂移 |
| PR evidence schema | `schemas/pr_review_gate.schema.json` | `additionalProperties:false`，敏感证据要求 approved_spec | 新 route 在进入 gate 前会被拒绝 |
| runtime ledger | `checks/runtime_ledger_gate.py:474-480`、`schemas/runtime_checkpoint.schema.json` | enforcement-sensitive item 固定要求 approved_spec evidence | 新 route 即使 PR gate 通过也会在 checkpoint 误拒绝 |
| lifecycle | `states.yaml:36-51` | `spec_review` 在 `spec_approved` 之前 | review 状态不能当批准终态 |

## Proposed Design

### 1. Route eligibility

新增 `checks/spec_revision_evidence.py`，避免继续扩张当前约 681 行的 `sensitive_enforcement.py`。入口为：

```text
spec_revision_route_eligible(config, issue, classification) -> RouteEligibility
```

- `issue` 必须是已验证的 linked issue，不能从 path 猜测或由调用方另行自报。
- 使用既有 `spec_packet_artifact_paths(config, issue)` 生成允许集；可信 `changed_paths` 必须非空且为该集合的子集，所有 path 命中 registry specs，`matched_paths=[]`，`matched_specs` 与实际 changed spec paths 一致。
- GH168 链接下只改 `specs/GH169/product.md` 必须失败；任何 code/test/schema/其它 markdown 混入也失败并回落 approved_spec。

### 2. Exact-head human approval collection

扩展 `checks/github_approved_spec_evidence.py` 的可信 timeline/reviewer helpers，并由 `checks/github_pr_evidence.py` 调用。collector 在同一次稳定 snapshot 内获取：

- linked issue 的最新可信 lifecycle label 必须是 `spec_approved`；`spec_review` 明确拒绝；
- maintainer 的非 dismissed GitHub PR review，`state=APPROVED`，其 `commit_oid` 精确等于 gate 的 `head_sha`；
- `maintainer_actor`、timezone-aware `approved_at`、review URL/source；
- 对 route eligibility 返回的规范化 artifact paths 排序后，按 `path + NUL + sha256(content-at-head)` 计算 `spec_artifacts_sha256`。

collector 在采集前后复核 PR head、issue relation、file snapshot 与 review/timeline cursor；任一漂移终止并要求重采。label 只证明 lifecycle terminal，不替代 APPROVED review。

### 3. Evidence validation and route split

`validate_spec_revision_evidence(evidence, *, repository, issue, gated_head_sha, classification)` 复用第 1 节资格结果并要求：

```json
{
  "sensitive_route": "spec_revision",
  "spec_approval": {
    "lifecycle_state": "spec_approved",
    "state_source": "label",
    "state_trusted": true,
    "maintainer_actor": "...",
    "approved_at": "timezone-aware timestamp",
    "approval_source": "github_pr_review",
    "approval_url": "https://...",
    "commit_oid": "40-char gated head",
    "artifact_paths": ["specs/GH168/..."],
    "spec_artifacts_sha256": "64-char digest"
  }
}
```

validator 重算 artifact path set 与 digest，并要求 `commit_oid == gated_head_sha`。`approved_spec` 与 `spec_approval` 混用、`spec_review`、head/digest mismatch、非 maintainer approval 或 partial object 均抛 `SpecRailError`。`evaluate_sensitive_evidence` 只在 eligibility 成立时走此 validator，否则保持现有 approved_spec 调用逐字节不变。

### 4. Schema and audit output

`schemas/pr_review_gate.schema.json` 增加 `sensitive_route` 与 closed `spec_approval` shape；条件约束要求：

- `sensitive_route=approved_spec`：要求 `approved_spec`，禁止 `spec_approval`；
- `sensitive_route=spec_revision`：要求 `spec_approval`，禁止 `approved_spec`；
- enforcement-sensitive 且缺 route/对应 evidence、两者并存或未知字段：拒绝。

`pr_gate` 结果输出从已验证对象派生的 route audit：linked issue、artifact paths、actor/time/source/URL、commit、digest。不得从 PR body 或未校验字段复制。

### 5. Runtime ledger compatibility

新增 `checks/runtime_sensitive_routes.py` 保存 route-aware checkpoint validation，防止约 751 行的 `runtime_ledger_gate.py` 越过 U-16 800 行上限。`runtime_ledger_gate` 委托该 helper：

- approved_spec item 继续要求现有 `approved_spec_evidence`；
- spec_revision item 要求本地 machine-readable `spec_approval_evidence`，并以 item `issue`/`head_sha`/可信 paths 复用相同 validator；
- route 缺失、两类 evidence 混用、head/digest drift 全部 blocked。

`runtime_checkpoint.schema.json` 只加入紧凑 optional route/evidence shape 与 conditional，修改后自身仍必须 `wc -l <= 800`；若无法满足，先收敛现有格式，不引入 validator 不支持的 `$ref`。

## Product-to-Test Mapping

| Invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-004 B-006 | route helper with linked issue | own/foreign packet、mixed path、snapshot mismatch tests |
| B-002 B-005 | lifecycle + GitHub review collector | `spec_review` rejection、maintainer exact-head APPROVED review tests |
| B-007 | commit/digest binding | old-head review、post-approval push、content mismatch tests |
| B-008 | live collector | `github_pr_evidence` end-to-end output test, not handwritten fixture only |
| B-009 | PR evidence schema | route one-of、mixed/partial/unknown field rejection tests |
| B-010 | runtime helper/ledger/schema | spec_revision passes without approved_spec; route/head/digest negative tests |
| B-003 B-011 | route split and unchanged gates | approved_spec regression + CI/review/thread/merge/auth removals |
| B-012 | pr_gate audit | exact derived audit object; omission/mismatch blocked |

## Data Flow

Stable GitHub snapshot（head + file set + linked issue labels + exact-head maintainer review）→ collector 构造 `sensitive_route=spec_revision`/`spec_approval` → closed schema → route eligibility（config + linked issue + trusted classification）→ exact-head/digest validator → `pr_gate` audit result → 同一 machine-readable evidence 写入 runtime checkpoint 并由 route-aware helper 重验。任何层缺失都 fail closed。

## Alternatives Considered

- 接受 `spec_review` label：拒绝；它只是进入审查，不能证明批准。
- 只增加 `approved_head_sha` 自报字段：拒绝；必须来自 GitHub APPROVED review 的 commit binding，并重算 artifact digest。
- 只改 gate、让调用方手写 `spec_approval`：拒绝；live collector、schema 与 runtime 会继续漂移。
- 用 route label 或 PR body 选路：拒绝；资格必须由 linked issue + trusted file snapshot 机械推导。
- 把实现继续塞进超大 `sensitive_enforcement.py`/`runtime_ledger_gate.py`：拒绝；新增 helper 保持两者 ≤800 行。

## Risks

- Security：新 route 跳过 default-base equality，因此 exact-head maintainer review + digest 是不可缺的替代约束；任一证据弱化都视为 blocking。
- Race：批准后 push、label/review timeline 分页漂移、file snapshot 漂移必须触发重采。
- Compatibility：只有显式、可信判定的 spec_revision 走新分支；approved_spec 与非敏感输入回归必须逐字节稳定。
- File size：`sensitive_enforcement.py`、`runtime_ledger_gate.py`、`runtime_checkpoint.schema.json` 修改后均必须 ≤800 行；helper/紧凑 schema 是实现约束，不是可选优化。

## Test Plan

- Focused: route helper、collector、schema、runtime helper/ledger 的所有正负例。
- End-to-end: mock live GitHub snapshot 产生 spec_approval，经过 schema、PR gate、runtime checkpoint 均通过；改变 review commit、artifact bytes、linked issue 或 lifecycle 任一字段后逐层 blocked。
- Regression: 现有 approved_spec、PR gate、runtime ledger、schema 全套测试不改断言全绿。
- Submission: `/usr/bin/python3 -m pytest -q`、`python3 checks/check_workflow.py --repo . --all-specs`、GH168 depth gate、`wc -l` 三个受限文件。

## Rollback Plan

删除 spec_revision collector/validator/runtime helper 分支与两个 schema route 条件即可恢复旧 approved_spec 行为；无持久化迁移。回滚后 bootstrap 死锁重新出现，属于已知结果。
