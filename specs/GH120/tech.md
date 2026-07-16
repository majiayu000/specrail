# Tech Spec

## Linked Issue

GH-120

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":120,"complete":true,"paths":["tests/route_gate_test_support.py","tests/test_route_gate.py","tests/test_route_gate_sensitive.py"],"spec_refs":["specs/GH120/product.md","specs/GH120/tech.md"]}
-->

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 共享执行/helper | `tests/test_route_gate.py:19`, `tests/test_route_gate.py:41`, `tests/test_route_gate.py:55`, `tests/test_route_gate.py:145`, `tests/test_route_gate.py:555` | 5 个 helper 负责 subprocess route gate、临时 pack、sensitive evidence 与 duplicate evidence | 拆分后必须维持单一来源和原始函数语义 |
| sensitive/approved spec | `tests/test_route_gate.py:186` | 15 个测试函数覆盖 trusted base、spec incorporation、manifest 与 forged evidence | 形成清晰且相对独立的安全主题模块 |
| 通用 route gate | `tests/test_route_gate.py:551` | 16 个测试函数覆盖 artifact path、readiness state、configured root 与 duplicate work | 保留为通用 route/readiness 模块 |
| production evaluator | `checks/route_gate.py:97`, `checks/route_gate.py:125` | `artifact_exists` 与 `evaluate_route` 实现确定性 gate | 本项禁止修改，只验证测试仍绑定真实对象 |
| CLI entry | `checks/route_gate.py:505` | 解析命令并输出 gate JSON | subprocess helper 的调用方式必须保持不变 |

## 设计方案

1. 新增 `tests/route_gate_test_support.py`，集中保留 `ROOT`、checks import bootstrap
   与 5 个既有 helper。文件名不以 `test_` 开头，不拥有可收集测试。
2. 新增 `tests/test_route_gate_sensitive.py`，迁移当前 `tests/test_route_gate.py:186-548`
   的 15 个 sensitive enforcement / approved-spec 测试函数。
3. 保留 `tests/test_route_gate.py`，迁移为通用模块，承载当前 `:551-1023` 的 16 个
   artifact/readiness/configured-path/duplicate-work 测试函数。
4. implementation 从当时最新 `origin/main` 创建；编辑前固定 `impl_base_sha`、唯一
   Python/pytest 入口、37-case normalized node multiset 与全库 553-case 基线。
5. 编辑后比较 normalized nodes、36 个顶层函数完整 AST、production symbol identity、
   skip/xfail、精确三路径 allowlist 与逐文件行数；任一差异都阻断交付。

不复制 helper、不动态生成测试、不使用 collection hook，也不改写测试函数体来满足行数目标。

## Deterministic Parity Procedure

implementation owner 在同一干净 worktree 中按顺序执行；步骤 1-2 必须发生在任何编辑前。

1. 记录实际 base 与唯一测试入口：

   ```sh
   git rev-parse HEAD > /tmp/gh120-impl-base-sha.txt
   command -v uvx > /tmp/gh120-uvx-bin.txt
   uvx pytest --version
   ```

2. 保存编辑前 normalized nodes 与全库 count：

   ```sh
   uvx pytest --collect-only -q tests/test_route_gate.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort > /tmp/gh120-before-nodes.txt
   uvx pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' > /tmp/gh120-before-all-count.txt
   test "$(rg -c '^def test_' tests/test_route_gate.py)" -eq 31
   test "$(wc -l < /tmp/gh120-before-nodes.txt | tr -d ' ')" -eq 37
   test "$(cat /tmp/gh120-before-all-count.txt)" -eq 553
   ```

3. 拆分后保存同形证据并比较：

   ```sh
   uvx pytest --collect-only -q tests/test_route_gate*.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort > /tmp/gh120-after-nodes.txt
   uvx pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' > /tmp/gh120-after-all-count.txt
   diff -u /tmp/gh120-before-nodes.txt /tmp/gh120-after-nodes.txt
   diff -u /tmp/gh120-before-all-count.txt /tmp/gh120-after-all-count.txt
   ```

4. 比较全部顶层函数 AST，并拒绝重复函数、support 测试、`pytestmark` 以及
   `pytest.skip`/`pytest.xfail`：

   ```sh
   impl_base_sha=$(cat /tmp/gh120-impl-base-sha.txt)
   python3 - "$impl_base_sha" <<'PY'
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

   baseline = subprocess.check_output(
       ["git", "show", f"{sys.argv[1]}:tests/test_route_gate.py"], text=True
   )
   paths = [
       "tests/route_gate_test_support.py",
       "tests/test_route_gate.py",
       "tests/test_route_gate_sensitive.py",
   ]
   trees = {path: ast.parse(open(path, encoding="utf-8").read()) for path in paths}
   support_tests = [
       node.name for node in trees["tests/route_gate_test_support.py"].body
       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
       and node.name.startswith("test_")
   ]
   assert not support_tests, support_tests
   before = function_map([ast.parse(baseline)])
   after = function_map(list(trees.values()))
   assert len(before) == 36, len(before)
   assert before == after, "route gate top-level FunctionDef AST mapping changed"
   print(f"AST parity passed: {len(after)} top-level functions")
   PY
   ```

