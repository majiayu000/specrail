# Tech Spec

## Linked Issue

GitHub issue: `#16`

## Product Spec

`specs/GH16/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| PR evidence | `checks/github_pr_evidence.py`, `tests/test_github_pr_evidence.py` | 只读收集 PR merge-readiness evidence。 | issue adapter 应复用 CLI/normalization/error 风格。 |
| Route gate | `checks/route_gate.py` | 读取 `state`、`labels`、`artifacts` 并决定 route。 | issue adapter 输出必须直接可消费。 |
| Shared helpers | `checks/specrail_lib.py` | 提供 state map、artifact path rendering。 | adapter 可复用 state/artifact 逻辑，避免重复 policy。 |

## 设计方案

新增 `checks/github_issue_evidence.py`：

- `parse_github_repo`、`parse_issue_number`、`run_gh_json` 与 PR adapter 风格一致。
- `collect_issue_view` 调用 `gh issue view --json number,title,state,labels,url,body`。
- `build_evidence(repo_root, issue_payload)` 输出 `issue`、`title`、`url`、`labels`、`state`、`artifacts`。
- labels 中的 known readiness state 优先；body hint 次之。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `build_evidence` normalization | Unit test with fake issue payload |
| P2 | readiness label inference | Unit test label state |
| P3 | body hint parsing | Unit test body state |
| P4 | route gate consumption | Fixture + `evaluate_route` / CLI test |
| P5 | CLI error handling | fake `gh` and invalid arg tests |

## 数据流

`gh issue view` JSON -> normalizer -> evidence JSON -> `route_gate.py --evidence`.

## 备选方案

- 让 `route_gate.py` 直接调用 GitHub：拒绝，因为 policy evaluator 必须保持 offline。

## 风险

- Security: shell command 必须用 array args。
- Compatibility: GitHub label names may be repo-specific; unknown labels remain labels only.
- Performance: 单 issue view 成本低。
- Maintenance: body hint parser 必须保守。

## 测试计划

- [ ] Unit tests: normalization, repo/issue parsing, body hint parsing。
- [ ] Integration tests: fake `gh` CLI。
- [ ] Manual verification: `route_gate.py --evidence examples/fixtures/issue-ready-to-spec.json`。

## 回滚方案

删除 adapter、schema、tests 和 docs references；不会影响现有 PR gate。
