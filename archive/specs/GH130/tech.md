# Tech Spec

## Linked Issue

GH-130

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| CLI 入口 | `tools/spec_depth_audit.py:166` | `main()` 解析 `--repo`/`--spec-dir`，打印表格与汇总后正常返回 | `--gate` 及阈值参数在此新增；阻断经 `SystemExit(1)` |
| 单 spec 审计 | `tools/spec_depth_audit.py:140` | `audit_dir()` 返回 8 元组，仅含展示字段 | 需要携带 trivial 标记与数值指标供 gate 判定 |
| 小节提取 | `tools/spec_depth_audit.py:59` | `section()` 按标题词提取小节正文 | 复用它限定 `complexity: trivial` 只在 Linked Issue 小节内生效（B-004/B-005） |
| fail-closed 现状 | `tools/spec_depth_audit.py:174` | 显式目录缺 `product.md` 即 `SystemExit`；无行则 `SystemExit` | B-008 保持不变 |
| 模板指引 | `templates/product_spec.md:19`、`templates/zh-CN/product_spec.md:19` | Behavior Invariants 小节现有写法指引未提条件式触发 | B-007 的替代措施：补 EARS 条件式触发写作指引 |
| 回归测试 | `tests/test_spec_depth_audit.py:1` | 单元 + subprocess CLI 两种风格 | gate 测试沿用 subprocess 风格 |

## Proposed Design

- `audit_dir()` 改为返回记录 dict（label、行数、inv、ears、cov、anchors、cov_names、trivial），打印层从记录构造原 8 列，展示输出不变。
- 新增 `is_trivial(ptext)`：`section(ptext, ["Linked Issue"])` 内按行匹配 `^complexity:\s*trivial$`（大小写不敏感）。
- 新增 `gate_failures(record, thresholds)`：trivial 返回空；否则对 invariants/boundary/anchors 三项逐一比较，返回 `metric=actual < threshold` 描述列表。
- `main()` 新增 `--gate`、`--min-invariants`（默认 8）、`--min-boundary`（默认 8）、`--min-anchors`（默认 5）。`--gate` 时在汇总后输出 gate 段：exempt 列表、逐 spec 失败原因；有失败则 `SystemExit(1)`，否则打印通过行。
- EARS 不进入 `gate_failures`（B-007）。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | `main()` 参数默认值 | `python3 -m pytest -q tests/test_spec_depth_audit.py`（既有非 gate 用例全绿） |
| B-002 | `gate_failures` + `main()` 阻断 | `test_gate_blocks_shallow_spec_with_reasons` |
| B-003 | `main()` gate 通过行 | `test_gate_passes_deep_spec` |
| B-004 | `is_trivial` | `test_gate_exempts_trivial_spec` |
| B-005 | `is_trivial` 小节限定 | `test_trivial_marker_outside_linked_issue_is_not_exempt` |
| B-006 | argparse 阈值 | `test_gate_thresholds_are_configurable` |
| B-007 | `gate_failures` 无 EARS 分支 | `test_gate_ignores_ears_ratio` |
| B-008 | 既有 fail-closed 路径 | `test_mixed_valid_and_invalid_explicit_dirs_fail_closed`（既有） |
| B-009 | 全程无写文件调用 | `test_gate_is_read_only`（审计前后目录快照一致） |
| B-010 | `audit_dir` 缺 tech.md 路径 | `test_gate_counts_missing_tech_as_zero_anchors` |

## Data Flow

输入：spec 目录集合（`--repo` glob 或 `--spec-dir`）→ 逐目录读 `product.md`/`tech.md` → 记录列表 → 打印表格/汇总 →（`--gate` 时）阈值判定 → 退出码。无持久化、无网络调用。

## Alternatives Considered

- 把 gate 写进 `checks/`：被否。GH-130 非目标明确不动 `checks/`；深度门禁的消费面是 spec 写作阶段而非 PR 阶段。
- 用 EARS 占比做阻断项：被否。v3 条件式语义下 GH88/GH91 深 spec 占比 0%，会把已验证的深 spec 判死（B-007）。
- 全库默认 gate：被否。33 份存量 spec 会全量报红，制造回溯税；由调用方显式选集合。
