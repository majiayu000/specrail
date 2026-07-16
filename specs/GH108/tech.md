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
3. 新建 `tests/test_runtime_ledger_queue.py` 承载 full-queue、budget/tranche 测试；
   这些测试共享同一 helper，保持函数名、参数化装饰器、输入 mutation 与断言等价。
4. 新建 `tests/test_runtime_ledger_review.py` 承载 review source、self-review
   authorization 与 lane-failure recovery 测试；同样保持函数名与断言语义不变。
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

1. 记录实际 implementation base 与本次验证唯一使用的 Python。默认跟随仓库/CI
   的 `python3`；本地环境需要覆盖时显式设置 `PYTHON_BIN`，但编辑前后不得切换：

   ```sh
   git rev-parse HEAD > /tmp/gh108-impl-base-sha.txt
   python_bin=${PYTHON_BIN:-python3}
   command -v "$python_bin" > /tmp/gh108-python-bin.txt
   python_bin=$(cat /tmp/gh108-python-bin.txt)
   "$python_bin" -m pytest --version
   ```

2. 保存编辑前的 normalized runtime nodes 与全库 collected count：

   ```sh
   python_bin=$(cat /tmp/gh108-python-bin.txt)
   "$python_bin" -m pytest --collect-only -q tests/test_runtime_ledger_gate.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort \
     > /tmp/gh108-before-runtime-nodes.txt
   "$python_bin" -m pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' \
     > /tmp/gh108-before-all-count.txt
   test "$(rg -c '^def test_' tests/test_runtime_ledger_gate.py)" -eq 66
   test "$(wc -l < /tmp/gh108-before-runtime-nodes.txt | tr -d ' ')" -eq 73
   ```

3. 拆分后保存同形证据并逐项比较：

   ```sh
   python_bin=$(cat /tmp/gh108-python-bin.txt)
   "$python_bin" -m pytest --collect-only -q tests/test_runtime_ledger*.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort \
     > /tmp/gh108-after-runtime-nodes.txt
   "$python_bin" -m pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' \
     > /tmp/gh108-after-all-count.txt
   diff -u /tmp/gh108-before-runtime-nodes.txt /tmp/gh108-after-runtime-nodes.txt
   diff -u /tmp/gh108-before-all-count.txt /tmp/gh108-after-all-count.txt
   ```

4. 比较全部顶层函数的完整 AST（66 tests + 4 helpers；decorators 与函数体均
   包含；重复函数名也阻断），并拒绝任何 skip/xfail 标记：

   ```sh
   impl_base_sha=$(cat /tmp/gh108-impl-base-sha.txt)
   python_bin=$(cat /tmp/gh108-python-bin.txt)
   "$python_bin" - "$impl_base_sha" <<'PY'
   import ast
   import subprocess
   import sys

   def function_map(trees):
       result = {}
       for tree in trees:
           for node in ast.walk(tree):
               if isinstance(node, ast.Call):
                   func = node.func
                   if isinstance(func, ast.Attribute) and func.attr in {"skip", "xfail"}:
                       raise AssertionError(f"forbidden skip/xfail call: {ast.dump(node)}")
           for node in tree.body:
               targets = []
               if isinstance(node, ast.Assign):
                   targets = node.targets
               elif isinstance(node, ast.AnnAssign):
                   targets = [node.target]
               if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets):
                   raise AssertionError("module-level pytestmark is forbidden")
           for node in tree.body:
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                   assert node.name not in result, f"duplicate function: {node.name}"
                   result[node.name] = ast.dump(node, include_attributes=False)
       return result

   baseline = subprocess.check_output(
       ["git", "show", f"{sys.argv[1]}:tests/test_runtime_ledger_gate.py"],
       text=True,
   )
   current_paths = [
       "tests/test_runtime_ledger_gate.py",
       "tests/test_runtime_ledger_queue.py",
       "tests/test_runtime_ledger_review.py",
       "tests/runtime_ledger_test_support.py",
   ]
   current_trees = {
       path: ast.parse(open(path, encoding="utf-8").read())
       for path in current_paths
   }
   support_tests = [
       node.name
       for node in current_trees["tests/runtime_ledger_test_support.py"].body
       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
       and node.name.startswith("test_")
   ]
   assert not support_tests, f"support module owns test functions: {support_tests}"
   before = function_map([ast.parse(baseline)])
   after = function_map(list(current_trees.values()))
   assert before == after, "runtime ledger top-level FunctionDef AST mapping changed"
   print(f"AST parity passed: {len(after)} top-level functions")
   PY
   ```

5. 导入拆分后的模块，验证测试全局名称仍绑定到真实 production symbols，而不是
   support wrapper、lambda 或替代常量：

   ```sh
   python_bin=$(cat /tmp/gh108-python-bin.txt)
   "$python_bin" - <<'PY'
   import importlib
   import sys
   from pathlib import Path

   root = Path.cwd().resolve()
   sys.path.insert(0, str(root / "tests"))
   sys.path.insert(0, str(root / "checks"))
   gate = importlib.import_module("runtime_ledger_gate")
   library = importlib.import_module("specrail_lib")
   test_modules = [
       importlib.import_module("test_runtime_ledger_gate"),
       importlib.import_module("test_runtime_ledger_queue"),
       importlib.import_module("test_runtime_ledger_review"),
   ]
   support = importlib.import_module("runtime_ledger_test_support")

   for module in test_modules:
       assert module.evaluate_checkpoint is gate.evaluate_checkpoint
   for name in (
       "CHECKPOINT_STATUSES",
       "FULL_QUEUE_NON_DRAINED_STATES",
       "FULL_QUEUE_TERMINAL_REMAINDER_STATES",
       "MERGE_READY_STATES",
   ):
       owners = [module for module in test_modules if hasattr(module, name)]
       assert owners, f"production symbol is no longer bound: {name}"
       assert all(getattr(module, name) is getattr(gate, name) for module in owners)
   for name in ("RUNTIME_ONLY_STATE", "RUNTIME_STATE_MAPPING", "SPEC_STATUSES", "load_yaml_file"):
       owners = [module for module in test_modules if hasattr(module, name)]
       assert owners, f"specrail_lib symbol is no longer bound: {name}"
       assert all(getattr(module, name) is getattr(library, name) for module in owners)
   for module in [*test_modules, support]:
       assert module.ROOT == root
   print("production symbol identity passed")
   PY
   ```

