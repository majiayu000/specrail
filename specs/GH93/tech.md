# Tech Spec

## Linked Issue

GH-93

## Product Spec

`specs/GH93/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 深度指标定义 | `tools/spec_depth_audit.py:21` (`INVARIANT_RE`)、`:22` (`EARS_RE`)、`:30-41` (`BOUNDARY_CATEGORIES`) | 编号 invariant / EARS 条件式 / 10 类边界的正则启发式 | 与 GH86 写作方法的四项指标一一对应 |
| 目录选择 | `tools/spec_depth_audit.py:104` | 默认 glob `specs/GH*/`,`--spec-dir` 覆盖 | B-002 的落点 |
| 空结果保护 | `tools/spec_depth_audit.py:105-107` | 无有效目录时 `SystemExit` 非零退出 | B-003 的落点 |
| 既有工具目录 | `tools/install_codex_skills.py:1` | 已有的仓库级开发工具 | 新脚本放同一目录,遵循既有布局 |

## Proposed Design

单文件只读脚本(约 140 行):正则启发式统计每份 spec 的 invariant 数、EARS 占比、边界类覆盖、tech.md path:line 锚点数,打印明细表与汇总。docstring 记录 2026-07-13 基线数字,供未来回归对比。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 全文件仅 `read_text`,无任何写调用(`tools/spec_depth_audit.py:76-77`) | `python3 tools/spec_depth_audit.py && git status --porcelain` 输出不含意外改动 |
| B-002 | `tools/spec_depth_audit.py:104` | `python3 tools/spec_depth_audit.py --spec-dir /tmp/<任意含 product.md 的目录>` 仅输出该目录 |
| B-003 | `tools/spec_depth_audit.py:105-107` | `python3 tools/spec_depth_audit.py --spec-dir /tmp/empty; echo $?` 非零 |

## Data Flow

输入:spec 目录下的 markdown 文件;输出:stdout 表格;无持久化、无网络、无外部调用。

## Alternatives Considered

- 接入 `check_workflow.py` 作为软告警:被否,深度门禁属 Phase 2,先以独立工具沉淀基线。
- 用 LLM 评审代替正则:成本高且不可复现,回归对比需要确定性。

## Risks

- Security: 无(只读本地文件)。
- Compatibility: 无(纯新增)。
- Performance: 30 份 spec 毫秒级。
- Maintenance: 正则启发式对英文 EARS 措辞低估(已在 product.md 非目标中声明)。

## Test Plan

- [ ] Unit tests: 不新增(trivial 只读工具,验证靠下述命令)。
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`、`python3 -m pytest -q` 全绿。
- [ ] Manual verification: 按 Product-to-Test Mapping 三条命令逐一执行。

## Rollback Plan

删除 `tools/spec_depth_audit.py` 与 `specs/GH93/` 即完全回滚,无其他文件依赖。
