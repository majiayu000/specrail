# Tech Spec

## Linked Issue

GitHub issue: `#18`

## Product Spec

`specs/GH18/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Product template | `templates/product_spec.md`, `templates/zh-CN/product_spec.md` | 用户可见行为是自由文本。 | 需要升级为 testable invariants。 |
| Tech template | `templates/tech_spec.md`, `templates/zh-CN/tech_spec.md` | 当前系统是自由文本。 | 需要 codebase evidence 和 test mapping。 |
| Validator | `checks/specrail_lib.py` | 检查 template parity 和 stable tokens。 | 模板结构变更必须保持 parity。 |

## 设计方案

直接更新四个模板文件。保持 required tokens `## Goals`、`## Non-Goals`、`## Acceptance Criteria`、`## Proposed Design`、`## Test Plan`、`## Rollback Plan` 以兼容现有 pack validator。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | product templates | `rg "Behavior Invariants" templates/*product_spec.md templates/zh-CN/product_spec.md` |
| P2 | tech templates | `rg "Codebase Context" templates/*tech_spec.md templates/zh-CN/tech_spec.md` |
| P3 | tech templates | `rg "Product-to-Test Mapping" templates/*tech_spec.md templates/zh-CN/tech_spec.md` |

## 数据流

Agent loads template -> writes spec packet -> check_workflow validates packet shape.

## 备选方案

- 新增单独 advanced templates：拒绝，默认模板应体现更强 contract。

## 风险

- Security: 无。
- Compatibility: 保留旧 required headings。
- Performance: 无。
- Maintenance: 中英文模板需要结构同步。

## 测试计划

- [ ] Unit tests: existing template parity validation。
- [ ] Manual verification: `python3 checks/check_workflow.py --repo .`。

## 回滚方案

恢复四个模板内容。
