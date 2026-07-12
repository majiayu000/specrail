# Tech Spec

## Linked Issue

GH-91

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Artifact validation | `checks/specrail_lib.py:389` | GH91 前只有字符串替换，没有 packet root、Windows drive 或 artifact 位置校验 | 需要唯一的 template 解释规则 |
| Packet discovery | `checks/check_workflow.py:272` | GH91 前固定扫描 `repo / "specs"` | 自定义根目录被漏检 |
| Issue evidence | `checks/github_issue_evidence.py:152` | GH91 前默认 artifacts 固定为 `specs/GH<number>` | route gate 会收到错误文件证据 |
| Route verification | `checks/route_gate.py:314` | GH91 前返回的 `--spec-dir` 固定且未 quote | handoff 命令不可执行或可被注入 |
| Regression tests | `tests/test_check_workflow.py:96`, `tests/test_github_issue_evidence.py:96`, `tests/test_route_gate.py:161` | GH91 前只覆盖默认路径 | 需要 custom-root、escape 与 quoting 负例 |

## 设计方案

### 1. 单一 packet template 解释器

在 `checks/specrail_lib.py` 增加确定性 helper，将
`artifacts.spec_packet` 分别用 issue `1`、`2` 渲染。helper 接受
`{issue_number}` 或 `{work_id}`，要求最终目录名分别为 `GH1`、`GH2`，且两次
渲染的父目录相同。

helper 拒绝：

- 缺失 template 或缺失受支持 placeholder；
- POSIX/Windows drive/UNC 路径、反斜杠、`..` 逃逸；
- 渲染后仍含花括号；
- 最终目录不是 `GH<number>` 或父目录随 issue 改变。

这里使用 repo-relative POSIX 路径语义；调用方通过 path parts 与本机 `Path`
组合，避免依赖当前工作目录，也不允许静默 fallback。

### 2. Workflow discovery 使用配置

`discover_spec_packet_dirs` 和 `select_spec_packet_dirs` 接受可选 pack config。
未传 config 的库级调用保留默认 `specs/` 行为；CLI 主路径总是传入已加载的
config，并在普通 pack check 中也验证 template，因此非法配置不会只在
`--all-specs` 时才暴露。扫描根、每个 packet 与显式 `--spec-dir` 在 `resolve`
后都必须仍位于 repo 内。解析后的 packet 必须精确等于配置 root 下的词法
`GH<number>`，三文件必须分别精确等于 packet 下固定文件名；因此同 root/packet
内的 symlink identity 重定向也会失败。symlink loop 等 resolve 异常统一转为
`SpecRailError`。

### 3. Issue evidence 使用所选 repo

`github_issue_evidence.py` 增加默认值为 `.` 的 `--repo` 参数。CLI 从该目录加载
pack，并通过共享 validator 渲染 `product_spec`、`tech_spec`、`task_plan`。
三者必须精确位于 packet 下并使用 `product.md`、`tech.md`、`tasks.md`；缺失、
逃逸或错位均抛出 `SpecRailError`。GitHub payload number 与 CLI issue 不一致时
抛出 `EvidenceError`；read-only GitHub 查询本身不变。

`build_issue_evidence` 保留可注入 artifact mapping，方便纯函数测试；CLI 不再
走固定默认值。

### 4. Route gate 命令使用同一模板

`route_gate.py` 使用同一 validated packet path 生成 `verification_commands`，并用
`--spec-dir=` 与 `shlex.quote` 序列化 repo-controlled 参数，保证前导 `-`、空格和
shell metacharacter 都保持单一参数。required artifact 的存在
检查也在 resolve 后验证 repo containment，拒绝 symlink 或 `..` 逃逸。

### 5. 文档与 changelog

更新 README/AGENT_USAGE，明确 `--all-specs` 和 issue evidence 读取当前 pack 的
artifact templates；记录 Unreleased 修复。不修改 skill 文件，避免不必要的
lockfile churn。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 configured discovery | `specrail_lib.py`, `check_workflow.py` | `python3 -m pytest -q tests/test_check_workflow.py tests/test_evaluate.py -k configured` |
| B-002 explicit/combined selection | `select_spec_packet_dirs` | `python3 -m pytest -q tests/test_evaluate.py -k select` |
| B-003 configured issue artifacts | `github_issue_evidence.py` | `python3 -m pytest -q tests/test_github_issue_evidence.py -k 'configured or mismatched'` |
| B-004 configured verification command | `route_gate.py` | `python3 -m pytest -q tests/test_route_gate.py -k 'configured or shell_quotes'` |
| B-005 default compatibility | existing default-path tests | `python3 -m pytest -q tests/test_evaluate.py tests/test_github_issue_evidence.py tests/test_route_gate.py` |
| B-006 invalid template rejection | shared path validators | `python3 -m pytest -q tests/test_check_workflow.py -k 'spec_packet_root or invalid_paths or symlink or parent_escape'` |
| B-007 read-only boundary | unchanged collector/gate command paths | `python3 -m pytest -q tests/test_github_issue_evidence.py tests/test_route_gate.py` |
| B-008 explicit errors | CLI exception handling and validator | `python3 checks/check_workflow.py --repo .` plus negative unit tests |

## 数据流

```text
workflow.yaml artifacts
        |
        +--> spec_packet_root --> --all-specs discovery
        |
        +--> validated artifact paths --> GitHub issue evidence
        |
        +--> validated artifact paths + shlex.quote --> route verification command
```

输入是本地 pack config 与只读 GitHub issue payload；输出是 validation result、
evidence JSON 或 route decision JSON。没有持久化和远端写入。

## 备选方案

- 在消费仓库建立 `specs -> docs/specs` symlink：拒绝；制造第二份路径事实且在
  Windows/checkout policy 下不稳定。
- 只给 `check_workflow.py` 新增 `--spec-root`：拒绝；配置仍会与 evidence/route
  执行面分裂。
- 保留硬编码并让消费仓库迁移：拒绝；`workflow.yaml` 已声明可配置 artifacts。

## 风险

- Security: 配置路径可能尝试逃逸 repo、重定向 packet/file identity 或注入 handoff
  command；helper 拒绝 POSIX/Windows/`..`/symlink 逃逸和 identity 重定向，命令
  参数使用 `--spec-dir=` 与 `shlex.quote`。
- Compatibility: 默认 helper 参数保留现有库调用；默认 templates 的结果不变。
- Performance: 每次命令只解析一次小型 YAML 并扫描一个父目录，可忽略。
- Maintenance: artifact templates 仍是唯一配置源，三个执行面通过共享 renderer 对齐。

## 测试计划

- [x] Unit tests: template validation、custom discovery、configured artifact rendering。
- [x] Integration tests: fake `gh` CLI + custom repo config。
- [x] Regression tests: 默认路径、去重/排序、route decision 全量既有测试。
- [x] Full suite: `python3 -m pytest -q`。
- [x] Pack checks: root、all specs、GH91 packet。

## 回滚方案

回滚 GH91 commit 即可恢复旧行为；没有数据迁移或远端状态变更。回滚后自定义
spec 根目录重新 fail closed/漏检，因此消费仓库 adoption 不应在回滚版本上启用。
