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

1. 增加 `tests/runtime_ledger_test_support.py` 作为非 `test_` 命名的共享 helper，
   集中保留 `ROOT`、checks import bootstrap、`clean_checkpoint()`、
   `full_queue_checkpoint()`、fixture JSON loader 与 schema enum walker。测试数据只保留
   一份；helper 不包含可被 pytest 收集的 `test_*` 函数。
2. 保留 `tests/test_runtime_ledger_gate.py` 作为 core 模块，覆盖 schema/state、
   基础 checkpoint、敏感 PR-gate evidence、top-level validation 与 CLI contract。
3. 新建具名测试模块承载 full-queue、budget/tranche 测试；这些测试共享同一 helper，
   保持函数名、参数化装饰器、输入 mutation 与断言逐项等价。
4. 新建具名测试模块承载 review source、self-review authorization 与 lane-failure
   recovery 测试；同样保持函数名与断言语义不变。
5. implementation 分支创建后立即记录 `impl_base_sha=$(git rev-parse HEAD)`；在
   编辑前保存 runtime ledger 与全库的 fresh collection 基线。若 runtime ledger
   基线不再是 66 functions / 73 cases，先停止并更新 spec。
6. 编辑后把 runtime node IDs 去除模块路径前缀、排序并与基线逐项 diff；同时从
   `git show "$impl_base_sha":tests/test_runtime_ledger_gate.py` 解析基线 AST，按测试
   函数名比较 `ast.dump(include_attributes=False)`，确保 decorators、参数值、函数体
   与断言完全一致。最后要求全库 collected count 与实际基线相等并运行全量测试。

不使用复制 helper、动态生成测试、批量改写断言或 pytest skip/xfail 来达到行数目标。

## Deterministic Parity Procedure

以下命令由 implementation owner 在同一个干净 worktree 中按顺序执行。步骤 1-2
必须发生在任何测试文件编辑之前；`/tmp` 证据同时摘要到 implementation PR，且不提交。

1. 记录实际 implementation base：

   ```sh
   git rev-parse HEAD > /tmp/gh108-impl-base-sha.txt
   ```

2. 保存编辑前的 normalized runtime nodes 与全库 collected count：

   ```sh
   /usr/bin/python3 -m pytest --collect-only -q tests/test_runtime_ledger_gate.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort \
     > /tmp/gh108-before-runtime-nodes.txt
   /usr/bin/python3 -m pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' \
     > /tmp/gh108-before-all-count.txt
   ```

3. 拆分后保存同形证据并逐项比较：

   ```sh
   /usr/bin/python3 -m pytest --collect-only -q tests/test_runtime_ledger*.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort \
     > /tmp/gh108-after-runtime-nodes.txt
   /usr/bin/python3 -m pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' \
     > /tmp/gh108-after-all-count.txt
   diff -u /tmp/gh108-before-runtime-nodes.txt /tmp/gh108-after-runtime-nodes.txt
   diff -u /tmp/gh108-before-all-count.txt /tmp/gh108-after-all-count.txt
   ```

4. 比较每个测试函数的完整 AST（decorators 与函数体均包含；重复函数名也阻断）：

   ```sh
   impl_base_sha=$(cat /tmp/gh108-impl-base-sha.txt)
   /usr/bin/python3 - "$impl_base_sha" <<'PY'
   import ast
   import glob
   import subprocess
   import sys

   def test_map(trees):
       result = {}
       for tree in trees:
           for node in tree.body:
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                   assert node.name not in result, f"duplicate test function: {node.name}"
                   result[node.name] = ast.dump(node, include_attributes=False)
       return result

   baseline = subprocess.check_output(
       ["git", "show", f"{sys.argv[1]}:tests/test_runtime_ledger_gate.py"],
       text=True,
   )
   current_paths = sorted(glob.glob("tests/test_runtime_ledger*.py"))
   before = test_map([ast.parse(baseline)])
   after = test_map(
       [ast.parse(open(path, encoding="utf-8").read()) for path in current_paths]
   )
   assert before == after, "runtime ledger test FunctionDef AST mapping changed"
   print(f"AST parity passed: {len(after)} test functions")
   PY
   ```

5. 用同一 SHA 审计 committed scope：

   ```sh
   impl_base_sha=$(cat /tmp/gh108-impl-base-sha.txt)
   git diff --name-only "$impl_base_sha"...HEAD
   git diff --exit-code "$impl_base_sha"...HEAD -- \
     checks schemas examples/fixtures .github/workflows specs
   ```

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | runtime ledger 各测试模块 | 编辑前后保存 `pytest --collect-only -q` 输出，去除首个 `::` 前的模块路径后排序，`diff -u /tmp/gh108-before-runtime-nodes.txt /tmp/gh108-after-runtime-nodes.txt` 必须为空；实际基线偏离 66 functions / 73 cases 时先更新 spec |
| B-002 | runtime ledger shared helper 与拆分模块 | `wc -l tests/test_runtime_ledger*.py`；每个文件严格小于 800 行，并人工确认 helper 只有一个定义来源 |
| B-003 | implementation diff scope | `git diff --name-only "$impl_base_sha"...HEAD` 仅包含 `tests/` 下批准的 runtime ledger 文件；`git diff --exit-code "$impl_base_sha"...HEAD -- checks schemas examples/fixtures .github/workflows specs` 必须为空 |
| B-004 | 所有迁移后的测试函数 | 执行 Deterministic Parity Procedure 步骤 4；`ast.parse` + `ast.dump(include_attributes=False)` mapping 必须完全相等 |
| B-005 | repository validation | 编辑前后全库 `pytest --collect-only` 总数相等；`/usr/bin/python3 -m pytest -q tests/test_runtime_ledger*.py`、`/usr/bin/python3 -m pytest -q`、`python3 checks/check_workflow.py --repo . --all-specs`、`git diff --check` 全部通过 |

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

- Security: 不改变生产或安全 gate；主要风险是漏迁移或替换负例，使用 normalized
  node multiset 与逐函数 AST equality 双重阻断。
- Compatibility: pytest 模块路径会变化，但测试函数与生产 API 不变；仓库没有声明
  外部消费者依赖测试 node ID 全路径。
- Performance: 模块导入略有变化；全量测试时间不应显著回归，不设未经基准支持的
  性能承诺。
- Maintenance: helper import 若设计不当可能形成收集歧义；使用非 `test_` 文件名并以
  fresh `--collect-only` 验证。

## 测试计划

- [ ] Unit tests: runtime ledger normalized node multiset 与逐函数 AST 相对
  `impl_base_sha` 完全相等，focused suite 全部通过。
- [ ] Integration tests: 全量 collected count 与实际 implementation base 相等，
  全量 pytest 与 workflow validation 全部通过。
- [ ] Manual verification: 核对 `impl_base_sha` 记录、文件行数和 committed diff 路径。

## 回滚方案

implementation 采用独立 commit；若收集集合、断言或全量测试不一致，直接回滚该
test-only commit，恢复单文件基线，不需要数据迁移或功能开关。
