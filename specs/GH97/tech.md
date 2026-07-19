# Tech Spec

## Linked Issue

GH-97

## Product Spec

Product: `product.md`

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":97,"complete":true,"paths":[".github/workflows/workflow-check.yml","PLAN.md","README.md","checks/check_workflow.py","checks/closure_audit.py","checks/github_approved_spec_evidence.py","checks/github_evidence_common.py","checks/github_issue_evidence.py","checks/github_pr_evidence.py","checks/github_pr_snapshot.py","checks/github_review_evidence.py","checks/pack_asset_validation.py","checks/pr_gate.py","checks/pr_review_contract.py","checks/review_json_gate.py","checks/review_result_semantics.py","checks/route_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/schema_validation.py","checks/sensitive_enforcement.py","checks/specrail_lib.py","examples/fixtures/pr-clean-authorized.json","examples/fixtures/pr-gate-head-mismatch.json","examples/fixtures/pr-implementer-resolved-thread.json","examples/fixtures/pr-merge-api-fallback-confirmed.json","examples/fixtures/pr-merge-confirmed.json","examples/fixtures/pr-merge-missing-path.json","examples/fixtures/pr-merge-unconfirmed-local-failure.json","examples/fixtures/pr-missing-human-auth.json","examples/fixtures/pr-missing-thread-resolver.json","examples/fixtures/pr-outdated-unresolved-thread.json","examples/fixtures/pr-pending-ci.json","examples/fixtures/pr-query-after-merge.json","examples/fixtures/pr-self-review-source.json","examples/fixtures/pr-self-review-unauthorized.json","examples/fixtures/pr-unresolved-thread.json","examples/fixtures/review-clean-pr10.json","examples/fixtures/review-clean-pr718-self.json","examples/fixtures/review-clean-pr718.json","examples/fixtures/review-invalid-body.json","examples/fixtures/review-invalid-empty-suggestion.json","examples/fixtures/review-invalid-line.json","examples/fixtures/review-invalid-range.json","examples/fixtures/review-invalid-severity.json","examples/fixtures/review-invalid-suggestion-side.json","examples/fixtures/review-manifest-pr10.json","examples/fixtures/review-manifest-pr718-self.json","examples/fixtures/review-manifest-pr718.json","examples/fixtures/review-resumed-no-checklist.json","examples/fixtures/review-round2-full.json","examples/fixtures/review-round3-diff-only-checklist.json","examples/fixtures/review-round3-full-no-request.json","examples/fixtures/review-round3-full-with-request.json","examples/fixtures/review-spec-drift.json","examples/fixtures/review-valid.json","examples/fixtures/runtime-self-review-merged-unauthorized.json","schemas/closure_audit_result.schema.json","schemas/issue_evidence.schema.json","schemas/pr_review_gate.schema.json","schemas/review_result.schema.json","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/specrail-write-tech-spec/SKILL.md","templates/tech_spec.md","templates/zh-CN/tech_spec.md","tests/runtime_ledger_test_support.py","tests/test_check_workflow.py","tests/test_closure_audit.py","tests/test_github_issue_evidence.py","tests/test_github_issue_route_evidence.py","tests/test_github_pr_evidence.py","tests/test_pr_gate.py","tests/test_review_json_gate.py","tests/test_route_gate.py","tests/test_runtime_ledger_gate.py","tests/test_runtime_ledger_review.py","tests/test_specrail_schema.py","workflow.yaml"],"spec_refs":["specs/GH97/product.md","specs/GH97/tech.md"]}
-->

## Codebase Context

