# Tech Spec

## Linked Issue

GH-200

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":200,"complete":true,"paths":["integrations/threads.md","skills-lock.json","skills/specrail-implement-queue/SKILL.md","specs/GH200/product.md","specs/GH200/tasks.md","specs/GH200/tech.md"],"spec_refs":["specs/GH200/product.md","specs/GH200/tech.md","specs/GH200/tasks.md"]}
-->

## Product Spec

见 `specs/GH200/product.md`。本设计覆盖 B-001..B-008。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue reviewer default | `skills/specrail-implement-queue/SKILL.md:367` | fastlane/standard 的一个独立 lane 满足默认要求。 | B-001 的主合同。 |
| extra-lane exceptions | `skills/specrail-implement-queue/SKILL.md:371` | heavy、人工要求、lane failure 才允许额外 lane。 | B-002 的封闭例外。 |
| artifact repair | `skills/specrail-implement-queue/SKILL.md:376`、`skills/specrail-implement-queue/SKILL.md:378` | 格式/元数据缺陷重生成 artifact 并只跑 review gate。 | B-003/B-004。 |
| threads orchestration | `integrations/threads.md:222` | integration 层复述单 lane 与 artifact repair 规则。 | 多执行器的一致入口。 |
| bounded review | `skills/specrail-review-pr/SKILL.md:70`、`skills/specrail-review-pr/SKILL.md:90` | manifest v2、round cap 与升级授权。 | B-007 不得被性能优化削弱。 |
| artifact gate | `checks/review_json_gate.py:318`、`checks/review_json_gate.py:722` | 输出 round/mode 证据并保持 advisory-only。 | artifact repair 的确定性验证点。 |
| manifest semantics | `checks/review_result_semantics.py:424`、`checks/review_result_semantics.py:444` | 安全加载 manifest，接受 v1/v2 并校验 terminal artifact。 | B-003/B-005/B-008 的机器边界。 |

## 设计方案

### 1. Reviewer lane 决策

queue 与 threads integration 使用同一决策表：

| 条件 | lane 行为 |
| --- | --- |
| fastlane/standard，首轮，无失败 | 一个 independent reviewer |
| heavy | 可按风险增加 lane |
| 人类明确要求 | 记录授权后增加 lane |
| lane failure | 保留失败记录，用新 lane retry |

不得用“更谨慎”作为未记录的额外 lane 理由。

### 2. Artifact-only 修复

只有原始 reviewer 输出可复用、head 未变化且缺陷仅位于 artifact 表示层时，协调者从
原输出重新生成 JSON/manifest，运行 `review_json_gate.py` 和 manifest loader。
测试、CI、PR snapshot 与 reviewer 推理均不重做。

### 3. 正常 re-review 分流

head 变化、真实 finding、审查范围不足或原输出缺失时，进入
`bounded_diff_v1`。第二轮起使用 `resumed|diff_only`，保留 typed carry 和 lane
failure 证据。artifact 修复不得递增 `review_round`。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | queue + threads default lane wording | `rg -n "One reviewer lane per PR|one reviewer lane per PR" skills/specrail-implement-queue/SKILL.md integrations/threads.md` |
| B-002 | extra-lane exception wording | `rg -n "heavy.*human|human.*lane failure|lane failure.*retry" skills/specrail-implement-queue/SKILL.md integrations/threads.md` |
| B-003 | artifact repair contract | `.venv/bin/python -m pytest -q tests/test_review_json_gate.py tests/test_review_result_semantics.py` |
| B-004 | unchanged-head repair boundaries | `rg -n "does not open a new review round|does not re-run tests" skills/specrail-implement-queue/SKILL.md` |
| B-005 | semantic gate + current-head selection | `.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_review_content_binding.py` |
| B-006 | lane failure/retry contract | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_review.py tests/test_runtime_ledger_gate.py` |
| B-007 | bounded round contract | `.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate_terminal.py` |
| B-008 | head/artifact identity validation | `.venv/bin/python -m pytest -q tests/test_github_pr_evidence.py tests/test_review_content_binding.py` |

## 数据流

```text
reviewer output + unchanged head
  -> representation defect? yes -> regenerate artifact -> review_json_gate
                           no  -> normal finding/fix/re-review flow

lane selection
  -> default one
  -> heavy/human/failure evidence -> additional lane
```

无新持久化格式；使用现有 review artifact、manifest、lane failure 和 checkpoint 字段。

## 备选方案

- 每 PR 固定多 lane：成本高且无风险分级，拒绝。
- artifact gate 失败就整轮重审：没有新增审查信息，拒绝。
- 所有 gate 失败都只修 JSON：会掩盖真实 finding，拒绝。

## 风险

- Security: 误分类真实 finding 会跳过复审；仅表示层缺陷允许 repair。
- Compatibility: v1/v2 manifest 均保持现有 loader 语义。
- Performance: 普通 PR 少派 lane，artifact 格式错误不重复验证。
- Maintenance: queue、threads 与 review skill 的 bounded contract 必须保持一致。

## 测试计划

- [ ] Unit: review JSON、manifest semantics、lane failure tests。
- [ ] Integration: GH200 packet check 与 lock check。
- [ ] Regression: full pytest、all-specs、diff check。
- [ ] Manual: 对照决策表确认三种额外 lane 原因是封闭集合。

## 回滚方案

回滚 queue/threads 文本、GH200 规格与 lock hash；review gate/schema 无格式迁移。
