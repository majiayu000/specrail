# Tech Spec

## Linked Issue

GH-208

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":208,"complete":true,"paths":["AGENTS.md","AGENT_USAGE.md","CHANGELOG.md","PLAN.md","README.md","SPEC.md","checks","examples/fixtures","integrations/threads.md","labels.yaml","review/agent_first_review.md","schemas","skills","skills-lock.json","specs/GH208/product.md","specs/GH208/tasks.md","specs/GH208/tech.md","states.yaml","templates","tests","tools/install_codex_skills.py","workflow.yaml"],"spec_refs":["specs/GH208/product.md","specs/GH208/tech.md","specs/GH208/tasks.md"]}
-->

manifest 中的目录条目声明该目录为本次重构的闭合修改子树；实现不得修改所列
根路径和子树以外的文件。最终 handoff 必须用 `git diff --name-only` 证明所有
实际路径均落在该闭集内。

## Product Spec

[`product.md`](product.md)

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| profile 与授权 | `workflow.yaml:15-59` | 只有 `review/auto` 授权模式，没有验证 profile；普通队列仍继承 spec/review/merge 多重 gate | 需要把风险强度与 merge 授权拆开 |
| Issue 状态机 | `states.yaml:1-99` | 18 个状态混合 Issue、spec PR、review、CI、merge 和 release | 需要收敛为八个 Issue 状态 |
| pack 闭集 | `checks/check_workflow.py:32-90` | 37 个 checker 中的大量 runtime/review helper 被强制要求 | 删除模块后必须同步 pack validator |
| schema 闭集 | `checks/pack_asset_validation.py:13-34` | 强制 17 个 schema，含 runtime/checkpoint/tier/thread 状态机 | 需要降到 8 个 durable artifact schema |
| PR gate | `checks/pr_gate.py:16-51` | 同时依赖 content binding、review contract、runtime tier、spec revision 和 evidence helper | 改为 profile-aware 的当前 head/CI/review/security 核心 gate |
| runtime ledger | `checks/runtime_ledger_gate.py:1-47` | 本地 checkpoint 复制 budget、Goal、review、tier、PR gate 和敏感路由状态 | 整个行为层删除，只保留可选文本游标 |
| queue contract | `skills/specrail-implement-queue/SKILL.md:210-249`、`:284-310` | 强制 budget telemetry、Goal、checkpoint、same-issue circuit breaker 和远端副作用 | 重写为基于 GitHub truth 的薄队列循环 |
| implx bootstrap | `skills/implx/SKILL.md:12-27`、`:42-80` | fastlane 仍加载六文件 bootstrap、完整 spec packet、review manifest、tier attestation | 缩为三文件/12 KiB，并让 profile 决定证据 |
| installed skills | `tools/install_codex_skills.py:41-103` | apply 后校验写入内容，但没有独立只读 installed-vs-lock doctor | 在现有工具内增加只读 `--check-installed`，不新建 gate |

## 设计方案

### 1. 三个正交 profile

在 `workflow.yaml` 增加 `verification_profiles`：

- `fastlane`：小型机械修复、测试或文档；linked Issue、focused/full project
  tests、一次 review、人工 merge 边界。
- `standard`：普通产品变更；linked Issue、可测试计划、一次 full review，若有
  P0/P1 修复则一次 diff-only review。
- `heavy`：auth、payments、secrets、权限、数据迁移、sensitive registry 或
  维护者指定；完整 product/tech/tasks、独立 review、安全证据、明确 merge
  authorization。

`auth_mode` 只决定本次 invocation 是否拥有正常 merge 授权，不能提升或降低
profile，也不能补齐证据。

### 2. 八状态 Issue graph

`states.yaml` 只保留：

```text
new_issue -> needs_info | ready_to_spec | ready_to_implement | parked
needs_info -> ready_to_spec | ready_to_implement | parked
ready_to_spec -> ready_to_implement | parked
ready_to_implement -> in_progress | parked
in_progress -> review | parked
review -> in_progress | done | parked
parked -> ready_to_spec | ready_to_implement
done -> terminal
```

`duplicate`、`abandoned`、`security_private` 为 outcome labels。validator 必须
拒绝同一 label 集合中的 `parked + ready_to_*` 和多个 readiness 标签。

### 3. 18 个核心 checker

最终只保留下列 `checks/*.py`：

