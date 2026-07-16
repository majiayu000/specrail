# Tech Spec

## Linked Issue

GH-97

## Product Spec

Product: `product.md`

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":97,"complete":true,"paths":[".github/workflows/workflow-check.yml","README.md","PLAN.md","workflow.yaml","checks/check_workflow.py","checks/github_approved_spec_evidence.py","checks/github_evidence_common.py","checks/github_issue_evidence.py","checks/github_pr_evidence.py","checks/github_pr_snapshot.py","checks/pack_asset_validation.py","checks/pr_gate.py","checks/route_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/schema_validation.py","checks/sensitive_enforcement.py","checks/specrail_lib.py","checks/review_json_gate.py","checks/review_result_semantics.py","checks/closure_audit.py","schemas/issue_evidence.schema.json","schemas/pr_review_gate.schema.json","schemas/runtime_checkpoint.schema.json","schemas/review_result.schema.json","schemas/closure_audit_result.schema.json","skills-lock.json","skills/specrail-write-tech-spec/SKILL.md","templates/tech_spec.md","templates/zh-CN/tech_spec.md","tests/test_check_workflow.py","tests/test_github_issue_evidence.py","tests/test_github_issue_route_evidence.py","tests/test_github_pr_evidence.py","tests/test_pr_gate.py","tests/test_route_gate.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py","tests/test_review_json_gate.py","tests/test_closure_audit.py"],"spec_refs":["specs/GH97/product.md","specs/GH97/tech.md"]}
-->

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Review artifact | `schemas/review_result.schema.json`, `checks/review_json_gate.py` | 支持 basic verdict、comments、review round 和简单 prior finding status；不要求 lane lifecycle、时间、finding ID/source head/关闭证据。 | 必须建立可验证的 terminal exact-head artifact。 |
| PR evidence | `schemas/pr_review_gate.schema.json`, `checks/github_pr_evidence.py` | 采集 current head、CI、review 和 thread；`review_source` 由调用方提供。 | 必须从 artifact 导出 review completion，不接受 source-only 证明。 |
| PR gate | `checks/pr_gate.py` | 检查 CI、thread、merge state、authorization；已有部分 resolver role/self-review gate。 | 需要加入 artifact、sensitive classification 和 review→gate 时序。 |
| Route gate | `checks/route_gate.py` | 验证 state/artifact/duplicate evidence；不知道 sensitive registry。 | implement route 必须验证 sensitive 声明与 approved spec。 |
| Runtime evidence | `schemas/runtime_checkpoint.schema.json`, `checks/runtime_ledger_gate.py` | 已记录 reviewer lane、lane failures、自审授权。 | 复用语义，避免两个 gate 对同一字段定义冲突。 |
| Closure | 无 executable check/schema | 只有 PR evidence 内可选 merge dispatch 字段。 | 需要独立 post-dispatch audit 和 payload contract。 |

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
