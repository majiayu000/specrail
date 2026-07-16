# Tech Spec

## Linked Issue

GH-127

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":127,"complete":true,"paths":["tests/pr_gate_test_support.py","tests/test_pr_gate.py","tests/test_pr_gate_terminal.py"],"spec_refs":["specs/GH127/product.md","specs/GH127/tech.md"]}
-->

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Current | Target |
| --- | --- | --- |
| support | `tests/test_pr_gate.py:12-119,253` | 非收集 support，保留 3 helpers 与 production bootstrap |
| sensitive/core | `tests/test_pr_gate.py:122-614` | 保留在原模块；删除第 396 行被遮蔽定义 |
| terminal review/merge | `tests/test_pr_gate.py:617-887` | 迁入 `test_pr_gate_terminal.py`，保留实际运行同名定义 |
| production | `checks/pr_gate.py` 等 | 禁止修改，验证 object identity |

## 设计方案

1. 新增 `tests/pr_gate_test_support.py`，集中 `ROOT`、`FIXTURES`、checks bootstrap、
   `clean_evidence`、`sensitive_evidence`、`fixture` 与真实 production imports。
2. 原 `tests/test_pr_gate.py` 保留 sensitive enforcement、issue reference、CI/thread、
   self-review、ordering 与 CLI 核心用例；删除第 396-403 行未被收集的遮蔽定义。
3. 新增 `tests/test_pr_gate_terminal.py`，迁移第 617-887 行 terminal review evidence、
   successor lineage 与 merge-record 用例，包括当前实际运行的 missing-review-source 测试。
4. 用固定环境保存编辑前 collection/outcome；用 AST 明确证明基线恰有两个同名定义，
   排除较早定义后，其余 54 个函数与拆分后精确相等。

## Deterministic Parity Procedure

1. 固定 base 与唯一 Python：

   ```bash
   set -euo pipefail
   git rev-parse HEAD > /tmp/gh127-impl-base-sha.txt
   uv venv --clear --python '3.13.11' /tmp/gh127-pytest-env
   uv pip install --python /tmp/gh127-pytest-env/bin/python 'pytest==9.1.1'
   printf '%s\n' /tmp/gh127-pytest-env/bin/python > /tmp/gh127-python-bin.txt
   "$(cat /tmp/gh127-python-bin.txt)" -m pytest --version
   ```

2. 编辑前保存 normalized nodes、全库 count 与 focused outcomes：

   ```bash
   set -euo pipefail
   python_bin=$(cat /tmp/gh127-python-bin.txt)
   if ! "$python_bin" -m pytest --collect-only -q tests/test_pr_gate.py > /tmp/gh127-before-focused.txt 2>&1; then
     tail -n 20 /tmp/gh127-before-focused.txt
     exit 1
   fi
   sed -n '/::/s/^[^:]*:://p' /tmp/gh127-before-focused.txt | LC_ALL=C sort > /tmp/gh127-before-nodes.txt
   if ! "$python_bin" -m pytest --collect-only -q > /tmp/gh127-before-all.txt 2>&1; then
     tail -n 20 /tmp/gh127-before-all.txt
     exit 1
   fi
   awk '/::/{count++} END{print count+0}' /tmp/gh127-before-all.txt > /tmp/gh127-before-all-count.txt
   test "$(wc -l < /tmp/gh127-before-nodes.txt | tr -d ' ')" -eq 69
   test "$(cat /tmp/gh127-before-all-count.txt)" -eq 553
   if ! "$python_bin" -m pytest -q -r a tests/test_pr_gate.py > /tmp/gh127-before-run.txt 2>&1; then
     tail -n 20 /tmp/gh127-before-run.txt
     exit 1
   fi
   rg -o '[0-9]+ (passed|failed|errors?|skipped|xfailed|xpassed)' /tmp/gh127-before-run.txt | LC_ALL=C sort > /tmp/gh127-before-outcomes.txt
   test -s /tmp/gh127-before-outcomes.txt
   ```

3. 编辑后比较 collection 与 outcomes：

   ```bash
   set -euo pipefail
   python_bin=$(cat /tmp/gh127-python-bin.txt)
   if ! "$python_bin" -m pytest --collect-only -q tests/test_pr_gate*.py > /tmp/gh127-after-focused.txt 2>&1; then
     tail -n 20 /tmp/gh127-after-focused.txt
     exit 1
   fi
   sed -n '/::/s/^[^:]*:://p' /tmp/gh127-after-focused.txt | LC_ALL=C sort > /tmp/gh127-after-nodes.txt
   if ! "$python_bin" -m pytest --collect-only -q > /tmp/gh127-after-all.txt 2>&1; then
     tail -n 20 /tmp/gh127-after-all.txt
     exit 1
   fi
   awk '/::/{count++} END{print count+0}' /tmp/gh127-after-all.txt > /tmp/gh127-after-all-count.txt
   diff -u /tmp/gh127-before-nodes.txt /tmp/gh127-after-nodes.txt
   diff -u /tmp/gh127-before-all-count.txt /tmp/gh127-after-all-count.txt
   if ! "$python_bin" -m pytest -q -r a tests/test_pr_gate*.py > /tmp/gh127-after-run.txt 2>&1; then
     tail -n 20 /tmp/gh127-after-run.txt
     exit 1
   fi
   rg -o '[0-9]+ (passed|failed|errors?|skipped|xfailed|xpassed)' /tmp/gh127-after-run.txt | LC_ALL=C sort > /tmp/gh127-after-outcomes.txt
   diff -u /tmp/gh127-before-outcomes.txt /tmp/gh127-after-outcomes.txt
   ```

