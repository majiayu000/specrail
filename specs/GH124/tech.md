# Tech Spec

## Linked Issue

GH-124

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":124,"complete":true,"paths":["tests/check_workflow_test_support.py","tests/test_check_workflow.py","tests/test_check_workflow_paths.py"],"spec_refs":["specs/GH124/product.md","specs/GH124/tech.md"]}
-->

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| bootstrap/helper | `tests/test_check_workflow.py:11`, `tests/test_check_workflow.py:225` | `ROOT`/checks import bootstrap 与 3 个 config helper 为全部主题共享 | 拆分后必须维持单一来源和原始函数语义 |
| assets/config/policy | `tests/test_check_workflow.py:35`, `tests/test_check_workflow.py:854` | required files、pack assets、enforcement、impl branch 与 auth mode 测试 | 保留在原模块，维持历史 focused path 的核心覆盖 |
| spec/path trust | `tests/test_check_workflow.py:259` | spec packet template、symlink identity、discovery 与 CLI root 测试 | 形成独立且内聚的 path/security 主题模块 |
| production validators | `checks/check_workflow.py`, `checks/specrail_lib.py` | 提供真实 workflow、spec packet 与 path validator | 本项禁止修改，只验证测试仍绑定真实对象 |

## 设计方案

1. 新增 `tests/check_workflow_test_support.py`，集中保留 `ROOT`、checks import bootstrap
   与 3 个既有 helper。文件名不以 `test_` 开头，不拥有可收集测试。
2. 保留 `tests/test_check_workflow.py`，承载 required assets、pack validation、enforcement、
   impl branch 与 auth mode policy 测试。
3. 新增 `tests/test_check_workflow_paths.py`，迁移 spec packet artifact、path trust、
   discovery 与 configured-root/CLI 测试。
4. implementation 从当时最新 `origin/main` 创建；编辑前固定 `impl_base_sha`、唯一
   Python/pytest 入口、72-case normalized node multiset、全库 553-case count、focused
   outcome 与 skip/xfail 基线。
5. 编辑后比较 normalized nodes、57 个顶层函数完整 AST、production symbol identity、
   15 个既有 skip/xfail 调用、focused outcome、精确三路径 allowlist和逐文件行数；
   任一差异都阻断交付。

不复制 helper、不动态生成测试、不使用 collection hook，也不改写测试函数体来满足
行数目标。

## Deterministic Parity Procedure

implementation owner 在同一干净 worktree 中按顺序执行；步骤 1-2 必须发生在任何编辑前。

1. 记录实际 base，创建固定 `Python 3.13.11` + `pytest==9.1.1` 的临时环境，并在
   后续步骤中只复用该环境的同一个 Python 解释器：

   ```bash
   set -euo pipefail
   git rev-parse HEAD > /tmp/gh124-impl-base-sha.txt
   command -v uv > /tmp/gh124-uv-bin.txt
   uv_bin=$(cat /tmp/gh124-uv-bin.txt)
   "$uv_bin" venv --clear --python '3.13.11' /tmp/gh124-pytest-env
   "$uv_bin" pip install --python /tmp/gh124-pytest-env/bin/python 'pytest==9.1.1'
   printf '%s\n' /tmp/gh124-pytest-env/bin/python > /tmp/gh124-python-bin.txt
   python_bin=$(cat /tmp/gh124-python-bin.txt)
   "$python_bin" -m pytest --version
   ```

2. 保存编辑前 normalized nodes、全库 count 与 focused outcome counts：

   ```bash
   set -euo pipefail
   python_bin=$(cat /tmp/gh124-python-bin.txt)
   if ! "$python_bin" -m pytest --collect-only -q tests/test_check_workflow.py \
     > /tmp/gh124-before-focused-collect.txt 2>&1; then
     tail -n 20 /tmp/gh124-before-focused-collect.txt
     exit 1
   fi
   sed -n '/::/s/^[^:]*:://p' /tmp/gh124-before-focused-collect.txt \
     | LC_ALL=C sort > /tmp/gh124-before-nodes.txt
   if ! "$python_bin" -m pytest --collect-only -q \
     > /tmp/gh124-before-all-collect.txt 2>&1; then
     tail -n 20 /tmp/gh124-before-all-collect.txt
     exit 1
   fi
   awk '/::/{count++} END{print count+0}' /tmp/gh124-before-all-collect.txt \
     > /tmp/gh124-before-all-count.txt
   test "$(rg -c '^def test_' tests/test_check_workflow.py)" -eq 54
   test "$(wc -l < /tmp/gh124-before-nodes.txt | tr -d ' ')" -eq 72
   test "$(cat /tmp/gh124-before-all-count.txt)" -eq 553
   if ! "$python_bin" -m pytest -q -r a tests/test_check_workflow.py \
     > /tmp/gh124-before-focused-pytest.txt 2>&1; then
     tail -n 20 /tmp/gh124-before-focused-pytest.txt
     exit 1
   fi
   rg -o '[0-9]+ (passed|failed|errors?|skipped|xfailed|xpassed)' \
     /tmp/gh124-before-focused-pytest.txt | LC_ALL=C sort \
     > /tmp/gh124-before-focused-outcomes.txt
   test -s /tmp/gh124-before-focused-outcomes.txt
   ```

