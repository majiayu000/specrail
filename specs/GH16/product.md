# Product Spec

## Linked Issue

GitHub issue: `#16`
status: legacy

## 用户问题

Agent 在执行 `write_spec` 或 `implement` 前，需要从 GitHub issue 获取真实 state、labels 和 artifact 路径。当前只有 PR evidence adapter，issue evidence 仍靠手工整理，容易把缺失 label 或 stale body 当成已验证事实。

## 目标

- 提供只读 `checks/github_issue_evidence.py`。
- 输出 `checks/route_gate.py` 可消费的 JSON evidence。
- 保持 GitHub automation 的 dry-run / advisory 边界。

## 非目标

- 不写 GitHub labels、comments、issues 或 PRs。
- 不替代 maintainer readiness gate。
- 不改变 `pr_gate.py`。

## Behavior Invariants

1. 给定有效 `OWNER/REPO` 和 issue number，adapter 输出 issue number、title、url、state hint、labels 和默认 spec artifact paths。
2. 当 issue labels 中恰好有一个 SpecRail readiness state 时，adapter 把它作为 `state` evidence。
3. 当 labels 没有 readiness state 但 body 中有 `state: ready_to_spec` 这类显式 hint 时，adapter 可使用该 hint。
4. 当缺少 state evidence 时，adapter 不伪造成功；`route_gate.py` 必须继续返回 `needs_human` / `warn` / `blocked`。
5. 无效 repo、无效 issue number、缺失 `gh` 或非 JSON 输出必须非零退出并给出清晰错误。

## 验收标准

- [ ] `checks/github_issue_evidence.py` 是只读 collector。
- [ ] `schemas/issue_evidence.schema.json` 描述输出。
- [ ] tests 使用 fake `gh`，不依赖真实网络。
- [ ] README、AGENT_USAGE、PLAN、skill guidance 说明边界。

## 边界情况

- 多个 readiness labels 同时存在时不应静默选一个。
- issue body 中的 hint 只能使用已知 state。
- reserved/security state 应由 `route_gate.py` 继续阻塞。

## 发布说明

这是 advisory evidence adapter；consumer repo 可先在本地或 CI dry-run 中使用。
