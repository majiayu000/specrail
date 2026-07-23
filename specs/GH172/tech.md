# Tech Spec

## Linked Issue

GH-172

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":172,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/installed_skill_integrity.py","checks/specrail_lib.py","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-install/SKILL.md","tests/test_check_workflow.py","tests/test_evaluate.py","tests/test_install_codex_skills.py","tests/test_installed_skill_integrity.py","tools/check_installed_codex_skills.py","tools/install_codex_skills.py"],"spec_refs":["specs/GH172/product.md","specs/GH172/tech.md","specs/GH172/tasks.md"]}
-->

## Product Spec

见 `specs/GH172/product.md`。本设计实现 B-001..B-020，并明确排除 GH-160。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 仓库 lock 校验 | `checks/specrail_lib.py:559-655` | `_sha256_file()` 与 `validate_skills_lock()` 只校验 `skills/<name>/SKILL.md`；lock version 固定为 1，目录内其他文件不在完整性集合中。 | 需要在保持现有单文件条目兼容的前提下，增加可选的目录内文件清单并拒绝未锁定、重复或越界资产。 |
| 整包检查 | `checks/check_workflow.py:32-86`, `checks/check_workflow.py:485-522` | `REQUIRED_FILES` 包含 installer 与 lock，主流程只调用仓库内 `validate_skills_lock()`，不访问本机安装目录。 | 新 doctor 工具必须成为 pack 必需资产，但普通 workflow 检查继续只验证仓库，不读取 `$HOME`。 |
| installer 数据模型 | `tools/install_codex_skills.py:28-58` | 本地 `LockedSkill` 只保存入口文件期望哈希；默认目标解析实现在 installer 内。 | 将文件清单与目标解析抽到共享只读 helper，避免 installer 与 doctor 漂移。 |
| installer 写入与复核 | `tools/install_codex_skills.py:61-101` | dry-run 只打印 source/destination；`--apply` 删除并复制整个目录，之后只复核安装的 `SKILL.md`。 | dry-run 应披露 pre-install integrity；apply 后必须复核全部锁定文件，不能只验证入口。 |
| installer CLI | `tools/install_codex_skills.py:104-147` | `--target-dir` 默认在 parser 构造时解析；无独立 doctor/JSON/require-installed 模式。 | 新 checker CLI 负责只读状态与退出码；installer 复用 library，不复制状态逻辑。 |
| installer 测试 | `tests/test_install_codex_skills.py:18-48`, `tests/test_install_codex_skills.py:69-106` | fixture 只生成单文件 v1 lock，覆盖 dry-run、apply 与 source-target 拒绝。 | 保留全部既有用例并增加多文件、pre/post doctor、漂移/缺失和无写入测试。 |
| agent 安装入口 | `skills/specrail-install/SKILL.md:18-51` | doctor 路径只运行 installer dry-run 与 workflow check；安装后文字要求人工核对 `SKILL.md` 哈希。 | 改为调用确定性 installed doctor，继续保留 `--apply` 人工授权。 |
| queue 入口 | `skills/implx/SKILL.md:17-29`, `skills/specrail-implement-queue/SKILL.md:11-38` | preflight 读取配置和 GitHub 队列，但不验证实际加载的安装 skill 与 lock 一致。 | 在派生 lane、写 checkpoint 或远端动作前运行 `--require-installed` doctor；失败时 fail closed。 |
| lock 回归 | `tests/test_evaluate.py:140-191` | 直接构造 v1 单文件 lock 验证 `validate_skills_lock()` 的通过与哈希失配。 | 扩充为可选多文件清单、集合闭合和路径安全回归，证明 v1 单文件兼容。 |

## 设计方案

### 1. 兼容扩展 `skills-lock.json`

保持顶层 `version: 1`、每个 skill 的 `path` 与 `computedHash` 语义不变：
它们继续绑定主入口 `skills/<name>/SKILL.md`。每个 skill 条目新增可选
`files[]`，仅声明入口之外的受分发文件：

```json
{
  "name": "specrail-implement-queue",
  "path": "skills/specrail-implement-queue/SKILL.md",
  "computedHash": "sha256:...",
  "files": [
    {
      "path": "references/runtime.md",
      "computedHash": "sha256:..."
    }
  ]
}
```

`files[].path` 必须是相对于该 skill 目录的 POSIX 路径，禁止绝对路径、空路径、
`.`、`..`、反斜线、重复路径和 `SKILL.md` 重复声明。仓库 validator 枚举 skill
目录中的普通文件；集合必须恰好等于入口加 `files[]`。目录、符号链接、socket
或其他非普通文件不属于合法分发资产并 fail closed。未声明 `files` 的现有条目
仍只信任 `SKILL.md`，因此 B-015 保持兼容而不会扩大信任面。