| Area | Files | Current behavior (anchors refreshed against the landed implementation) | Why relevant |
| --- | --- | --- | --- |
| Review artifact | `schemas/review_result.schema.json:6-22`, `checks/review_result_semantics.py:15-21`, `checks/review_result_semantics.py:108` | schema 强制 `reviewer_lane`、`head_sha`、`human_final_review_required` 等 required 字段；semantic 模块定义封闭 status 集（`completed|pending|failed|cancelled|superseded`）、verdict 集（merge-ready 仅 `clean|non_blocking`）与 `validate_review_artifact` 共享验证入口。 | 可验证的 terminal exact-head artifact 契约（B-001、B-002）。 |
| PR evidence | `checks/github_pr_evidence.py:583`, `checks/github_pr_evidence.py:537`, `checks/github_pr_evidence.py:406` | merge-ready 路径要求 `--review-manifest`；`--review-source` 单独出现被明确拒绝（"cannot prove terminal review"）；`review_completed_at` 从 trusted review evidence 导出。 | manifest 驱动的候选发现，不接受 source-only 证明（B-001、B-004）。 |
| Terminal review / resolver / 时序契约 | `checks/pr_review_contract.py:21`, `checks/pr_review_contract.py:61-157`, `checks/pr_review_contract.py:348-364` | `BLOCKED_RESOLVER_ROLES = {implementer, orchestrator, coordinator, unknown}`；original/successor reviewer 与 maintainer 授权验证；`review_completed_at <= gate_started_at <= gate_query_completed_at` 时间链验证。 | resolver 身份与 review→gate 顺序（B-005、B-008）。 |
| Sensitive classification | `checks/sensitive_enforcement.py:46`, `checks/sensitive_enforcement.py:126-149`, `checks/route_gate.py:40-45`, `checks/pr_gate.py:317-328` | `sensitive_registry` 解析 workflow.yaml registry；`classify_sensitive_changes` 用 fnmatch 对 normalized changed paths 自行计算 `matched_paths`；route gate 与 PR gate 都消费该分类。 | registry 命中不信任 caller boolean（B-006、B-007）。 |
| Runtime evidence | `schemas/runtime_checkpoint.schema.json:1`, `checks/runtime_gate_rules.py:183-200` | runtime ledger 记录 reviewer lane、lane failures；auto 模式 self-review 要求两条独立失败 lane。 | 复用语义，避免两个 gate 对同一字段定义冲突（B-011）。 |
| Closure audit | `checks/closure_audit.py:135-150`, `checks/closure_audit.py:159`, `schemas/closure_audit_result.schema.json:6-17` | `_required_follow_up` 生成含 `idempotency_key`（`specrail-closure-v1:<digest>`）的稳定 payload；`audit_closure` 验证 `gate_query_completed_at < merge_dispatched_at <= merged_at`；schema 强制 `required_follow_up` 字段。 | 独立 post-dispatch audit 与 payload contract（B-009、B-010）。 |

## 设计方案

### 1. Review artifact v2 semantic contract

- 扩展 `review_result.schema.json`：要求 `reviewer_lane`、`head_sha`、
  `review_started_at`、`review_completed_at`、`status`、`verdict`、`findings` 和 `comments`。
- `status` 使用封闭值 `completed|pending|failed|cancelled|superseded`；merge-ready 仅接受
  `completed`。`verdict` 使用 `clean|non_blocking|changes_requested|blocking`；仅前两者可继续。
- finding 包含稳定 `id`、`severity`、`actionable`、`summary`；current-head 任一
  `critical|important` 或 `actionable=true` finding 阻止。
- prior finding 包含 `id`、`source_head_sha`、`status` 和关闭证据；gate 比较 previous artifact
  时要求集合完整、ID 唯一，且 resolved/obsolete 有证据。
- 把纯 semantic validation 提取为可被 `review_json_gate` 与 GitHub evidence adapter 复用的
  模块或函数，避免 schema/gate 漂移；不引入网络调用。

### 2. Evidence adapter 与 thread resolver

- `github_pr_evidence.py` 新增 required `--review-manifest`（merge-ready 路径）。manifest 由
  validated runtime checkpoint/native lane roster 导出，列出全部 lane、head、artifact path、
  lifecycle 和 producer identity；adapter 必须按 manifest 读取全部候选，不接受调用方任选单个
  `--review-artifact`。每个 lane/head 最多一个有效 terminal artifact，整个 current head 若出现
  多个 terminal、重复 terminal，或 clean 与 blocking 并存均 fail closed。stale/superseded
  artifact 只作为 carry-forward 来源，不能覆盖 current-head truth。
- GraphQL thread 采集保留 `resolvedBy`；resolver role map 增加 original reviewer 与 successor
  re-review evidence 的结构化输入。resolved actionable thread 只有 allowlisted resolver
  contract 通过才清除。
- 保留 self-review CLI 仅作为显式恢复路径，并要求 lane failure + same PR/head scoped human
  authorization + `human_final_review_required=true`。

### 3. Sensitive classification

- 在 `workflow.yaml` 定义通用 consumer registry contract；SpecRail 不写死 remem 路径。
  `route_gate.py` 从受信任 plan/diff evidence、`github_pr_evidence.py` 从 GitHub current-head
  changed-file snapshot 取得路径，复用现有 configured-path normalization、symlink/traversal
  防护后自行计算 `matched_paths`/`matched_specs`，不能把 caller boolean 当作 registry truth。
- approved-spec adapter 从 maintainer-controlled GitHub label/state 与已合并 base tree 生成
  evidence：repository、issue、normalized spec paths、content hashes、base head、approved_at、
  maintainer actor、`state_source=label`、`state_trusted=true`。gate 用 repo-safe path resolver
  重算本地/base 内容 hash 并验证 approval head；body hint、caller boolean、unmerged head、
  changed-after-approval 或 hash mismatch 一律不可信。
- evidence object 记录计算得到的 registry matches、声明的 `enforcement_sensitive` 和上述
  approved-spec evidence。`route_gate.py` 的 implement 路径验证一致性；`pr_gate.py` 对
  current-head merge-ready evidence 重复验证，防止 route 后 diff 改变。
- 缺 registry 时不猜测普通 PR；但显式 `enforcement_sensitive=true` 仍必须有 approved spec。

### 4. Pre-merge gate 时间链