3. 拆分后保存同形证据并比较：

   ```bash
   set -euo pipefail
   python_bin=$(cat /tmp/gh124-python-bin.txt)
   if ! "$python_bin" -m pytest --collect-only -q tests/test_check_workflow*.py \
     > /tmp/gh124-after-focused-collect.txt 2>&1; then
     tail -n 20 /tmp/gh124-after-focused-collect.txt
     exit 1
   fi
   sed -n '/::/s/^[^:]*:://p' /tmp/gh124-after-focused-collect.txt \
     | LC_ALL=C sort > /tmp/gh124-after-nodes.txt
   if ! "$python_bin" -m pytest --collect-only -q \
     > /tmp/gh124-after-all-collect.txt 2>&1; then
     tail -n 20 /tmp/gh124-after-all-collect.txt
     exit 1
   fi
   awk '/::/{count++} END{print count+0}' /tmp/gh124-after-all-collect.txt \
     > /tmp/gh124-after-all-count.txt
   diff -u /tmp/gh124-before-nodes.txt /tmp/gh124-after-nodes.txt
   diff -u /tmp/gh124-before-all-count.txt /tmp/gh124-after-all-count.txt
   ```

4. 比较全部顶层函数 AST，并拒绝重复函数、support 测试、`pytestmark` 以及
   skip/xfail 调用相对基线的任何增删或变化：

   ```bash
   set -euo pipefail
   impl_base_sha=$(cat /tmp/gh124-impl-base-sha.txt)
   python_bin=$(cat /tmp/gh124-python-bin.txt)
   "$python_bin" - "$impl_base_sha" <<'PY'
   import ast
   import subprocess
   import sys

   def function_map(trees):
       result = {}
       for tree in trees:
           for node in tree.body:
               targets = node.targets if isinstance(node, ast.Assign) else (
                   [node.target] if isinstance(node, ast.AnnAssign) else []
               )
               if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets):
                   raise AssertionError("module-level pytestmark is forbidden")
           for node in tree.body:
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                   assert node.name not in result, f"duplicate function: {node.name}"
                   result[node.name] = ast.dump(node, include_attributes=False)
       return result

   def skip_xfail_calls(trees):
       result = []
       for tree in trees:
           for node in ast.walk(tree):
               func = node.func if isinstance(node, ast.Call) else None
               if (
                   isinstance(func, ast.Attribute)
                   and isinstance(func.value, ast.Name)
                   and func.value.id == "pytest"
                   and func.attr in {"skip", "xfail"}
               ):
                   result.append(ast.dump(node, include_attributes=False))
       return sorted(result)

   baseline = subprocess.check_output(
       ["git", "show", f"{sys.argv[1]}:tests/test_check_workflow.py"], text=True
   )
   paths = [
       "tests/check_workflow_test_support.py",
       "tests/test_check_workflow.py",
       "tests/test_check_workflow_paths.py",
   ]
   trees = {path: ast.parse(open(path, encoding="utf-8").read()) for path in paths}
   support_tests = [
       node.name for node in trees["tests/check_workflow_test_support.py"].body
       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
       and node.name.startswith("test_")
   ]
   assert not support_tests, support_tests
   baseline_tree = ast.parse(baseline)
   before = function_map([baseline_tree])
   after = function_map(list(trees.values()))
   assert len(before) == 57, len(before)
   assert before == after, "check workflow top-level FunctionDef AST mapping changed"
   before_skip_xfail = skip_xfail_calls([baseline_tree])
   after_skip_xfail = skip_xfail_calls(list(trees.values()))
   assert len(before_skip_xfail) == 15, len(before_skip_xfail)
   assert before_skip_xfail == after_skip_xfail, "skip/xfail AST changed"
   print(
       f"AST parity passed: {len(after)} functions, "
       f"{len(after_skip_xfail)} skip/xfail calls"
   )
   PY
   ```

