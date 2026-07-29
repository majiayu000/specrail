# Tech Spec

## Linked Issue

GitHub issue: `#17`

## Product Spec

`specs/GH17/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Review guide | `review/agent_first_review.md` | 只要求简单 findings JSON。 | 需要升级为 schema-backed artifact。 |
| PR gate | `checks/pr_gate.py`, `schemas/pr_review_gate.schema.json` | 检查 merge-readiness evidence。 | review gate 应独立，不混入 merge policy。 |
| Fixtures | `examples/fixtures/` | 当前缺少 corpus。 | review gate tests 需要 patch/review fixtures。 |

## 设计方案

新增 `schemas/review_result.schema.json` 和 `checks/review_json_gate.py`：

- 使用标准库 JSON 校验核心字段。
- 解析 unified diff，记录 RIGHT/LEFT 可评论行。
- 输出 `allowed` / `blocked` decision。
- 使用 denylist 拒绝 final approval / merge authority wording。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | schema/core field validation | valid fixture test |
| P2 | diff parser | invalid line test |
| P3 | severity validation | invalid severity fixture |
| P4 | authority wording guard | unit test body/comment text |
| P5 | spec alignment | spec drift fixture test |

## 数据流

review JSON + unified diff patch -> validator -> decision JSON -> CI/agent report.

## 备选方案

- 依赖 GitHub API 校验 inline comments：拒绝，因为本地 dry-run 必须可复现。

## 风险

- Security: 不执行 diff 内容。
- Compatibility: unified diff parser 保守，复杂 rename 可后续扩展。
- Performance: fixture-scale diff parsing 成本低。
- Maintenance: wording guard 应窄，避免误杀普通 review text。

## 测试计划

- [ ] Unit tests: diff parser、schema field、wording guard。
- [ ] CLI tests: valid/invalid fixtures。
- [ ] Manual verification: `python3 checks/review_json_gate.py --repo . --review examples/fixtures/review-valid.json --diff examples/fixtures/pr-diff.patch --json`

## 回滚方案

移除 review gate/schema/fixtures/tests；现有 PR gate 不受影响。
