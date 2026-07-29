# Tech Spec

## Linked Issue

GH-163

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":163,"complete":true,"paths":[".gitignore","checks/review_json_gate.py","checks/review_result_semantics.py","schemas/review_result.schema.json","skills/specrail-review-pr/SKILL.md","skills-lock.json","tests/test_review_json_gate.py","tests/test_specrail_schema.py","specs/GH163/product.md","specs/GH163/tech.md","specs/GH163/tasks.md"],"spec_refs":["specs/GH163/product.md","specs/GH163/tech.md"]}
-->

## Product Spec

`specs/GH163/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Review route contract | `skills/specrail-review-pr/SKILL.md:14` | route gate 与 artifact gate 的执行条件由 skill 文本定义 | 必须消除 “when available” 静默跳过语义 |
| Artifact JSON gate | `checks/review_json_gate.py:170` | `_validate_top_level()` 校验允许字段、body heading 与 review 状态 | degraded evidence 必须在同一门禁内 fail closed |
| Artifact schema | `schemas/review_result.schema.json:1` | `additionalProperties: false`；manifest loader 使用此 schema | 新字段若未进入 schema，会在下游被拒绝 |
| Shared semantics / manifest loader | `checks/review_result_semantics.py:1` | JSON gate 与 `load_review_manifest()` 共享 degraded provenance 语义校验 | 防止任一入口绕过双向 status/auth/marker/claim invariant |
| Rejection artifacts | `.gitignore:7` | 本地 rejection evidence 不进入版本控制 | 允许按 B-009 持久化失败证据而不污染 PR |
| Regression tests | `tests/test_review_json_gate.py:510` | 同时覆盖 JSON gate 与 schema-backed manifest | 可证明 checker 与 schema 不再漂移 |

## 设计方案

1. Skill 将 route gate 与 review artifact gate 定义为存在时必跑；缺失或执行错误均
   fail closed。人工授权只开启显式 degraded 路径。
2. Degraded artifact 使用两个可选顶层字段：`gate_status` 闭集为
   `gated | unavailable`，`gate_authorization` 保存人工授权原文。
3. 共享 semantic validator 双向校验 status/auth/marker：unavailable 要求非空白授权、
   exact-case marker 位于 `## Summary`；完整 body 与 published comment text 均不得声称
   SpecRail-gated、verified 或 merge-ready；反向出现 marker 或授权也必须配套
   unavailable 状态。
4. `review_result.schema.json` 接受新字段，并用 conditional schema 与 `\\S` pattern
   执行可移植的结构约束；旧 artifact 不声明字段时不触发 conditional。
5. JSON gate 与 schema-backed manifest 都调用共享 semantic validator，保证两个
   trust boundary 对同一 artifact 给出一致的 fail-closed 结果。合规 unavailable
   artifact 可发布用于审计，但 semantic layer 固定返回 merge-readiness blocker。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-003 | `skills/specrail-review-pr/SKILL.md` | `python3 checks/check_workflow.py --repo .` 与人工核对 Gate Availability 表 |
| B-004 B-005 B-006 | `checks/review_json_gate.py`, `checks/review_result_semantics.py` | `uvx pytest tests/test_review_json_gate.py -q -k 'gate_status or authorization or degraded or marker or unavailable'` |
| B-007 | `schemas/review_result.schema.json`, shared semantics, manifest loader tests | `uvx pytest tests/test_review_json_gate.py tests/test_specrail_schema.py -q -k 'manifest or gate_authorization'` |
| B-008 | 既有 artifact fixtures | `uvx pytest tests/test_review_json_gate.py -q` |
| B-009 | rejection persistence contract | `python3 checks/check_workflow.py --repo .` |

## 数据流

Skill route preflight → gate exists/error classification → 可选人工 degraded authorization →
review artifact（status + authorization + summary marker）→ `review_json_gate.py` →
schema-backed `load_review_manifest()`。任一证据缺口都输出 blocked，不产生静默成功。

## 备选方案

- 只在 skill 文本中提示：拒绝。无法防止 artifact schema/checker 漂移。
- 只允许 `gate_status` 而不记录授权：拒绝。无法审计 degraded 路径的授权来源。
- gate 缺失时自动安装 SpecRail：拒绝。越过仓库与用户的安装授权边界。

## 风险

- Security: 授权文本仍是审计证据而非密码学证明；但缺失时稳定阻断。
- Compatibility: 新字段可选，旧 artifact 行为不变；声明 unavailable 时采用新规则。
- Performance: 常数级字符串与 schema 校验，无可测性能影响。
- Maintenance: checker 与 schema 双处规则可能漂移，由 manifest regression test 绑定。

## 测试计划

- [ ] Unit tests: 合规 degraded、缺授权、缺披露、非法状态、孤立授权。
- [ ] Integration tests: schema-backed manifest 接受合规 degraded artifact。
- [ ] Full verification: 完整 `pytest`、workflow check、diff check。

## 回滚方案

回滚 GH-163 merge commit 可恢复旧行为；无数据迁移。回滚会重新开放静默降级风险，
只能作为短期兼容应急。
