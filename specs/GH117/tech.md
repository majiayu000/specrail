# Tech Spec

## Linked Issue

GH-117

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":117,"complete":true,"paths":["tests/github_pr_evidence_test_support.py","tests/test_github_pr_evidence.py","tests/test_github_pr_evidence_approval.py","tests/test_github_pr_evidence_cli.py"],"spec_refs":["specs/GH117/product.md","specs/GH117/tech.md"]}
-->

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 共享 payload/helper | `tests/test_github_pr_evidence.py:42` | 8 个 helper 构造 PR、threads、review、snapshot 与 approval payload | 拆分后需要单一来源，不能复制测试数据 |
| approval timeline | `tests/test_github_pr_evidence.py:198` | 验证 label timeline pagination、drift、merged spec provenance | 形成 approval/snapshot 主题的一部分 |
| PR file snapshot | `tests/test_github_pr_evidence.py:336` | 验证 REST pagination、rename source 与 snapshot drift | 与 approved-spec/path classification 同属 pre-gate evidence |
| evidence/review relation | `tests/test_github_pr_evidence.py:491` | 验证 build contract、partial/closing relation、resolver roles 与 authorization | 保留为 core evidence 模块 |
| CLI/query lifecycle | `tests/test_github_pr_evidence.py:1004` | fake-gh CLI、live issue query 与 head/relation snapshot race | 可独立为 CLI/query 模块 |
| production adapter | `checks/github_pr_evidence.py:1` | 只读采集并规范化 GitHub PR evidence | 本项禁止修改 production evaluator |
| snapshot/approval production | `checks/github_pr_snapshot.py:1`, `checks/github_approved_spec_evidence.py:1` | 提供 file snapshot 与 approved-spec timeline 采集 | 测试拆分后仍须直接绑定这些对象 |

## 设计方案

1. 增加 `tests/github_pr_evidence_test_support.py`，集中保留 `ROOT`、checks import
   bootstrap 与 8 个既有 helper；使用非 `test_` 文件名，且不拥有可收集测试。
2. 保留 `tests/test_github_pr_evidence.py` 作为 core 模块，覆盖 evidence contract、
   partial/closing relation、review-thread resolver 与 authorization。
3. 新建 `tests/test_github_pr_evidence_approval.py`，承载 approved-spec timeline 与
   PR file snapshot/pagination 测试。
4. 新建 `tests/test_github_pr_evidence_cli.py`，承载 fake-gh CLI、collect/query
   lifecycle 与 head/relation snapshot drift 测试。
5. implementation 从当时最新 `origin/main` 创建，编辑前固定 `impl_base_sha` 与唯一
   Python interpreter，保存 focused normalized node multiset 和全库 collection count。
6. 编辑后比较 normalized nodes、全部 50 个顶层函数 AST、production symbol identity、
   skip/xfail、精确 path allowlist 与每文件行数；任何差异均阻断。

不复制 helper、不动态生成测试、不改写断言，也不以 pytest collection hook 或
skip/xfail 达成行数目标。

## Deterministic Parity Procedure

implementation owner 在同一干净 worktree 中按顺序执行；步骤 1-2 必须发生在任何
编辑前，`/tmp` 证据不提交。

1. 记录实际 base 与唯一 Python：

   ```sh
   git rev-parse HEAD > /tmp/gh117-impl-base-sha.txt
   python_bin=${PYTHON_BIN:-python3}
   command -v "$python_bin" > /tmp/gh117-python-bin.txt
   python_bin=$(cat /tmp/gh117-python-bin.txt)
   "$python_bin" -m pytest --version
   ```

2. 保存编辑前 normalized nodes 与全库 count：

   ```sh
   python_bin=$(cat /tmp/gh117-python-bin.txt)
   "$python_bin" -m pytest --collect-only -q tests/test_github_pr_evidence.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort \
     > /tmp/gh117-before-nodes.txt
   "$python_bin" -m pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' > /tmp/gh117-before-all-count.txt
   test "$(rg -c '^def test_' tests/test_github_pr_evidence.py)" -eq 42
   test "$(wc -l < /tmp/gh117-before-nodes.txt | tr -d ' ')" -eq 79
   ```

