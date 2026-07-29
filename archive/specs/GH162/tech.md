# Tech Spec

## Linked Issue

GH-162

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":162,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/github_pr_evidence.py","checks/pr_review_contract.py","checks/review_json_gate.py","checks/review_result_semantics.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","schemas/pr_review_gate.schema.json","schemas/review_result.schema.json","schemas/runtime_checkpoint.schema.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-pr-gate/SKILL.md","skills/specrail-review-pr/SKILL.md","skills-lock.json","tests/github_pr_evidence_test_support.py","tests/runtime_ledger_test_support.py","tests/test_github_pr_evidence.py","tests/test_pr_gate_terminal.py","tests/test_review_json_gate.py","tests/test_runtime_ledger_gate.py","tests/test_runtime_ledger_review.py","tests/test_specrail_schema.py","examples/fixtures/pr-clean-authorized.json","examples/fixtures/pr-gate-head-mismatch.json","examples/fixtures/pr-implementer-resolved-thread.json","examples/fixtures/pr-merge-api-fallback-confirmed.json","examples/fixtures/pr-merge-confirmed.json","examples/fixtures/pr-merge-missing-path.json","examples/fixtures/pr-merge-unconfirmed-local-failure.json","examples/fixtures/pr-missing-human-auth.json","examples/fixtures/pr-missing-thread-resolver.json","examples/fixtures/pr-outdated-unresolved-thread.json","examples/fixtures/pr-pending-ci.json","examples/fixtures/pr-query-after-merge.json","examples/fixtures/pr-self-review-source.json","examples/fixtures/pr-self-review-unauthorized.json","examples/fixtures/pr-unresolved-thread.json","examples/fixtures/runtime-lane-failure-retried.json","examples/fixtures/runtime-self-review-merged-unauthorized.json","examples/fixtures/review-clean-pr10.json","examples/fixtures/review-clean-pr718.json","examples/fixtures/review-clean-pr718-self.json","examples/fixtures/review-valid.json","tests/fixtures/gh143-review-artifact-pr718.json","tests/fixtures/gh143-standard-auto.json","specs/GH162/product.md","specs/GH162/tech.md","specs/GH162/tasks.md"],"spec_refs":["specs/GH162/product.md","specs/GH162/tech.md"]}
-->

## Product Spec