在 `checks/specrail_lib.py` 提供共享的不可变 lock manifest 数据结构和 loader。
`validate_skills_lock()`、installer 与 installed doctor 都消费同一规范化结果，
不再各自解析 JSON。错误聚合保持稳定排序。

### 2. 只读完整性 library

新增 `checks/installed_skill_integrity.py`：

- `resolve_codex_skills_dir(explicit_target, environ, home)` 实现唯一目标解析：
  explicit → `$CODEX_HOME/skills` → `~/.codex/skills`；
- `inspect_installed_skills(repo, target)` 先调用共享 lock validator/loader，再对每个
  manifest 文件构造安装目标；
- 安装根不存在时返回整体 `not_installed`，不创建目录；
- 安装根存在时，每个文件返回 `match | drift | missing | unsafe | unstable`，
  结果包含 skill、相对文件、目标路径、expected/actual hash 和非敏感 reason；
- 路径检查使用 `lstat` 与受控根边界，拒绝 skill 目录、父组件或文件符号链接，
  且在读取前后比较 inode/device/size/mtime，变化时返回 `unstable`；
- 只读取 lock 声明的普通文件，不扫描或输出未声明文件正文；
- 返回结构化 Python 结果与稳定 JSON 字典，library 不调用 `sys.exit()`、不写文件。

整体状态规则：

- 目标根不存在：`not_installed`；
- 根存在且全部文件匹配：`match`；
- 根存在且出现其他状态：`invalid`。

### 3. 独立 doctor CLI

新增 `tools/check_installed_codex_skills.py`，参数：

- `--repo`：SpecRail 源仓库；
- `--target-dir`：显式覆盖安装根；
- `--json`：输出机器可读结果；
- `--require-installed`：把 `not_installed` 从显式 skipped 变为非零阻断，供 queue 使用。

默认退出码：`match=0`、`not_installed=0`、`invalid=1`、lock/运行错误 `=1`。
带 `--require-installed` 时只有 `match=0`。人类文本与 JSON 都按 skill path 排序，
不输出正文或环境变量内容。

`checks/check_workflow.py` 只把新 library/CLI 加入 `REQUIRED_FILES` 并继续执行仓库
lock 校验；它不调用 doctor，CI 因此不依赖本机安装状态。

### 4. installer 接线

`tools/install_codex_skills.py` 删除自己的目标解析与只含入口哈希的数据模型，改用共享
manifest 与 integrity library：

1. 解析/验证仓库 lock；
2. 运行只读 pre-install inspect；
3. dry-run 打印现状和安装计划，不写文件；目标不存在成功，目标存在但 drift/missing
   返回非零并给出 `--apply` 需要人工授权的说明；
4. `--apply` 只有在用户显式传入时执行既有同步写入；pre-install drift 是待修复状态，
   不阻止已授权 apply；
5. apply 后重新运行完整 inspect，只有整体 `match` 才成功。

复制仍以 skill 目录为单位，保证未来引用/脚本随目录分发；post-check 只信 lock 清单。
本 issue 不改变删除旧目标目录的既有 apply 语义，也不自动调用 apply。

### 5. queue/install Skill 接线

- `specrail-install` 的 `doctor` 路由直接调用新 checker；`install_local_skills`
  先 doctor/dry-run，人工明确授权后才 `--apply`，随后再次 doctor。
- `implx` startup 在读取本机安装的 queue skill 后、任何 lane/checkpoint/远端写入前，
  从可定位的 SpecRail 源包调用 doctor `--require-installed`。无法定位 checker、
  lock、源包或返回非 `match` 时停止自动 queue，不能把失败降级为 warning。
- `specrail-implement-queue` 重复声明同一 precondition，保证直接调用时也 fail closed。
  它消费 compact JSON 摘要，不把全部文件哈希正文反复注入父上下文。

如果消费者只有安装后的 `SKILL.md` 而没有可定位的 SpecRail pack/checker，本 issue 的
queue preflight 会明确阻断；把 runtime gate/checker 本身作为全局可执行依赖分发属于后续
独立 issue，不在 GH-172 偷偷引入。

### 6. 文档与 lock 收口

