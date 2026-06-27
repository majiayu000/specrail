# Tech Spec

## Linked Issue

GitHub issue: `#20`

## Product Spec

`specs/GH20/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| PR gate tests | `tests/test_pr_gate.py` | 使用内嵌 `clean_evidence()`。 | 应改为读取 fixtures。 |
| Adoption matrix | `docs/ADOPTION_MATRIX.md`, `examples/adoptions/matrix.json` | 记录 real repo adoption evidence。 | 需要明确 fixtures 不是 adoption claims。 |
| New gates | `checks/github_issue_evidence.py`, `checks/review_json_gate.py` | 将新增。 | 需要共享 fixture corpus。 |

## 设计方案

新增 `examples/fixtures/`。将 PR gate tests 的 canonical payload 搬到 JSON fixture，保留 helper 读取并按测试修改少量字段。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | fixture files | JSON parse tests |
| P2 | PR fixtures/tests | `uvx pytest -q tests/test_pr_gate.py` |
| P3 | issue fixtures/tests | `uvx pytest -q tests/test_github_issue_evidence.py` |
| P4 | review fixtures/tests | `uvx pytest -q tests/test_review_json_gate.py` |

## 数据流

Fixture file -> test helper -> gate evaluator -> expected decision.

## 备选方案

- 保持内嵌 fixtures：拒绝，不能形成可审计 corpus。

## 风险

- Security: 不放入 secrets。
- Compatibility: Test helper paths must be stable from repo root.
- Performance: JSON fixture loading cost negligible.
- Maintenance: Fixtures must stay aligned with schemas.

## 测试计划

- [ ] Unit tests: fixture loading in PR/issue/review tests。
- [ ] Manual verification: `python3 checks/check_workflow.py --repo .`。

## 回滚方案

恢复内嵌 test fixtures，删除 `examples/fixtures/`。