3. 拆分后保存同形证据并逐项比较：

   ```sh
   python_bin=$(cat /tmp/gh117-python-bin.txt)
   "$python_bin" -m pytest --collect-only -q tests/test_github_pr_evidence*.py \
     | sed -n '/::/s/^[^:]*:://p' | LC_ALL=C sort \
     > /tmp/gh117-after-nodes.txt
   "$python_bin" -m pytest --collect-only -q \
     | awk '/::/{count++} END{print count+0}' > /tmp/gh117-after-all-count.txt
   diff -u /tmp/gh117-before-nodes.txt /tmp/gh117-after-nodes.txt
   diff -u /tmp/gh117-before-all-count.txt /tmp/gh117-after-all-count.txt
   ```

4. 用 `git show "$impl_base_sha":tests/test_github_pr_evidence.py` 解析基线，并对
   四个允许文件运行 AST mapping：拒绝重复函数名、support 中的 `test_*`、任何
   `pytestmark` 赋值以及 `pytest.skip`/`pytest.xfail` 调用；要求编辑前后 mapping
   完全相等并输出 `AST parity passed: 50 top-level functions`。

5. 导入三个测试模块和 support，逐项确认以下全局名称仍以 `is` 绑定到对应 production
   module 对象：

   - `github_pr_evidence`: `EvidenceError`, `REVIEW_THREADS_QUERY`, `build_evidence`,
     `build_human_authorization`, `collect_issue_view`, `collect_evidence`,
     `load_resolver_role_map`, `normalize_issue_reference`, `normalize_review_threads`,
     `parse_github_repo`, `references_partial_issue`, `run_gh_json`
   - `github_approved_spec_evidence`: `collect_approval_metadata`
   - `github_pr_snapshot`: `assert_same_pr_file_snapshot`, `collect_pr_file_snapshot`,
     `derive_spec_refs`
   - `pr_gate`: `evaluate_pr_gate`
   - `sensitive_enforcement`: `classify_sensitive_changes`
   - `specrail_lib`: `PackConfig`, `load_pack`

   同时要求全部测试模块与 support 的 `ROOT == Path.cwd().resolve()`。

6. 提交后以 `impl_base_sha...HEAD` 计算 changed paths，要求它减去 B-003 四路径
   allowlist 后为空；逐文件执行 `test "$(wc -l < "$file")" -lt 800`，并要求
   `checks/ schemas/ examples/fixtures/ .github/workflows/ specs/` 无 committed diff。

7. focused run 必须实际执行全部 79 cases，且 `-r a` summary 中不得出现非零
   skipped/xfailed/xpassed；随后执行全量 pytest、workflow checks 与 whitespace check。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 三个测试模块 | 步骤 1-3；normalized nodes 与全库 count diff 均为空 |
| B-002 | 三个测试模块与 support | 步骤 6；四文件逐一 `<800`，support 无测试且 helper 单一来源 |
| B-003 | committed diff scope | 步骤 6；changed paths 精确闭合且 protected paths 无 diff |
| B-004 | 全部迁移函数与 production bindings | 步骤 4-5、7；50-function AST、identity 与 no-skip gate 通过 |
| B-005 | repository validation | focused/full pytest、all-spec/single-spec workflow 与 `git diff --check` |

## 数据流

pytest 收集三个 `test_github_pr_evidence*.py` 模块；它们从唯一 support 构造 GitHub
形状的本地 payload，再直接调用未修改的 production objects。fake-gh 仍只在 pytest
临时目录中执行；不新增网络、持久化或远端写入。

## 备选方案

- 只按行数机械切成两个文件并复制 payload helper：拒绝，会产生漂移来源。
- 豁免测试文件的 800 行规则：拒绝，会隐藏已确认的维护性问题。
- 同时重构 production adapter：拒绝，超出 GH117 的 test-only 范围并放大风险。

## 风险

- Security: 不改变生产或授权 gate；主要风险是漏迁移 fail-closed 负例，由 node、AST
  与 production identity 三重阻断。
- Compatibility: pytest 模块路径改变，但函数、参数与 production API 不变；仓库未声明
  外部消费者依赖完整测试 node path。
- Performance: 模块导入略有变化，不承诺未经基准支持的加速。
- Maintenance: support import 顺序可能影响 checks bootstrap；使用单一 ROOT/bootstrap、
  import identity 和完整 focused run 验证。

## 测试计划

- [ ] Unit tests: 79-case node multiset、50-function AST 与 production identity 完全相等。
- [ ] Integration tests: 全库 collected count、全量 pytest 与 workflow checks 通过。
- [ ] Manual verification: 核对实际 base、四文件行数、helper 单一来源和 committed scope。

## 回滚方案

implementation 使用独立 test-only commit；若任何 parity 或全量验证失败，回滚该提交
恢复单文件基线，无数据迁移或 feature flag。