6. 用同一 SHA 和精确 allowlist 审计 committed scope；只打印路径不算通过：

   ```sh
   set -eu
   impl_base_sha=$(cat /tmp/gh108-impl-base-sha.txt)
   git diff --name-only "$impl_base_sha"...HEAD | LC_ALL=C sort \
     > /tmp/gh108-changed-paths.txt
   printf '%s\n' \
     tests/runtime_ledger_test_support.py \
     tests/test_runtime_ledger_gate.py \
     tests/test_runtime_ledger_queue.py \
     tests/test_runtime_ledger_review.py \
     | LC_ALL=C sort > /tmp/gh108-allowed-paths.txt
   while IFS= read -r path; do
     lines=$(wc -l < "$path" | tr -d ' ')
     if [ "$lines" -ge 800 ]; then
       printf '%s has %s lines; expected < 800\n' "$path" "$lines" >&2
       exit 1
     fi
   done < /tmp/gh108-allowed-paths.txt
   comm -23 /tmp/gh108-changed-paths.txt /tmp/gh108-allowed-paths.txt \
     > /tmp/gh108-unexpected-paths.txt
   if [ -s /tmp/gh108-unexpected-paths.txt ]; then
     cat /tmp/gh108-unexpected-paths.txt >&2
     exit 1
   fi
   git diff --exit-code "$impl_base_sha"...HEAD -- \
     checks schemas examples/fixtures .github/workflows specs
   ```

7. focused run 必须实际执行全部 73 cases，不得出现 skipped/xfailed/xpassed：

   ```sh
   set -eu
   python_bin=$(cat /tmp/gh108-python-bin.txt)
   if ! "$python_bin" -m pytest -q -r a tests/test_runtime_ledger*.py \
     > /tmp/gh108-focused-pytest.txt 2>&1; then
     tail -n 20 /tmp/gh108-focused-pytest.txt
     exit 1
   fi
   tail -n 20 /tmp/gh108-focused-pytest.txt
   if rg -n '(^|, )[1-9][0-9]* (skipped|xfailed|xpassed)' \
     /tmp/gh108-focused-pytest.txt; then
     exit 1
   fi
   ```

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | runtime ledger 各测试模块 | 编辑前后保存 `pytest --collect-only -q` 输出，去除首个 `::` 前的模块路径后排序，`diff -u /tmp/gh108-before-runtime-nodes.txt /tmp/gh108-after-runtime-nodes.txt` 必须为空；实际基线偏离 66 functions / 73 cases 时先更新 spec |
| B-002 | runtime ledger shared helper 与拆分模块 | 执行 Deterministic Parity Procedure 步骤 6 的逐文件行数 gate；任一文件达到 800 行即非零退出，并人工确认 helper 只有一个定义来源 |
| B-003 | implementation diff scope | 执行 Deterministic Parity Procedure 步骤 6；changed paths 减去四文件 allowlist 后必须为空，protected paths committed diff 也必须为空 |
| B-004 | 所有迁移后的测试与 helper 函数及其 production bindings | 执行 Deterministic Parity Procedure 步骤 4、5、7；70 个顶层函数 AST mapping 与 production symbol identity 必须相等，且无 skip/xfail |
| B-005 | repository validation | 编辑前后使用 `/tmp/gh108-python-bin.txt` 中同一解释器；全库 `pytest --collect-only` 总数相等；focused/full pytest、`python3 checks/check_workflow.py --repo . --all-specs`、`git diff --check` 全部通过 |

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
  外部消费者依赖测试 node ID 全路径。验证默认使用 PATH `python3`，仅允许通过
  显式 `PYTHON_BIN` 选择一次本地解释器并在整个 parity 流程复用。
- Performance: 模块导入略有变化；全量测试时间不应显著回归，不设未经基准支持的
  性能承诺。
- Maintenance: helper import 若设计不当可能形成收集歧义；使用固定非 `test_` 文件名、
  精确四文件 allowlist 与 fresh `--collect-only` 验证。

## 测试计划

- [ ] Unit tests: runtime ledger normalized node multiset 与逐函数 AST 相对
  `impl_base_sha` 完全相等，focused suite 全部通过。
- [ ] Integration tests: 全量 collected count 与实际 implementation base 相等，
  全量 pytest 与 workflow validation 全部通过。
- [ ] Manual verification: 核对 `impl_base_sha` 记录、文件行数和 committed diff 路径。

## 回滚方案

implementation 采用独立 commit；若收集集合、断言或全量测试不一致，直接回滚该
test-only commit，恢复单文件基线，不需要数据迁移或功能开关。
