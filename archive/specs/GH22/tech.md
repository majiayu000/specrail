# Tech Spec

## Linked Issue

GitHub issue: `#22`

## Product Spec

`specs/GH22/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Pack validator | `checks/check_workflow.py` | 只校验 base pack，并按重复的 `--spec-dir` 参数校验指定 packets。 | 需要新增 all-specs discovery，复用现有 packet validator。 |
| CI workflow | `.github/workflows/workflow-check.yml` | 硬编码 GH5/GH7/GH9/GH13。 | 新增 GH16-GH20 和未来 packets 时会漏检。 |
| Tests | `tests/test_evaluate.py` | 已覆盖 task/spec helper 和 CLI contracts。 | 适合补 discovery/unit coverage。 |

## 设计方案

在 `checks/check_workflow.py` 中新增 `discover_spec_dirs(repo)`：

- 扫描 `repo/specs`。
- 只返回目录名匹配 `GH[0-9]+` 的路径。
- 按数字 issue number 排序，保证输出稳定。

CLI 增加 `--all-specs`。主流程把显式 `--spec-dir` 和 discovered dirs 合并去重后调用
`validate_spec_packet()`。CI 改为：

```sh
python3 checks/check_workflow.py --repo . --all-specs
```

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `discover_spec_dirs` | Unit test with matching and non-matching dirs |
| P2 | CLI aggregation | CLI test on repo root with `--all-specs` |
| P3 | Workflow command | Static inspection plus CI workflow diff |
| P4 | Empty specs behavior | Unit test on tmp repo without `specs` |
| P5 | Compatibility | Existing `--spec-dir` tests still pass |

## 数据流

repo path -> `specs/` directory listing -> deterministic packet list -> `validate_spec_packet`.

## 备选方案

- 在 workflow 中写 shell loop：拒绝，因为 discovery 逻辑会分散在 CI 而不是 validator。

## 风险

- Security: 只读取 repo-local paths，不执行 packet 内容。
- Compatibility: `--spec-dir` 保持原有行为。
- Performance: packet 数量小，目录扫描成本低。
- Maintenance: numeric sort 避免 GH10 排在 GH2 前。

## 测试计划

- [ ] Unit tests: `discover_spec_dirs` matching、sorting、empty specs。
- [ ] CLI tests: `python3 checks/check_workflow.py --repo . --all-specs`。
- [ ] Manual verification: `python3 checks/check_workflow.py --repo . --all-specs`。

## 回滚方案

恢复 CI hardcoded list 并移除 `--all-specs`；base pack validation 不受影响。