- PR evidence 记录 `review_completed_at`、`gate_started_at`、`gate_query_completed_at` 和各自
  head SHA；`pr_gate.py` 使用 timezone-aware ISO-8601 解析并验证顺序与 exact head。
- `gate_query_completed_at` 是 pre/post-merge 共用的 canonical completion key；不得新增或接受
  `gate_completed_at` alias。下游 GH813 文本中的 gate completion 概念在同步实现时映射到该
  canonical key。
- pre-merge evaluator 不读取或要求 future dispatch；若 evidence 包含 dispatch，仍验证其不
  早于 gate completion，但 post-dispatch 合规由 closure audit 负责。

### 5. Closure audit

- 新增 `schemas/closure_audit_result.schema.json` 和 `checks/closure_audit.py`。输入是已完成 PR 的
  final head、merge timestamps、最后一次 allowed gate result/evidence 与 repository identity。
- 合规链以 `gate_query_completed_at < merge_dispatched_at <= merged_at` 返回 `compliant`。
  缺失或顺序错误返回 `violation`，并生成稳定
  `required_follow_up`：`violation_code`、`repository`、`pr_number`、`final_head_sha`、
  `idempotency_key`、`summary`。
- `idempotency_key` 由上述稳定字段规范化连接/哈希得到；不调用 GitHub Issues API。

### 6. Compatibility

- CLI 对 legacy review artifact 给出明确 blocked/error；不静默映射 `APPROVE` 为 clean。
- schema/check fixtures 全部升级到 v2；历史 fixtures 只在显式 legacy-rejection 测试中保留。
- workflow 的 dry-run/advisory 默认及 human gates 不变。
- 新 check/schema 必须注册进 `checks/check_workflow.py` 与
  `checks/pack_asset_validation.py`；若修改 repo-distributed skill，必须同步 `skills-lock.json`。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| `B-001`,`B-002` | review schema/semantic gate/evidence/pr gate | terminal/empty/verdict/finding table tests |
| `B-003`,`B-004` | semantic validator + trusted manifest/roster | prior completeness、concurrent clean+blocking、duplicate terminal、stale/superseded tests |
| `B-005` | GraphQL normalization、resolver evidence、PR gate | original/successor/human positives; forbidden roles negatives |
| `B-006`,`B-007` | workflow registry、path normalization、approved-spec adapter、route/pr gate | forged approval、body hint、changed hash/head、path-traversal negatives |
| `B-008` | PR evidence/pr gate timestamp parser | canonical-key/no-dispatch positive; alias/review-after-gate/head mismatch negatives |
| `B-009`,`B-010` | closure schema/audit | compliant chain、dispatch-before-gate、external merge missing-chain fixtures |
| `B-011` | PR gate/runtime-aligned recovery | same-head lane failure/auth/human final review matrix |
| `B-012` | every file loader/CLI | missing/unreadable/invalid JSON/schema failures are explicit |

## 数据流

```text
reviewer lane -> review artifact v2 -> semantic gate -> exact-head PR evidence
consumer registry + approved spec -> sensitive classification check
PR head + CI + threads + resolver evidence + review completion
  -> pre-merge PR gate (review <= gate_query_completed_at, no future dispatch required)
  -> authorized merge dispatch
  -> closure audit (gate < dispatch <= merged, same head)
  -> compliant OR violation + required_follow_up payload
```

## 备选方案

- 继续信任 `--review-source`：拒绝；调用方字符串不能证明 lane、head、终态或 findings。
- 只看 GitHub review/thread：拒绝；artifact-only actionable finding 会丢失，且不覆盖 lane failure。
- 在 pre-merge gate 要求 dispatch：拒绝；形成不可能的未来证据依赖。
- closure audit 直接创建 issue：拒绝；SpecRail 只定义可复用 payload，consumer 拥有持久化。

## 风险

- Security：路径输入与 artifact 文件必须按 repo/path trust 规则解析，禁止 `..` 越界。
- Compatibility：旧 artifact 被阻止会中断现有调用方；错误需明确，consumer 同步须原子化。
- Performance：只读取小型 JSON；GitHub API 调用次数保持 bounded，不能新增无界分页。
- Maintenance：schema、semantic gate、adapter、PR gate 容易漂移；共享验证函数与 table fixtures
  是必需的。

## 测试计划

- [ ] `python3 -m pytest tests/test_review_json_gate.py tests/test_github_pr_evidence.py tests/test_pr_gate.py tests/test_route_gate.py tests/test_runtime_ledger_gate.py tests/test_closure_audit.py`
- [ ] `python3 checks/check_workflow.py --repo . --spec-dir specs/GH97`
- [ ] `python3 checks/check_workflow.py --repo .`
- [ ] `python3 -m pytest`
- [ ] CLI smoke：invalid/unreadable artifact、clean current-head artifact、external merge violation。

## 回滚方案

在 consumer 尚未同步时可整体回滚 GH97 commit。consumer 已同步后，回滚必须同时恢复 lock
和调用方格式；不得临时接受裸 `review_source` 或把无证据状态降级为 advisory success。