1. `check_workflow.py`
2. `checks_availability.py`
3. `closure_audit.py`
4. `duplicate_work_gate.py`
5. `github_duplicate_evidence.py`
6. `github_evidence_common.py`
7. `github_issue_evidence.py`
8. `github_issue_reference.py`
9. `github_pr_evidence.py`
10. `pack_asset_validation.py`
11. `pr_gate.py`
12. `rejection_items.py`
13. `review_json_gate.py`
14. `route_gate.py`
15. `schema_validation.py`
16. `sensitive_enforcement.py`
17. `skill_size_gate.py`
18. `specrail_lib.py`

删除以下模块及所有 import：

- `evidence_content_binding.py`
- `github_approved_spec_evidence.py`
- `github_pr_snapshot.py`
- `github_review_evidence.py`
- `github_tier_evidence.py`
- `pr_evidence_items.py`
- `pr_review_contract.py`
- `review_content_binding.py`
- `review_result_semantics.py`
- `review_round_semantics.py`
- `runtime_budget_dimensions.py`
- `runtime_gate_rules.py`
- `runtime_ledger_gate.py`
- `runtime_pr_gate_evidence.py`
- `runtime_review_evidence.py`
- `runtime_sensitive_routes.py`
- `runtime_tier_authorization.py`
- `session_telemetry.py`
- `spec_revision_evidence.py`

必要的当前 head、CI、P0/P1、sensitive registry 和 merge authorization 判断直接
收敛到 `github_pr_evidence.py`、`pr_gate.py`、`review_json_gate.py` 与
`sensitive_enforcement.py`。不得用兼容 wrapper 保留旧状态机。

### 4. 八个 schema

保留并缩减：

- `duplicate_work_evidence.schema.json`
- `evaluation_result.schema.json`
- `issue_evidence.schema.json`
- `issue_triage.schema.json`
- `pr_review_gate.schema.json`
- `review_result.schema.json`
- `spec_packet.schema.json`
- `task_plan.schema.json`

删除 adoption、closure、content-binding、flow-manifest、PR authorization、
runtime checkpoint/tier/thread 和 workflow-run schema。closure 与 duplicate
结果是 advisory JSON，不再需要 durable schema。

### 5. 当前证据模型

`github_pr_evidence.py` 只采集：

- repository、PR number、linked Issue
- base/head SHA 和查询时 head
- changed files
- CI rollup
- current review verdict 与当前 head 的 unresolved P0/P1
- merge state
- profile 与 sensitive classification
- 当前 invocation 的人工 merge authorization（heavy 必需）

旧 runtime/tier/content-binding 字段出现时，adapter/gate 一次返回
`unsupported_legacy_evidence`，列出全部旧字段。

### 6. 有界 review

`review_json_gate.py` 成为 review 的单一 authority：

- round 1 为 full。
- round 2 只能为 diff-only。
- round >2 直接返回 `needs_human`，不接受逐轮授权 artifact。
- 当前 head 的 P0/P1 阻断。
- P2/P3 输出到 `follow_ups`，不阻断、不自动开 Issue。
- `outdated=true` 的 hosted thread 不阻断；当前 head 的 unresolved P0/P1
  仍阻断。

### 7. 无 runtime 第二状态机

删除 runtime checker、schema、fixture、tests 和 skills 文案。可选 checkpoint
改为一个无 schema 的 Markdown/YAML cursor，只允许：

```yaml
completed: []
pending: []
blocked: []
artifact_refs: []
resume_action: ""
```

它不参与 route/PR/merge decision。旧 checkpoint 只能触发重建提示。

### 8. 最小安装完整性

扩展现有 `tools/install_codex_skills.py`：

- 默认仍 dry-run。
- 新增只读 `--check-installed`。
- 对 `skills-lock.json` 中每个 `SKILL.md` 计算 SHA-256 并一次报告 missing/drift。
- drift 返回非零并提示显式重新安装与重启会话。
- 不实现事务 journal、mount traversal、migration authorization 或 consumer
  runtime bundle。

### 9. 技能和文档

- `implx` 只负责识别 invocation、刷新 GitHub truth、选择 profile、调用 focused
  skill，不保存 runtime 状态。
- queue skill 只保留 search-first、ownership、one issue/one PR、验证、review、
  merge/human gate、等待策略和停止条件。