5. 导入两个测试模块与 support，确认关键全局名称仍绑定真实 production objects：

   ```sh
   python3 - <<'PY'
   import importlib
   import sys
   from pathlib import Path

   root = Path.cwd().resolve()
   sys.path[:0] = [str(root / "tests"), str(root / "checks")]
   general = importlib.import_module("test_route_gate")
   sensitive = importlib.import_module("test_route_gate_sensitive")
   support = importlib.import_module("route_gate_test_support")
   assert general.artifact_exists is importlib.import_module("route_gate").artifact_exists
   assert support.build_approved_spec_evidence is importlib.import_module(
       "sensitive_enforcement"
   ).build_approved_spec_evidence
   assert support.load_pack is importlib.import_module("specrail_lib").load_pack
   assert general.ROOT == sensitive.ROOT == support.ROOT == root
   print("production symbol identity passed")
   PY
   ```

6. 审计 committed scope 与逐文件行数：

   ```sh
   set -eu
   impl_base_sha=$(cat /tmp/gh120-impl-base-sha.txt)
   git diff --name-only "$impl_base_sha"...HEAD | LC_ALL=C sort \
     > /tmp/gh120-changed-paths.txt
   printf '%s\n' tests/route_gate_test_support.py tests/test_route_gate.py \
     tests/test_route_gate_sensitive.py | LC_ALL=C sort > /tmp/gh120-allowed-paths.txt
   diff -u /tmp/gh120-allowed-paths.txt /tmp/gh120-changed-paths.txt
   while IFS= read -r file; do
     lines=$(wc -l < "$file" | tr -d ' ')
     test "$lines" -lt 800 || { printf '%s has %s lines\n' "$file" "$lines" >&2; exit 1; }
   done < /tmp/gh120-allowed-paths.txt
   git diff --exit-code "$impl_base_sha"...HEAD -- checks schemas examples .github specs
   ```

7. 执行 focused/full 与 workflow 验证：

   ```sh
   uvx pytest -q -r a tests/test_route_gate*.py | tee /tmp/gh120-focused-pytest.txt
   rg -q '37 passed' /tmp/gh120-focused-pytest.txt
   if rg -n '(^|, )[1-9][0-9]* (skipped|xfailed|xpassed)' /tmp/gh120-focused-pytest.txt; then exit 1; fi
   uvx pytest -q
   python3 checks/check_workflow.py --repo . --all-specs
   python3 checks/check_workflow.py --repo . --spec-dir specs/GH120
   impl_base_sha=$(cat /tmp/gh120-impl-base-sha.txt)
   git diff --check "$impl_base_sha"...HEAD
   ```

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 两个测试模块 | 步骤 2-3；normalized nodes 与全库 count diff 均为空 |
| B-002 | 两个测试模块与 support | 步骤 4、6；三文件 `<800`，support 无测试且 helper 单一来源 |
| B-003 | committed diff scope | 步骤 6；changed paths 精确闭合且 protected paths 无 diff |
| B-004 | 全部迁移函数与 production bindings | 步骤 4-5、7；36-function AST、identity 与 no-skip gate 通过 |
| B-005 | repository validation | focused/full pytest、all-spec/single-spec workflow 与 `git diff --check` |

## 数据流

pytest 收集两个 `test_route_gate*.py` 模块；它们从唯一 support 构造本地 pack/evidence，
再直接调用未修改的 production evaluator。所有临时 repo 和 evidence 仍只存在于 pytest
临时目录；不新增网络、持久化或远端写入。

## 备选方案

- 只按行数机械切分并复制 helper：拒绝，会制造漂移来源。
- 豁免测试文件的 800 行规则：拒绝，会隐藏已量化的维护性问题。
- 同时重构 production route gate：拒绝，超出 GH120 的 test-only 范围并放大风险。

## 风险

- Security: 不改变生产或授权 gate；漏迁移 fail-closed 负例由 node、AST 与 identity 阻断。
- Compatibility: pytest 文件路径变化，但函数、参数与 production API 不变；未声明外部消费者依赖完整 node path。
- Performance: 模块导入略有变化，不承诺未经基准支持的性能提升。
- Maintenance: support import 顺序可能影响 checks bootstrap；使用单一 ROOT、identity 与完整 focused run 验证。

## 测试计划

- [ ] Unit tests: 37-case node multiset、36-function AST 与 production identity 完全相等。
- [ ] Integration tests: 全库 553 cases、全量 pytest 与 workflow checks 通过。
- [ ] Manual verification: 核对实际 base、三文件行数、helper 单一来源和 committed scope。

## 回滚方案

implementation 使用独立 test-only commit；任一 parity 或全量验证失败时回滚该提交，恢复
单文件基线，无数据迁移、远端副作用或 feature flag。
