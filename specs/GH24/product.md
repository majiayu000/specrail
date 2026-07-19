# Product Spec

## Linked Issue

GitHub issue: `#24`
status: legacy

## 用户问题

Issue evidence adapter 现在会从 label 或 issue body hint 推断 `state`，但输出没有说明 state
来自哪里。因为 issue body 通常可由 requester 编辑，`state: ready_to_implement` 不能等同 maintainer
readiness label。如果 route gate 直接信任 body hint，就会弱化人类 readiness gate。

## 目标

- Issue evidence 输出 `state_source` 和 `state_trusted`。
- Label-derived state 明确为 trusted。
- Body hint-derived state 明确为 untrusted，并触发 human gate。

## 非目标

- 不删除 body hint 支持；fixtures 和 self-managed workflows 仍可使用。
- 不自动写 GitHub labels 或 comments。
- 不引入 maintainer-authored comment adapter。

## Behavior Invariants

1. 当 state 来自 readiness 或 terminal label 时，evidence 必须包含 `state_source: "label"` 和 `state_trusted: true`。
2. 当 state 仅来自 issue body hint 时，evidence 必须包含 `state_source: "body_hint"` 和 `state_trusted: false`。
3. 当没有 state evidence 时，`state_source` 必须是 `"none"` 且 `state_trusted` 为 `false`。
4. `route_gate.py` 不能让 untrusted body hint 直接通过 `write_spec` 或 `implement`。
5. 显式 CLI `--state` 行为保持兼容，并仍由调用者负责 human gate 语义。

## 验收标准

- [ ] `github_issue_evidence.py` 输出新增字段。
- [ ] `schemas/issue_evidence.schema.json` 和 fixtures 更新。
- [ ] `route_gate.py` 对 untrusted evidence 返回 `needs_human`。
- [ ] tests 覆盖 label trusted、body hint untrusted、route gate body hint blocking。
- [ ] docs 说明 body hint 不能替代 maintainer readiness label。

## 边界情况

- Label 和 body hint 同时存在时，label 优先。
- Terminal labels 仍然由 route gate 阻塞。
- Closed GitHub issue 仍然 blocked。

## 发布说明

Issue evidence 更清楚地区分事实来源，避免 requester-owned body text 绕过 readiness labels。
