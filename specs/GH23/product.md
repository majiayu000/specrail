# Product Spec

## Linked Issue

GitHub issue: `#23`

## 用户问题

Agent review artifacts 已能校验单行 diff location，但 GitHub review 常见的 multi-line
comment range、suggestion block 和 structured review body 还没有被约束。缺少这些约束时，
review JSON 可以看似合规，却无法稳定发布为可审查的 inline review artifact。

## 目标

- 支持 `start_line` / `start_side` multi-line range。
- 校验 suggestion 内容只出现在合法 RIGHT-side diff comment。
- 要求 review body 包含稳定的 summary / verdict 结构。

## 非目标

- 不自动发布 GitHub review。
- 不支持完整 GitHub suggested-changes API 语义。
- 不把 advisory `APPROVE` 当作 human final approval。

## Behavior Invariants

1. 单行 comment 必须继续绑定 diff 中存在的 `path` / `line` / `side`。
2. Multi-line comment 必须同时提供 `start_line` 和 `start_side`，且 range 内每一行都存在于对应 diff side。
3. Suggestion 内容必须非空，并且只能用于 RIGHT-side comment。
4. Review body 必须包含 `## Summary` 和 `## Verdict` heading。
5. Final approval / merge authority language 必须继续被 blocked。

## 验收标准

- [ ] `schemas/review_result.schema.json` 描述 range 和 suggestion 字段。
- [ ] `checks/review_json_gate.py` 校验 range、suggestion 和 body contract。
- [ ] fixtures 覆盖 valid range/suggestion、invalid range、invalid suggestion、invalid body。
- [ ] tests 覆盖新增行为和现有 final-authority guard。

## 边界情况

- `start_line` 单独出现或 `start_side` 单独出现时必须 blocked。
- LEFT-side deleted line 不能附带 suggestion。
- Empty fenced suggestion block 必须 blocked。

## 发布说明

Review artifact gate 更接近可发布 inline review contract，但仍然保持 advisory-only。
