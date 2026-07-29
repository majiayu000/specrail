# Tech Spec

## Linked Issue

GitHub issue: `#23`

## Product Spec

`specs/GH23/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Review gate | `checks/review_json_gate.py` | 校验 top-level fields、单行 diff location、severity、spec drift、final-authority wording。 | 需要扩展 comment shape 和 policy checks。 |
| Review schema | `schemas/review_result.schema.json` | 只允许 `path`、`line`、`side`、`severity`、`body`。 | 需要新增 optional range/suggestion fields。 |
| Fixtures/tests | `examples/fixtures/review-*.json`, `tests/test_review_json_gate.py` | 覆盖 valid、invalid line/severity、spec drift、authority wording。 | 需要新增 regression corpus。 |
| Review docs | `review/agent_first_review.md`, route skill | 描述 advisory JSON contract。 | 需要同步告诉 agent 如何写 body/range/suggestion。 |

## 设计方案

在 `review_json_gate.py` 中：

- 扩展 comment allowed keys：`start_line`、`start_side`、`suggestion`。
- 新增 body contract check：`body` 必须包含 `## Summary` 和 `## Verdict`。
- 新增 range checker：对 start/end inclusive range 的每一行调用 diff index。
- 新增 suggestion checker：支持 `suggestion` 字段和 body 中 fenced `suggestion` block；内容必须非空且 side 为 RIGHT。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | Existing location check | Existing valid/invalid line tests |
| P2 | Range checker | invalid range fixture/test |
| P3 | Suggestion checker | valid fixture + invalid suggestion fixture/test |
| P4 | Body contract | invalid body fixture/test |
| P5 | Authority wording | existing denylist test |

## 数据流

review JSON + unified diff -> top-level/body validation -> comment shape/range/suggestion validation -> advisory decision JSON.

## 备选方案

- 只在 skill 文档中要求 range/suggestion：拒绝，因为 artifact contract 必须可机器验证。

## 风险

- Security: 不执行 suggestion 内容。
- Compatibility: 旧 review fixtures 需要补 body heading；schema optional fields 保持向后扩展。
- Performance: range validation 只查 set membership。
- Maintenance: suggestion parsing 保守，复杂 markdown 可后续扩展。

## 测试计划

- [ ] Unit tests: range success/failure、suggestion success/failure、body contract。
- [ ] CLI tests: valid fixture still exits zero。
- [ ] Manual verification: `python3 checks/review_json_gate.py --repo . --review examples/fixtures/review-valid.json --diff examples/fixtures/pr-diff.patch --json`。

## 回滚方案

移除新增 fields/checks/fixtures；保留现有单行 review gate。