- `fastlane` 启动集固定为 `AGENTS.md`、`workflow.yaml`、`skills/implx/SKILL.md`。
- docs 明确 breaking release 和旧 runtime artifact 不兼容。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001, B-002 | `workflow.yaml`, `route_gate.py`, profile fixtures | `pytest tests/test_route_gate.py tests/test_workflow_profiles.py` |
| B-003 | `sensitive_enforcement.py`, `pr_gate.py` | `pytest tests/test_pr_gate_sensitive_routes.py tests/test_sensitive_enforcement.py` |
| B-004 | `checks_availability.py`, workflow router docs | adopted/missing 与 not-adopted fixtures |
| B-005, B-006 | `states.yaml`, `labels.yaml`, `specrail_lib.py` | `pytest tests/test_specrail_yaml.py tests/test_workflow_profiles.py` |
| B-007 | profile/skill contracts | `pytest tests/test_review_contract_docs.py tests/test_workflow_profiles.py` |
| B-008, B-009, B-010 | `review_json_gate.py`, review schema | `pytest tests/test_review_json_gate.py tests/test_review_policy.py` |
| B-011 | duplicate/closure gates | `pytest tests/test_duplicate_work_gate.py tests/test_closure_audit.py` |
| B-012, B-013, B-017 | runtime asset absence and legacy negative fixtures | `pytest tests/test_legacy_runtime_removal.py` |
| B-014, B-015, B-016 | `skill_size_gate.py`, `check_workflow.py`, pack asset validator | `pytest tests/test_skill_size_gate.py tests/test_check_workflow.py tests/test_pack_asset_validation.py` |
| B-018 | rejection aggregation in route/review/PR gates | negative fixtures assert complete `rejection_items` set |
| B-019 | `workflow.yaml`, `pr_gate.py`, skill contracts | authorization negative fixtures and docs-token tests |
| B-020 | profile E2E fixtures | `pytest tests/test_profile_end_to_end.py`; full commands below |

## 数据流

```text
GitHub Issue + labels
        |
        v
route_gate(profile) ----> allowed / warning / needs_human / blocked
        |
        v
implementation PR + CI + current review evidence
        |
        v
pr_gate(profile, sensitive classification, human auth)
        |
        v
advisory merge-readiness result
```

本地 cursor 不进入该数据流。GitHub adapter 只读；所有远端写动作仍由显式授权的
orchestrator 执行。

## 备选方案

- 只合并 PR #198：拒绝。它基于旧 main、存在冲突，并新增大型
  `merge_authorization_gate.py`，属于删除一套状态机后新增另一套。
- 只保留 400/150 行上限：拒绝。压缩不能降低 checker/schema 数量或状态耦合。
- 为旧 runtime artifact 写迁移器：拒绝。迁移器会延续治理飞轮；直接从 GitHub
  truth 重建游标更简单。

## 风险

- Security：删除证据 helper 可能误删 sensitive fail-closed 语义；heavy profile
  的负例测试必须先锁定并在重写中保持。
- Compatibility：旧 checkpoint/tier/review round artifact 不兼容；发布为 breaking
  workflow version。
- Performance：profile 分类必须是本地、确定性、单次读取，不得引入新的网络轮询。
- Maintenance：不得通过把删除模块搬入新包来满足 checker 数量；最终以 git tree
  和 import 搜索验证。

## 测试计划

- [x] Unit tests：八状态、profile 分类、review policy、legacy rejection、installed
  hash doctor。
- [x] Integration tests：route gate、PR gate、sensitive heavy path、pack validator。
- [x] Manual verification：统计 checker/schema/skill 行数与 read-set bytes；检查
  `git diff --name-only` 未越出 manifest 子树。
- [x] Full verification：
  - `python3 checks/check_workflow.py --repo .`
  - `python3 checks/check_workflow.py --repo . --all-specs`
  - `/usr/bin/python3 -m pytest -q`
  - `python3 checks/skill_size_gate.py --repo . --json`
  - `git diff --check origin/main...HEAD`

## 回滚方案

整套变更保持在单一 GH208 分支并按 milestone commit 交付。若任一阶段无法保持
heavy/sensitive fail-closed 或全量测试，停止在该阶段，不 push 后续 commit。
发布后需要回滚时，revert GH208 implementation commits 并恢复上一版本 skills；
不尝试把新 cursor 反向迁移成旧 runtime checkpoint。
