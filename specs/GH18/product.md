# Product Spec

## Linked Issue

GitHub issue: `#18`

## 用户问题

SpecRail 模板可以生成 spec，但 product spec 对行为契约约束不足，tech spec 对 codebase grounding 和 verification mapping 约束不足。

## 目标

- Product spec 强制 `Behavior Invariants`。
- Tech spec 强制 `Codebase Context` 和 `Product-to-Test Mapping`。
- 英文与 `zh-CN` 模板保持结构对齐。

## 非目标

- 不重写历史 spec packet。
- 不添加 repo-specific guidance。

## Behavior Invariants

1. 新 product spec 模板引导 agent 写 numbered, testable behavior invariants。
2. 新 tech spec 模板要求列出 relevant files/current behavior/why relevant。
3. 新 tech spec 模板要求每个 product invariant 映射 implementation 和 verification。

## 验收标准

- [ ] 英文和中文 product spec 模板包含 `Behavior Invariants`。
- [ ] 英文和中文 tech spec 模板包含 `Codebase Context`。
- [ ] 英文和中文 tech spec 模板包含 `Product-to-Test Mapping`。

## 边界情况

- Stable IDs 和 paths 不翻译。
- 模板不应假设特定语言或框架。

## 发布说明

这是模板质量升级，不改变运行时。
