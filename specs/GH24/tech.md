# Tech Spec

## Linked Issue

GitHub issue: `#24`

## Product Spec

`specs/GH24/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Issue adapter | `checks/github_issue_evidence.py` | 返回 `state`，但不暴露 source/trust。 | 需要区分 label 和 body hint。 |
| Issue schema/fixtures | `schemas/issue_evidence.schema.json`, `examples/fixtures/issue-*.json` | schema required fields 未包含 trust metadata。 | 需要让 evidence contract 可验证。 |
| Route gate | `checks/route_gate.py` | 直接使用 evidence `state` 作为 explicit state。 | 需要对 untrusted source 进入 human gate。 |
| Tests | `tests/test_github_issue_evidence.py` | 已覆盖 label/body hint/closed issue。 | 需要新增 trust expectations 和 route gate behavior。 |

## 设计方案

在 adapter 中新增 `infer_state()` style helper，返回 `(state, state_source, state_trusted)`：

- label match: `("ready_to_spec", "label", true)`
- body hint: `("ready_to_spec", "body_hint", false)`
- no state: `(null, "none", false)`

在 `route_gate.py` 中读取 evidence metadata。若 route 是 `write_spec` 或 `implement`，当前 state 来自
untrusted evidence，且没有显式 `--state` 覆盖，则 decision 为 `needs_human`，missing 包含
`trusted_state`，reason 明确要求 maintainer readiness label。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | label state source | `tests/test_github_issue_evidence.py` label test |
| P2 | body hint state source | body hint test |
| P3 | no state source | new no-state test |
| P4 | route gate human gate | subprocess route gate test with tmp evidence |
| P5 | explicit `--state` compatibility | existing route gate behavior |

## 数据流

`gh issue view` JSON -> adapter source/trust metadata -> issue evidence JSON -> route gate trust check.

## 备选方案

- 完全移除 body hint：拒绝，因为本地 fixtures 和 lightweight workflows 仍然需要非-label hint。

## 风险

- Security: body hint 不再被当作 trusted readiness fact。
- Compatibility: consumer fixtures 需要新增两个 required fields。
- Performance: 无变化。
- Maintenance: 后续若新增 trusted comment adapter，可扩展 `state_source` enum。

## 测试计划

- [ ] Unit tests: label/body/none source metadata。
- [ ] Integration tests: fake `gh` CLI 输出新增 fields。
- [ ] Route gate tests: body hint state returns `needs_human` for `write_spec` / `implement`。

## 回滚方案

移除 metadata 和 route gate trust check；保留原 state inference 行为。
