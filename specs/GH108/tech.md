# Tech Spec

## Linked Issue

GH-108

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 共享 checkpoint 构造 | `tests/test_runtime_ledger_gate.py:30`, `tests/test_runtime_ledger_gate.py:148` | `clean_checkpoint()` 与 `full_queue_checkpoint()` 被多个测试主题复用 | 拆分后需要单一共享来源，不能复制大段 fixture 数据 |
| schema/state 与 core gate 测试 | `tests/test_runtime_ledger_gate.py:193` | 校验共享状态词表、基础 checkpoint、敏感 evidence 与 CLI 合同 | 形成职责稳定的 core 测试模块 |
| full-queue 测试 | `tests/test_runtime_ledger_gate.py:664` | 校验 spec coverage、remaining queue 与完成态 | 可独立为 queue/budget 主题模块 |
| review/lane failure 测试 | `tests/test_runtime_ledger_gate.py:788` | 校验 review source、self-review 授权与 lane failure 恢复 | 可独立为 review 主题模块 |
| budget/tranche 测试 | `tests/test_runtime_ledger_gate.py:889` | 校验 compaction budget、item cap、spec-only streak 与 tranche mix | 与 full-queue 生命周期同属长队列运行主题 |
| production evaluator | `checks/runtime_ledger_gate.py:387` | `evaluate_checkpoint()` 是上述测试共同调用的生产入口 | 本项只重组调用方，禁止修改该入口 |
| tranche rules | `checks/runtime_gate_rules.py:280` | `_validate_tranche_mix()` 承载后段测试的生产规则 | 作为不改动的生产边界 |
| CI test command | `.github/workflows/workflow-check.yml:32` | CI 执行 `python3 -m pytest -q` | 拆分后不得改变 CI 发现方式或命令 |

## 设计方案

1. 在 `tests/` 下增加一个非 `test_` 命名的 runtime ledger 共享 helper 模块，
   集中保留 `ROOT`、checks import bootstrap、`clean_checkpoint()`、
   `full_queue_checkpoint()`、fixture JSON loader 与 schema enum walker。测试数据只保留
   一份；helper 不包含可被 pytest 收集的 `test_*` 函数。
2. 保留 `tests/test_runtime_ledger_gate.py` 作为 core 模块，覆盖 schema/state、
   基础 checkpoint、敏感 PR-gate evidence、top-level validation 与 CLI contract。
3. 新建具名测试模块承载 full-queue、budget/tranche 测试；这些测试共享同一 helper，
   保持函数名、参数化装饰器、输入 mutation 与断言逐项等价。
4. 新建具名测试模块承载 review source、self-review authorization 与 lane-failure
   recovery 测试；同样保持函数名与断言语义不变。
5. implementation 前后分别收集测试函数名和 pytest node IDs：函数名集合必须
   完全一致，收集数必须保持 73；随后运行 focused 与全量测试。

不使用复制 helper、动态生成测试、批量改写断言或 pytest skip/xfail 来达到行数目标。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | runtime ledger 各测试模块 | 对比 `f3251fe:tests/test_runtime_ledger_gate.py` 与工作树的 `test_*` 函数名集合；`/usr/bin/python3 -m pytest --collect-only -q tests/test_runtime_ledger*.py` 显示 73 collected |
| B-002 | runtime ledger shared helper 与拆分模块 | `wc -l tests/test_runtime_ledger*.py`；每个文件严格小于 800 行，并人工确认 helper 只有一个定义来源 |
| B-003 | implementation diff scope | `git diff --name-only f3251fe...HEAD` 仅包含 GH108 spec 与 `tests/` 下 runtime ledger 相关文件；`git diff -- checks schemas examples/fixtures .github/workflows` 为空 |
| B-004 | 所有迁移后的测试函数 | 人工逐块 diff 确认断言/参数等价；focused pytest 全通过且没有新增 `skip` / `xfail` |
| B-005 | repository validation | `/usr/bin/python3 -m pytest -q tests/test_runtime_ledger*.py`、`/usr/bin/python3 -m pytest -q`、`python3 checks/check_workflow.py --repo . --all-specs`、`git diff --check` 全部通过 |

## 数据流

pytest 收集各 `test_runtime_ledger*.py` 模块；测试从唯一共享 helper 构造 checkpoint
或读取既有 fixture，再调用未修改的 `evaluate_checkpoint()`，最后执行原有断言。
不新增持久化、网络调用或生产运行时数据流。

## 备选方案

- 只把 1063 行文件机械切成两个文件但复制 `clean_checkpoint()`：拒绝，因为会制造
  重复测试数据和后续漂移。
- 仅豁免测试文件的 800 行规则：拒绝，因为隐藏了已确认的维护性问题。
- 同时拆分生产 evaluator：拒绝，超出 GH108 的 test-only 范围并提高回归风险。

## 风险

- Security: 不改变生产或安全 gate；主要风险是漏迁移负例，使用函数集合与 collected
  case 对比阻断。
- Compatibility: pytest 模块路径会变化，但测试函数与生产 API 不变；仓库没有声明
  外部消费者依赖测试 node ID 全路径。
- Performance: 模块导入略有变化；全量测试时间不应显著回归，不设未经基准支持的
  性能承诺。
- Maintenance: helper import 若设计不当可能形成收集歧义；使用非 `test_` 文件名并以
  fresh `--collect-only` 验证。

## 测试计划

- [ ] Unit tests: runtime ledger focused suite 收集 73 cases 并全部通过。
- [ ] Integration tests: 全量 421+ tests 与 workflow validation 全部通过。
- [ ] Manual verification: 对比函数名集合、assert/parametrize diff、文件行数和改动路径。

## 回滚方案

implementation 采用独立 commit；若收集集合、断言或全量测试不一致，直接回滚该
test-only commit，恢复单文件基线，不需要数据迁移或功能开关。
