# Tech Spec

## Linked Issue

GH-163

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":163,"complete":true,"paths":[".gitignore","checks/review_json_gate.py","schemas/review_result.schema.json","skills/specrail-review-pr/SKILL.md","skills-lock.json","tests/test_review_json_gate.py","specs/GH163/product.md","specs/GH163/tech.md","specs/GH163/tasks.md"],"spec_refs":["specs/GH163/product.md","specs/GH163/tech.md"]}
-->

## Product Spec

`specs/GH163/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Review route contract | `skills/specrail-review-pr/SKILL.md:14` | route gate 与 artifact gate 的执行条件由 skill 文本定义 | 必须消除 “when available” 静默跳过语义 |
| Artifact JSON gate | `checks/review_json_gate.py:170` | `_validate_top_level()` 校验允许字段、body heading 与 review 状态 | degraded evidence 必须在同一门禁内 fail closed |
| Artifact schema | `schemas/review_result.schema.json:1` | `additionalProperties: false`；manifest loader 使用此 schema | 新字段若未进入 schema，会在下游被拒绝 |
| Manifest loader | `checks/review_result_semantics.py:257` | `load_review_manifest()` 在聚合前执行 schema validation | 用于验证合规 degraded artifact 的端到端兼容性 |
| Rejection artifacts | `.gitignore:7` | 本地 rejection evidence 不进入版本控制 | 允许按 B-009 持久化失败证据而不污染 PR |
| Regression tests | `tests/test_review_json_gate.py:510` | 同时覆盖 JSON gate 与 schema-backed manifest | 可证明 checker 与 schema 不再漂移 |

## 设计方案

1. Skill 将 route gate 与 review artifact gate 定义为存在时必跑；缺失或执行错误均
   fail closed。人工授权只开启显式 degraded 路径。
2. Degraded artifact 使用两个可选顶层字段：`gate_status` 闭集为
   `gated | unavailable`，`gate_authorization` 保存人工授权原文。
3. 当且仅当 `gate_status == unavailable` 时要求非空 `gate_authorization`，并要求
   body 包含稳定披露标记 `SpecRail gate status: unavailable`。
4. `review_result.schema.json` 接受新字段，并用 conditional schema 要求 unavailable
   状态同时携带授权和披露；旧 artifact 不声明字段时不触发 conditional。
5. JSON gate 重复执行同一语义校验，保证 artifact 发布前即可得到具名 rejection，
   而不是等到下游 manifest loader 才失败。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-003 | `skills/specrail-review-pr/SKILL.md` | `python3 checks/check_workflow.py --repo .` 与人工核对 Gate Availability 表 |
| B-004 B-005 B-006 | `checks/review_json_gate.py` | `uvx pytest tests/test_review_json_gate.py -q -k 'gate_status or authorization or disclosure'` |
| B-007 | `schemas/review_result.schema.json`, manifest loader tests | `uvx pytest tests/test_review_json_gate.py -q -k 'manifest_allows_explicit_ungated'` |
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