`specs/GH162/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Artifact semantics | `checks/review_result_semantics.py:123` | required strings 只有 `review_source`，manifest 只聚合 source | 必须增加并聚合 execution provenance |
| PR evidence | `checks/github_pr_evidence.py:398` | 从 manifest 派生 `review_source` 与完成时间 | 同一路径派生 execution，禁止顶层自报 |
| PR gate schema | `schemas/pr_review_gate.schema.json:353` | review evidence 没有 execution 字段 | 新字段必须进入 evidence contract |
| Runtime merge gate | `checks/runtime_ledger_gate.py:660` | merge-ready 只区分 independent/self-review | implx 主路径也必须拒绝 hosted-as-primary |
| Runtime schema | `schemas/runtime_checkpoint.schema.json:578` | review summary 没有 execution 字段 | checkpoint 需要可验证 provenance |
| Skill contract | `skills/implx/SKILL.md:173`, `skills/specrail-pr-gate/SKILL.md:63` | 要求 reviewer lane，但未区分本地与 hosted | 明确 primary 与 supplemental 边界 |

## 设计方案

1. 在 terminal review artifact 增加 `review_execution`，闭集为 `local | hosted`。
   Schema 保持字段可解析，但 semantic validator 将缺失视为错误，从而兼顾诊断旧
   artifact 与 fail-closed merge gate。
2. `validate_review_artifact()` 校验闭集，并拒绝
   `independent_lane + hosted` 作为 terminal primary artifact；`self_review` 只允许
   `local`。
3. `load_review_manifest()` 聚合当前 head artifact 的 execution；多值冲突写入 blocker，
   输出 `review_execution`。GitHub adapter 只转发该派生值。
4. PR evidence schema 要求派生的 `review_execution`；offline gate 重新验证嵌入 artifact，
   因而 hosted 或缺失字段均 blocked。
5. Runtime checkpoint review summary 新增 `review_execution`，merge-ready
   independent/self-review 均要求 local。`review.evidence` 必须是本地 JSON artifact；
   loader 先执行 schema 与共享 `validate_review_artifact()` 语义校验，并传播 errors 与
   blocking reasons，同时保留已解析 payload 供后续 binding/tier diagnostics。然后将
   artifact 的 PR、reviewer lane、artifact ID、source、execution、head、完成时间、
   status、verdict、human gate、findings 与 prior findings 和 summary 逐项比较。URL、
   缺失/非 JSON、legacy、hosted、字段错配、非法时间戳及 `clean` + findings 均阻断。
6. Skill/使用文档规定：本地 CLI/native lane 是 primary；`@codex review` 是可选
   supplemental，不能填充 primary artifact 或 reviewer lane evidence。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-006 B-009 | `review_result_semantics.py`, review schema | `python3 -m pytest -q tests/test_review_json_gate.py` |
| B-003 B-004 B-010 | manifest aggregation tests | `python3 -m pytest -q tests/test_review_json_gate.py -k execution` |
| B-007 | `github_pr_evidence.py`, PR evidence schema | `python3 -m pytest -q tests/test_github_pr_evidence.py -k review` |
| B-008 B-011 | PR gate + runtime ledger artifact binding | `python3 -m pytest -q tests/test_pr_gate_terminal.py tests/test_runtime_ledger_review.py tests/test_runtime_ledger_gate.py` |
| B-005 | `implx`, `specrail-pr-gate`, `AGENT_USAGE.md` | `rg -n "@codex review|review_execution|supplemental" skills AGENT_USAGE.md` and pack check |

## 数据流

本地 reviewer CLI/native lane → exact-head terminal artifact（source + execution）→ review
manifest 聚合 → GitHub PR evidence adapter → offline `pr_gate`。Hosted review 只作为 GitHub
评论/review 可见，不进入 primary terminal manifest；若显式记录为 hosted artifact，gate
稳定阻断。Runtime checkpoint 从同一 artifact 摘要复制 execution；ledger gate 重新加载本地
artifact，执行 schema + semantic validation，并把身份、head、verdict 与 findings 等摘要
字段逐项绑定后才接受 merge-ready。

## 备选方案

- 按 bot 登录名黑名单识别 `chatgpt-codex-connector`：拒绝。厂商耦合且可改名。
- 完全禁用 `@codex review`：拒绝。用户明确允许其作为 supplemental。
- 把 `independent_lane` 重命名为 `local_lane`：拒绝。独立性与执行位置是正交维度，且会
  造成不必要迁移。

## 风险

- Security: provenance 仍由本地 artifact 生产者声明，不是密码学证明；但 gate 不再把
  GitHub hosted review 自动等价为 local evidence，也不允许 checkpoint summary 脱离
  artifact 自报 local/clean。Artifact 语义错误仍保留 payload 进入 binding/tier diagnostics，
  但整体决定 fail closed。
- Compatibility: 旧 artifact 缺字段将不能满足 merge gate，属于预期 fail-closed 迁移。
- Performance: 仅增加常数级字段校验。
- Maintenance: PR gate 与 runtime ledger 必须保持规则一致，由双路径回归测试约束。

## 测试计划

- [ ] Unit tests: semantic、manifest aggregation、adapter、PR gate、runtime ledger。
- [ ] Integration tests: 完整 `pytest` 与 `check_workflow --all-specs`。
- [ ] Manual verification: 本地 `codex review`/native lane 与 GitHub `@codex review` 文案区分。

## 回滚方案

回滚 GH-162 单一提交即可恢复旧契约；无数据库、网络或远端权限迁移。回滚会重新允许
hosted review 被误记为 primary，因此只应在 gate 兼容事故下临时执行。
