# Tech Spec

## Linked Issue

GH-93

## Product Spec

`specs/GH93/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 深度指标定义 | `tools/spec_depth_audit.py:32`、`:33`、`:45`、`:81`、`:132` | 编号 invariant / 条件式 EARS / 当前模板 10 类边界 verdict / 锚点判定 | 与 GH86 写作方法的四项指标一一对应 |
| 目录选择 | `tools/spec_depth_audit.py:166`、`:173`、`:178` | 默认 glob `specs/GH*/`,`--spec-dir` 覆盖；重复 basename 使用 resolved path | B-002 的落点 |
| 空结果保护 | `tools/spec_depth_audit.py:174`、`:184` | 显式目录缺 `product.md` 或最终无结果时 `SystemExit` 非零退出 | B-003 的落点 |
| 既有工具目录 | `tools/install_codex_skills.py:1` | 已有的仓库级开发工具 | 新脚本放同一目录,遵循既有布局 |

## Proposed Design

单文件只读脚本:正则启发式统计每份 spec 的 invariant 数、条件式 EARS 占比、当前模板边界 verdict 覆盖、tech.md path:line 锚点数,打印 `metric_semantics=v3`、明细表与汇总。v3 补充代码格式或常见 extensionless 文件锚点；docstring 记录在 GH86 基线提交 `ac66dbb` 上重算的 v3 数字，旧 v1 基线与 A/B 数字仅保留作来源记录，不跨版本直接比较。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 全文件仅 `read_text`,无任何写调用(`tools/spec_depth_audit.py:145`、`:146`) | `python3 tools/spec_depth_audit.py && git status --porcelain` 输出不含意外改动 |
| B-002 | `tools/spec_depth_audit.py:166`、`:173`、`:178` | `python3 tools/spec_depth_audit.py --spec-dir /tmp/<任意含 product.md 的目录>` 仅输出该目录 |
| B-003 | `tools/spec_depth_audit.py:174`、`:184` | `python3 tools/spec_depth_audit.py --spec-dir /tmp/empty; echo $?` 非零 |

## Data Flow

输入:spec 目录下的 markdown 文件;输出:stdout 表格;无持久化、无网络、无外部调用。

## Alternatives Considered

- 接入 `check_workflow.py` 作为软告警:被否,深度门禁属 Phase 2,先以独立工具沉淀基线。
- 用 LLM 评审代替正则:成本高且不可复现,回归对比需要确定性。

## Risks

- Security: 无(只读本地文件)。
- Compatibility: 无(纯新增)。
- Performance: 30 份 spec 毫秒级。
- Maintenance: 指标是启发式；语义变更必须提升 `metric_semantics` 并重算带 commit 的基线。

## Test Plan

- [ ] Unit tests: `python3 -m pytest -q tests/test_spec_depth_audit.py` 覆盖条件式 EARS、边界 verdict、extensionless path:line 锚点与同名外部目录标签。
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`、`python3 -m pytest -q` 全绿。
- [ ] Manual verification: 按 Product-to-Test Mapping 三条命令逐一执行。

## Rollback Plan

回滚整个 GH93 PR：删除 `tools/spec_depth_audit.py`、`tests/test_spec_depth_audit.py` 与 `specs/GH93/`，并删除 `CHANGELOG.md` 中对应条目；不得只删脚本而留下测试导入。