更新 `AGENT_USAGE.md` 和 `CHANGELOG.md`，说明普通 pack check 与 installed doctor 的边界。
三个修改后的 skill 重算入口哈希写入 `skills-lock.json`。本 issue 尚不新增 skill 引用
文件，因此 `files[]` 可保持缺省；GH-174 将首次消费多文件声明并验证完整链路。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-006 B-007 B-020 | shared manifest + integrity result aggregation | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "all_files or mixed or ordering"` |
| B-002 | `resolve_codex_skills_dir()` + CLI target reporting | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "target or codex_home or default"` |
| B-003 B-012 | `not_installed` status + `--require-installed` caller policy | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "not_installed or require_installed"` |
| B-004 B-005 | missing/drift result and exit status | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "missing or drift"` |
| B-008 B-014 B-015 | `validate_skills_lock()` compatible multi-file contract | `python3 -m pytest -q tests/test_evaluate.py -k skills_lock` |
| B-009 | repository/install path containment and symlink rejection | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "escape or symlink or unsafe"` |
| B-010 B-017 B-019 | read-only/idempotent inspection and bounded output | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "read_only or idempotent or output"` |
| B-011 | installer preflight, explicit apply and post-check | `python3 -m pytest -q tests/test_install_codex_skills.py` |
| B-013 | ordinary workflow check remains repo-only | `python3 -m pytest -q tests/test_check_workflow.py -k installed_skill` |
| B-016 | before/after stat snapshot consistency | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k unstable` |
| B-018 | incomplete/error result cannot pass CLI | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "unreadable or interrupted or invalid"` |

## 数据流

```text
skills-lock.json + repo skill files
  -> shared lock validator/manifest
  -> installed integrity library
       -> explicit target | CODEX_HOME/skills | ~/.codex/skills
       -> stable lstat/read/lstat per locked file
  -> status: match | not_installed | invalid
  -> doctor CLI / installer preflight / implx queue preflight
```

所有检查均为本地只读。只有 installer 收到显式 `--apply` 才进入既有写路径，写后重新
走同一 inspect 验证。

## 备选方案

- 把 installed check 接入普通 `check_workflow.py`：拒绝。CI 没有本机安装目录，且
  仓库一致性与运行时部署一致性是两种不同证据。
- 只比较 `SKILL.md`：拒绝。无法支持 GH-174 的 references/scripts，并制造“目录已验证”
  的虚假保证。
- 对整个目录做一个不透明 tree hash：拒绝。无法逐文件报告 drift/missing，也不利于
  稳定兼容与有界诊断。
- 发现 drift 后自动 `--apply`：拒绝。违反 dry-run 默认和人工安装授权。
- 将 doctor 逻辑复制进 installer 与两个 skill：拒绝。会立即产生三套状态和路径语义。

## 风险

- Security: 安装目录可能含用户自建文件或符号链接。checker 只读取 lock 声明的普通文件，
  拒绝符号链接/逃逸，不输出正文；apply 权限没有扩大。
- Compatibility: v1 单文件条目继续合法；新增 `files[]` 是可选闭集扩展。依赖 installer
  dry-run 在已存在 drift 时仍返回 0 的脚本会看到非零，这是 issue 明确要求的 fail-closed
  收紧。
- Performance: 文件数与锁定资产线性相关；当前 14 个入口文件，未来引用仍是小型文本，
  单次本地哈希成本可忽略。queue 只保留汇总，不加载正文。
- Maintenance: 三个消费者共享 library 和 manifest；`check_workflow` 通过 required-file
  与测试保证 checker 没有从 pack 中遗漏。
- Race: 无法对任意外部目录获得事务快照；双 stat 检测可观察变化并 fail closed，不能保证
  阻止恶意同内容替换。该 doctor 是完整性诊断，不是操作系统沙箱。

## 测试计划

- [ ] Unit tests: `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_evaluate.py`
- [ ] Installer tests: `python3 -m pytest -q tests/test_install_codex_skills.py`
- [ ] Workflow integration: `python3 -m pytest -q tests/test_check_workflow.py`
- [ ] Full regression: `python3 -m pytest -q`
- [ ] Pack/spec checks:
      `python3 checks/check_workflow.py --repo . --all-specs &&
      python3 tools/spec_depth_audit.py --spec-dir specs/GH172 --gate`
- [ ] Manual dry-run:
      `python3 tools/check_installed_codex_skills.py --repo . --target-dir <fixture>`;
      校验 match/drift/missing/not_installed 输出与退出码。
- [ ] No-write verification: 对目标目录执行前后文件清单、mtime 和哈希快照，doctor 运行后
      完全一致。

## 回滚方案

回滚新 checker/library、installer 接线、lock 多文件解析、三个 Skill 入口、测试、文档和
三个 skill 哈希即可恢复原行为。新增 `files[]` 尚未由本 issue 的生产 lock 使用；若后续
GH-174 已使用，必须先把其引用内容合回对应 `SKILL.md` 并恢复单文件 lock，不能只删除
validator 支持。回滚不需要修改用户安装目录，且不得自动运行 installer。