4. 证明遮蔽定义与保留函数 AST parity：

   ```bash
   set -euo pipefail
   impl_base_sha=$(cat /tmp/gh127-impl-base-sha.txt)
   python_bin=$(cat /tmp/gh127-python-bin.txt)
   "$python_bin" - "$impl_base_sha" <<'PY'
   import ast
   import collections
   import subprocess
   import sys

   baseline = ast.parse(subprocess.check_output(
       ["git", "show", f"{sys.argv[1]}:tests/test_pr_gate.py"], text=True
   ))
   base_functions = [
       node for node in baseline.body
       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
   ]
   duplicates = collections.defaultdict(list)
   for node in base_functions:
       duplicates[node.name].append(node)
   duplicate_nodes = duplicates["test_pr_gate_blocks_missing_review_source"]
   assert [node.lineno for node in duplicate_nodes] == [396, 617]
   shadowed = duplicate_nodes[0]

   paths = [
       "tests/pr_gate_test_support.py",
       "tests/test_pr_gate.py",
       "tests/test_pr_gate_terminal.py",
   ]
   trees = {path: ast.parse(open(path, encoding="utf-8").read()) for path in paths}
   for tree in trees.values():
       for node in tree.body:
           targets = node.targets if isinstance(node, ast.Assign) else (
               [node.target] if isinstance(node, ast.AnnAssign) else []
           )
           assert not any(
               isinstance(target, ast.Name) and target.id == "pytestmark"
               for target in targets
           )

   def function_map(nodes):
       result = {}
       for node in nodes:
           assert node.name not in result, node.name
           result[node.name] = ast.dump(node, include_attributes=False)
       return result

   expected = function_map(node for node in base_functions if node is not shadowed)
   after_nodes = [
       node for tree in trees.values() for node in tree.body
       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
   ]
   after = function_map(after_nodes)
   assert len(expected) == len(after) == 54
   assert expected == after
   assert sum(name.startswith("test_") for name in after) == 51
   assert not [
       name for name in function_map([
           node for node in trees[paths[0]].body
           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
       ]) if name.startswith("test_")
   ]
   skip_xfail = [
       node for tree in trees.values() for node in ast.walk(tree)
       if isinstance(node, ast.Call)
       and isinstance(node.func, ast.Attribute)
       and isinstance(node.func.value, ast.Name)
       and node.func.value.id == "pytest"
       and node.func.attr in {"skip", "xfail"}
   ]
   assert not skip_xfail
   print("AST parity passed: removed 1 shadowed definition; retained 54 unique functions")
   PY
   ```

5. 验证 production identity：

   ```bash
   set -euo pipefail
   python_bin=$(cat /tmp/gh127-python-bin.txt)
   "$python_bin" - <<'PY'
   import importlib
   import sys
   from pathlib import Path
   root = Path.cwd().resolve()
   sys.path[:0] = [str(root / "tests"), str(root / "checks")]
   support = importlib.import_module("pr_gate_test_support")
   general = importlib.import_module("test_pr_gate")
   terminal = importlib.import_module("test_pr_gate_terminal")
   pr_gate = importlib.import_module("pr_gate")
   sensitive = importlib.import_module("sensitive_enforcement")
   lib = importlib.import_module("specrail_lib")
   assert support.evaluate_pr_gate is general.evaluate_pr_gate is terminal.evaluate_pr_gate is pr_gate.evaluate_pr_gate
   assert support.build_approved_spec_evidence is sensitive.build_approved_spec_evidence
   assert support.load_pack is lib.load_pack
   assert support.ROOT == general.ROOT == terminal.ROOT == root
   print("production identity passed")
   PY
   ```

6. 审计 scope、行数与最终验证：

   ```bash
   set -euo pipefail
   impl_base_sha=$(cat /tmp/gh127-impl-base-sha.txt)
   python_bin=$(cat /tmp/gh127-python-bin.txt)
   git diff --name-only "$impl_base_sha"...HEAD | LC_ALL=C sort > /tmp/gh127-changed.txt
   printf '%s\n' tests/pr_gate_test_support.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py | LC_ALL=C sort > /tmp/gh127-allowed.txt
   diff -u /tmp/gh127-allowed.txt /tmp/gh127-changed.txt
   while IFS= read -r file; do
     lines=$(wc -l < "$file" | tr -d ' ')
     test "$lines" -lt 800 || { printf '%s has %s lines\n' "$file" "$lines" >&2; exit 1; }
   done < /tmp/gh127-allowed.txt
   git diff --exit-code "$impl_base_sha"...HEAD -- checks schemas examples .github specs
   "$python_bin" -m pytest -q
   python3 checks/check_workflow.py --repo . --all-specs
   python3 checks/check_workflow.py --repo . --spec-dir specs/GH127
   git diff --check "$impl_base_sha"...HEAD
   ```

## Risks and Rollback

- 漏迁移/重复收集：normalized node multiset 与全库 count 必须完全相等。
- 错删实际用例：基线必须证明两个同名定义位于 396/617，且只排除较早定义；当前运行
  的较后定义 AST 必须保留。
- import drift：production identity 与 54-function AST gate 阻断 wrapper/替代对象。
- 回滚：test-only commit 可整体 revert，不得修改 production 或弱化测试代替回滚。
