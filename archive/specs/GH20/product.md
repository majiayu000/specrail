# Product Spec

## Linked Issue

GitHub issue: `#20`
status: legacy

## 用户问题

SpecRail 的 adoption matrix 记录真实 pilot evidence，但 gate behavior 缺少可复用 fixtures。测试里有内嵌 payload，不能作为可审计 benchmark corpus。

## 目标

- 新增 `examples/fixtures/` corpus。
- PR gate、route gate、review gate tests 复用 fixtures。
- docs 说明 fixtures 是 benchmark，不是 adoption claim。

## 非目标

- 不把 fixture 当真实远端状态。
- 不替代 live GitHub evidence adapters。

## Behavior Invariants

1. 每个 fixture 都是独立、可读、可复用的 JSON 或 patch artifact。
2. PR gate tests 至少覆盖 clean authorized、pending CI、unresolved thread、missing human auth。
3. Route/issue tests 至少覆盖 ready_to_spec、ready_to_implement、reserved_internal。
4. Review gate tests 至少覆盖 valid、invalid line、spec drift。

## 验收标准

- [ ] `examples/fixtures/` 包含 issue、PR、review fixtures。
- [ ] tests 读取 fixture 文件。
- [ ] docs 说明 fixture corpus 的用途和边界。

## 边界情况

- Fixtures 不应包含真实 secrets。
- External URLs 只能作为 inert evidence strings。

## 发布说明

这是测试和 benchmark 资产，不改变 runtime policy。
