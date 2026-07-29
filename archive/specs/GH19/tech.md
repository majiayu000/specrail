# Tech Spec

## Linked Issue

GitHub issue: `#19`

## Product Spec

`specs/GH19/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Skill entrypoint | `skills/specrail-workflow/SKILL.md` | 单个 skill 覆盖所有 routes。 | 需要变为 router。 |
| Validation | `checks/check_workflow.py`, `checks/specrail_lib.py` | 不校验 skill lock。 | 需要 deterministic lock validation。 |
| Distribution | `skills/` | 只有一个 repo skill。 | 需要 focused skill set。 |

## 设计方案

新增 focused skills 和 `skills-lock.json`。在 `specrail_lib.py` 中新增 skill frontmatter/hash validation helper，`check_workflow.py` 调用该 helper。

`computedHash` 使用每个 `SKILL.md` UTF-8 bytes 的 sha256 hex。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `specrail-workflow` router | grep + check_workflow |
| P2 | focused skill files | skill lock validation |
| P3 | `skills-lock.json` | hash validation test |
| P4 | check workflow | `python3 checks/check_workflow.py --repo .` |

## 数据流

`skills-lock.json` -> validator -> each `skillPath` -> frontmatter + sha256 check.

## 备选方案

- 不加 lockfile，仅文档列出 skills：拒绝，无法审计版本。

## 风险

- Security: 不执行 skill 内容。
- Compatibility: 保留原入口 skill。
- Performance: 读取少量 `SKILL.md` 文件。
- Maintenance: 每次改 skill 需更新 hash。

## 测试计划

- [ ] Unit tests: lock hash mismatch / missing skill。
- [ ] Integration: `python3 checks/check_workflow.py --repo .`。

## 回滚方案

删除 focused skills、lockfile 和 validation helper；恢复 router skill。