5. 导入两个测试模块与 support，确认测试函数使用的全部 production/module 全局名称
   仍精确绑定真实对象：

   ```bash
   set -euo pipefail
   python_bin=$(cat /tmp/gh124-python-bin.txt)
   "$python_bin" - <<'PY'
   import importlib
   import sys
   from pathlib import Path

   root = Path.cwd().resolve()
   sys.path[:0] = [str(root / "tests"), str(root / "checks")]
   general = importlib.import_module("test_check_workflow")
   paths = importlib.import_module("test_check_workflow_paths")
   support = importlib.import_module("check_workflow_test_support")
   workflow = importlib.import_module("check_workflow")
   specrail_lib = importlib.import_module("specrail_lib")
   expected_general = {
       "check_workflow": workflow,
       "REQUIRED_FILES": workflow.REQUIRED_FILES,
       "validate_required_file_globs": workflow.validate_required_file_globs,
       "validate_auth_mode": workflow.validate_auth_mode,
       "validate_impl_branch_template": workflow.validate_impl_branch_template,
       "validate_pack_assets": workflow.validate_pack_assets,
       "load_pack": specrail_lib.load_pack,
       "check_workflow_main": workflow.main,
   }
   expected_paths = {
       "discover_spec_packet_dirs": workflow.discover_spec_packet_dirs,
       "select_spec_packet_dirs": workflow.select_spec_packet_dirs,
       "spec_packet_sort_key": workflow.spec_packet_sort_key,
       "validate_spec_packet": workflow.validate_spec_packet,
       "SpecRailError": specrail_lib.SpecRailError,
       "resolve_path": specrail_lib.resolve_path,
       "spec_packet_artifact_paths": specrail_lib.spec_packet_artifact_paths,
       "spec_packet_root": specrail_lib.spec_packet_root,
   }
   for name, expected in expected_general.items():
       assert getattr(general, name) is expected, name
   for name, expected in expected_paths.items():
       assert getattr(paths, name) is expected, name
   assert general.ROOT == paths.ROOT == support.ROOT == root
   print(
       "production symbol identity passed: "
       f"{len(expected_general) + len(expected_paths)} bindings"
   )
   PY
   ```

6. 审计 committed scope 与逐文件行数：

   ```bash
   set -euo pipefail
   impl_base_sha=$(cat /tmp/gh124-impl-base-sha.txt)
   git diff --name-only "$impl_base_sha"...HEAD | LC_ALL=C sort \
     > /tmp/gh124-changed-paths.txt
   printf '%s\n' tests/check_workflow_test_support.py tests/test_check_workflow.py \
     tests/test_check_workflow_paths.py | LC_ALL=C sort > /tmp/gh124-allowed-paths.txt
   diff -u /tmp/gh124-allowed-paths.txt /tmp/gh124-changed-paths.txt
   while IFS= read -r file; do
     lines=$(wc -l < "$file" | tr -d ' ')
     test "$lines" -lt 800 || { printf '%s has %s lines\n' "$file" "$lines" >&2; exit 1; }
   done < /tmp/gh124-allowed-paths.txt
   git diff --exit-code "$impl_base_sha"...HEAD -- checks schemas examples .github specs
   ```

7. 执行 focused/full 与 workflow 验证：

   ```bash
   set -euo pipefail
   impl_base_sha=$(cat /tmp/gh124-impl-base-sha.txt)
   python_bin=$(cat /tmp/gh124-python-bin.txt)
   if ! "$python_bin" -m pytest -q -r a tests/test_check_workflow*.py \
     > /tmp/gh124-focused-pytest.txt 2>&1; then
     tail -n 20 /tmp/gh124-focused-pytest.txt
     exit 1
   fi
   tail -n 20 /tmp/gh124-focused-pytest.txt
   rg -o '[0-9]+ (passed|failed|errors?|skipped|xfailed|xpassed)' \
     /tmp/gh124-focused-pytest.txt | LC_ALL=C sort \
     > /tmp/gh124-after-focused-outcomes.txt
   diff -u /tmp/gh124-before-focused-outcomes.txt \
     /tmp/gh124-after-focused-outcomes.txt
   "$python_bin" -m pytest -q
   python3 checks/check_workflow.py --repo . --all-specs
   python3 checks/check_workflow.py --repo . --spec-dir specs/GH124
   git diff --check "$impl_base_sha"...HEAD
   ```

## Risks and Rollback

- 风险：漏迁移或重复收集参数化 case。缓解：normalized node multiset 与全库 count
  必须与编辑前同环境证据完全相等。
- 风险：迁移时改变函数体、断言或 skip 条件。缓解：57-function 与 15-call AST parity。
- 风险：共享 bootstrap 使测试绑定到替代对象。缓解：production symbol identity 检查。
- 风险：历史单文件命令不再覆盖 path 主题。缓解：原文件保留 assets/config/policy
  核心覆盖，新的标准 focused 命令明确使用 `tests/test_check_workflow*.py`。
- 回滚：实现为无数据迁移的 test-only commit，可整体 revert；不得以修改 production
  或降低断言代替回滚。
