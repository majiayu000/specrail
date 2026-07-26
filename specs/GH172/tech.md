# Tech Spec

## Linked Issue

GH-172

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":172,"complete":true,"paths":["AGENTS.md","AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/installed_skill_integrity.py","checks/specrail_lib.py","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-install/SKILL.md","skills/specrail-workflow/SKILL.md","tests/test_check_workflow.py","tests/test_evaluate.py","tests/test_install_codex_skills.py","tests/test_installed_skill_integrity.py","tools/check_installed_codex_skills.py","tools/install_codex_skills.py"],"spec_refs":["specs/GH172/product.md","specs/GH172/tech.md","specs/GH172/tasks.md"]}
-->

## Product Spec

见 `specs/GH172/product.md`。本设计实现 B-001..B-032；GH-160 的功能行为仍排除在本
issue 外，但其 multi-file skill/lock 实现明确依赖 GH-172。

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
| 活动 session | `AGENT_USAGE.md:80-81` | 文档只提示安装后“可能需要”重启；没有 runtime-owned evidence 绑定当前 session 实际已加载的入口 bytes，磁盘 match 可与 stale loaded instructions 并存。 | queue 必须比较 current-session loaded-entrypoint identity 与同一 lock manifest；host evidence 缺失或 apply 后仍是旧 session 时确定性阻断。 |
| lock 回归 | `tests/test_evaluate.py:140-191` | 直接构造 v1 单文件 lock 验证 `validate_skills_lock()` 的通过与哈希失配。 | 扩充为可选多文件清单、集合闭合和路径安全回归，证明 v1 单文件兼容。 |

## 设计方案

### 1. 兼容扩展 `skills-lock.json`

顶层 `version` 随声明形态变化：纯单文件 lock 保持 `version: 1`；**任一条目声明
`files[]` 时，顶层必须为 `version: 2`**。旧 reader（v1 validator/installer）只接受
`version: 1`，因此会对多文件 lock 直接 fail closed，而不是忽略未知字段、只校验
`SKILL.md` 后误判通过——这正是本 issue 要防的 stale-install 场景。v2 reader 同时
接受 v1 与 v2 lock。每个 skill 的 `path` 与 `computedHash` 语义不变：
它们继续绑定主入口 `skills/<name>/SKILL.md`。每个 skill 条目新增可选
`files[]`，仅声明入口之外的受分发文件：

```json
{
  "name": "specrail-implement-queue",
  "path": "skills/specrail-implement-queue/SKILL.md",
  "computedHash": "sha256:...",
  "mode": "0644",
  "files": [
    {
      "path": "references/runtime.md",
      "computedHash": "sha256:...",
      "mode": "0644"
    },
    {
      "path": "scripts/check-runtime",
      "computedHash": "sha256:...",
      "mode": "0755"
    }
  ]
}
```

v2 的 skill entry 和每个 `files[]` item 都必须有 `mode`，使用四字符字符串闭集
`"0644" | "0755"`：文档/数据/仅由 interpreter 读取的文件显式用 `0644`，需要直接执行的
脚本显式用 `0755`。禁止根据扩展名或 shebang 推断；缺失/其它字符串、JSON number、setuid/
setgid/sticky、group/world-write 或 source actual mode 与声明不符均 fail closed。v1 单入口
条目继续沿用既有 hash-only 兼容语义，不追溯新增 mode；一旦使用 `files[]` 就必须升级 v2，
并为入口和全部 file 显式声明 mode。

`files[].path` 必须是相对于该 skill 目录的 POSIX 路径，禁止绝对路径、空路径、
`.`、`..`、反斜线、重复路径和 `SKILL.md` 重复声明。仓库 validator 枚举 skill
目录中的普通文件；集合必须恰好等于入口加 `files[]`。**目录本身不能作为 `files[]`
条目**（symlink、socket 等非普通文件同样非法并 fail closed），但 `files[]` 条目
可以包含目录成分（例如 `references/runtime.md`）：其父目录必须是受 containment 检查
的真实目录，不得为符号链接，也不得逃出 skill 根。因此多文件 skill 可以有嵌套结构，
只是嵌套目录本身不是被哈希的分发资产。未声明 `files` 的现有条目
仍只信任 `SKILL.md`，因此 B-015 保持兼容而不会扩大信任面。

shared manifest 必须从入口与 `files[]` 的规范化相对路径确定性派生
`structural_directories`：它恰好是每个声明文件的所有非空严格父路径前缀。例如
`references/runtime.md` 只派生 `references/`；调用方不能直接声明或额外注入该集合。
repo validator、installed doctor 与 installer 共用这一派生结果：structural entry 必须是
skill root 内的真实目录、逐段 no-follow containment 检查通过，且其递归 namespace 最终只含
声明 regular files 与更深 structural directories。必要父目录因此不会被误报为
`undeclared`，但同级 stale directory、空的非必要目录、symlink 或特殊项仍 fail closed。

顶层 completeness discovery 必须枚举 `skills/*/SKILL.md` 对应的所有直接子目录，
且 `SKILL.md` 必须是普通文件；集合与 lock 的 skill 条目精确相等。不得继续使用
`skills/specrail-*/SKILL.md` 前缀过滤，因为 `skills/implx` 已是受分发 skill。测试除
既有 `implx` 外还要创建一个无 `specrail-*` 前缀的顶层 skill fixture，证明整项缺锁会
fail closed，而不是只检查已被 lock 点名的目录内部闭集。

在 `checks/specrail_lib.py` 提供共享的不可变 lock manifest 数据结构和 loader。
`validate_skills_lock()`、installer 与 installed doctor 都消费同一规范化结果；v2 manifest
把每个文件的 identity 定义为 `(relative_path, sha256, normalized_mode)`，
不再各自解析 JSON。错误聚合保持稳定排序。

### 2. 只读完整性 library

新增 `checks/installed_skill_integrity.py`：

- `resolve_codex_skills_dir(explicit_target, environ, home)` 实现唯一目标解析：
  explicit → `$CODEX_HOME/skills` → `~/.codex/skills`；
- `inspect_installed_skills(repo, target)` 先调用共享 lock validator/loader，再对每个
  manifest 文件构造安装目标；
- 安装根不存在时返回整体 `not_installed`，不创建目录；
- 安装根存在时，每个文件返回 `match | drift | missing | unsafe | unstable`，
  结果包含 skill、相对文件、目标路径、expected/actual hash、v2 的 expected/actual
  normalized mode、expected/actual size、`hash_status`、`bytes_read` 和非敏感 reason；
  hash 相同但 mode 不同仍是 `drift`。只有哈希在安全 read-work boundary 内完整结束时
  `actual_hash` 才是 digest；size/安全边界已先确定失败时必须为 JSON `null`，不得伪造值；
- 路径检查使用 `lstat` 与受控根边界，拒绝 skill 目录、父组件或文件符号链接；
  inspection 从 stable filesystem anchor 逐段打开 target root、skill root 与 manifest
  派生的全部 structural directories，保存每个 pathname component 对应 descriptor 的
  `(st_dev, st_ino, type, mode, size, mtime_ns, ctime_ns, nlink)` namespace snapshot。namespace
  枚举和 declared-file open 只相对这些所持 dirfd，不能在枚举后重新从 pathname 打开
  replacement tree。完整 inspection 结束时从同一 anchor rewalk 每个目录 pathname，并同时
  final `fstat` 所持 descriptor；pathname identity 或 namespace metadata 任一变化即整体
  `unstable`。读取 declared file 必须用 no-follow 描述符：逐段
  `openat(..., O_RDONLY|O_NOFOLLOW|O_DIRECTORY|O_CLOEXEC)` 打开目录成分，最终文件用
  `openat(..., O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC)` 打开。final open 后必须立即
  `fstat`，只有 `S_ISREG` 才能开始哈希；FIFO、socket、device 或其它 special file 直接
  `unsafe`/`unstable`，不得等待 writer 或读取内容；首次 `fstat` 还必须要求
  `st_nlink == 1`，否则在读取前返回 `unsafe_hardlink`。哈希只对该 fd 计算，并用同一 fd 的
  前后 `fstat` 比较，snapshot identity 包含 inode/device/type/size/mtime_ns/ctime_ns 与
  `stat.S_IMODE(st_mode)`/`st_nlink`，final `st_nlink` 也必须保持 1。仅靠读取前后的
  `lstat` 不够：文件可能被换成 symlink，或换成 FIFO
  令阻塞式 open 永远到不了 fstat。fd 与 lstat 的 inode/device 不一致，或前后 fstat 的
  inode/device/size/mtime/ctime 变化，返回 `unstable` 且不输出内容；同尺寸原位改写后
  恢复 mtime 仍会改变 POSIX ctime，必须稳定拒绝；
- shared manifest loader 在对 source 做相同的 no-follow、single-link、pre/post snapshot
  校验时记录 `expected_size`，并固定
  `MAX_LOCKED_FILE_BYTES = 8 * 1024 * 1024`；该 cap 属于 repo contract，CLI flag、environment
  或 caller 都不能提高。source initial size 超 cap 时 lock validation 直接失败。installed
  initial `fstat` 的 size 超 cap 或不等于 `expected_size` 时在哈希前返回
  `drift`/`size_mismatch`，`actual_hash=null`、`hash_status=not_computed_size_mismatch`、
  `bytes_read=0`。size 合法时 bounded reader 最多请求 `expected_size + 1` bytes：不足、
  出现第 `expected_size+1` byte、final size/mtime/identity 变化或持续 append 都返回
  `unstable`；任何单文件 inspection 的读取工作因此都不超过 cap 加一个探测 byte；
- 只读取 lock 声明且 single-link 的 regular files；同时有界枚举每个受锁 skill 安装目录的 namespace。
  规范化路径若属于 shared manifest 派生的 `structural_directories`，仅在该项为 no-follow
  containment 内的真实目录时跳过 undeclared 计数并继续枚举；任何声明文件或 structural
  directory 之外的文件、目录或特殊项都使该 skill 判为 `undeclared` 并令整体 `invalid`
  （Codex skill 可以按
  `SKILL.md` 里的相对路径加载资源，所以"入口匹配 + 残留旧 reference"仍可能把未校验
  指令喂进 queue preflight）。枚举只进入 manifest 派生的 structural directories；遇到
  undeclared directory 把其 raw-byte relative path 作为一个 subtree root 后立即停止向下，
  不统计其 descendants。library 固定 `MAX_NAMESPACE_VISITS = 4096`，caller/CLI/env 不能提高；
  读取第 4097 项即停止整个 traversal。lock validation 复用同一常量做 cardinality gate：
  全部 skill 的入口、`files[]` 声明文件与派生 structural directories 的总数超过
  `MAX_NAMESPACE_VISITS` 时 lock 直接 invalid，因此 installer 可分发的 manifest 对应的
  完全匹配安装树永远不会触发 truncation；测试必须覆盖恰好 4096（match）与 4097
  （lock invalid）的 exact-boundary fixtures。命中 cap 时返回
  `traversal_truncated=true`、`undeclared_total_exact=false`、
  `undeclared_total=null`、`undeclared_observed=4097`、
  `undeclared_omitted=null` 与固定空 `undeclared_sample`，整体 `invalid`。未命中 cap 时
  `undeclared_total_exact=true`、total/omitted 为 exact integer，并按 POSIX raw relative
  path bytes 排序。内部 traversal 一律使用 bytes path；human/JSON 的 path display 对每个
  component 仅保留 ASCII unreserved `[A-Za-z0-9._-]`，其它 byte 用大写 `%HH`，`/` 只作为
  component separator。sample 最多 50 项且 escaped ASCII 合计最多 8192 bytes；非 UTF-8
  name 因此不会 decode 失败或产生非法 JSON。不得读取或输出未声明文件正文；
- 返回结构化 Python 结果与稳定 JSON 字典，library 不调用 `sys.exit()`、不写文件。
  library 的标准序列化结果不得携带无界完整路径数组。需要排障时，CLI 仅在调用方显式
  传入 `--undeclared-artifact <new-file>` 后，才把**同一次有界 traversal** 的
  exact/truncated metadata、escaped display 与每项无 padding base64url raw path 写入权限
  `0600` 的新 JSON artifact；它不得为追求“完整清单”继续递归/扫描。CLI 从 stable
  filesystem root/cwd anchor 逐段以 `openat(O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)` 打开已经存在的
  parent，验证其 descriptor ancestry 不在稳定 target-root descriptor 内，最后只以该 parent
  dirfd 上的 `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` 创建 regular file。写前/写后都
  rewalk pathname 并比较 parent inode chain；parent symlink/rebind、目标已存在、无法证明
  containment 或 post-create identity/mode 不一致时 fail closed，并只经所持 artifact-parent
  fd 清理新文件。`resolve()`、pathname precheck 或 final-name exclusive create 不能独立授权。
  queue/`implx` 不得传该参数，因此 runtime preflight 始终只消费有界摘要。

整体状态规则：

- 目标根不存在：`not_installed`；
- 根存在、全部文件 hash 与 v2 exact mode 匹配，且 namespace 除安全 structural directories 外无 undeclared 项：
  `match`；
- 根存在且出现其他状态（含 `undeclared`、`unsafe_hardlink`、`traversal_truncated` 或
  durable installer transaction record）：`invalid`；transaction record 另给
  `recovery_required=true`，不得由 doctor 自动修改。

唯一窄例外是 installer 在同一 apply 进程内、exchange 后运行的 post-check：installer
构造不可序列化 `ActiveInstallTransaction` capability，持有 target-root fd 与安全打开的
record fd，并绑定其 `(st_dev, st_ino, ctime_ns)`、transaction ID、canonical destination、
new manifest digest。library 的 internal-only inspect 入口只在 capability 与当前 held
descriptor/record bytes 全匹配时，把这一条 record 视为 authenticated structural entry；
它仍验证 new destination 的完整 namespace/hash/mode。额外 record、fd/path/inode/ctime/
transaction/manifest 任一不符仍 `recovery_required`。public library、doctor CLI、JSON、
queue/agent 无参数可构造或反序列化该 capability，故外部检查相同现场继续 fail closed。

### 3. 独立 doctor CLI

新增 `tools/check_installed_codex_skills.py`，参数：

- `--repo`：SpecRail 源仓库；
- `--target-dir`：显式覆盖安装根；
- `--json`：输出机器可读结果；
- `--require-installed`：把 `not_installed` 从显式 skipped 变为非零阻断，供 queue 使用。
- `--undeclared-artifact <new-file>`：显式导出同一次 bounded traversal 的稳定诊断；
  stable no-follow parent dirfd-relative create-only，不得位于安装目标内，默认与 queue
  路径均不启用。

默认退出码：`match=0`、`not_installed=0`、`invalid=1`、lock/运行错误 `=1`。
带 `--require-installed` 时只有 `match=0`。人类文本与 JSON 都按 skill path 排序，
未声明项只输出上述 exact/truncated metadata、有界样本与 raw-byte-safe display，不输出正文
或环境变量内容。显式 artifact 也不能扩大 traversal work。

`checks/check_workflow.py` 只把新 library/CLI 加入 `REQUIRED_FILES` 并继续执行仓库
lock 校验；它不调用 doctor，CI 因此不依赖本机安装状态。

### 4. installer 接线

`tools/install_codex_skills.py` 删除自己的目标解析与只含入口哈希的数据模型，改用共享
manifest 与 integrity library：

1. 解析/验证仓库 lock；
2. 运行只读 pre-install inspect；
3. dry-run 打印现状和安装计划，不写文件；目标不存在成功，目标存在但 drift/missing
   返回非零并给出 `--apply` 需要人工授权的说明；
4. `--apply` 只有在用户显式传入时执行同步写入；pre-install drift 是待修复状态，
   不阻止已授权 apply。不得再用 `shutil.copytree(..., symlinks=False)` 或任何会在验证后
   按路径重开并跟随 source symlink 的 whole-directory copy；
5. apply 开始时从 stable filesystem root/home anchor descriptor 逐段处理目标路径：已有
   component 只用 `openat(..., O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)`，仅在已授权 apply 下才可
   用 `mkdirat` 创建缺失 component，并立即从同一 parent fd no-follow 打开；每一级保存
   `(st_dev, st_ino)`，最终持有 target root fd。`Path.resolve()`、`exists()`、pathname
   `mkdir/rmtree/replace` 只能用于非安全展示，不参与写入或 containment 判定。source/target
   重叠检查也以已打开 descriptor 的 inode ancestry 为权威；
6. installer 在 target root fd 下以不可预测名称、create-exclusive 建立 staging，并为每个
   skill 使用固定、collision-safe 的 transaction-record basename
   `.specrail-install-txn-<sha256(skill-name)>.json`。record 必须 create-exclusive、`0600`、
   closed JSON，绑定 transaction id、destination/staging 名、old/new manifest identity 与
   `prepared` phase；写入后依次 fsync staging files/directories、record fd 与 target-root fd。
   record 已存在即返回 `recovery_required`，不得覆盖。destination 不存在时只允许单次
   `renameat2(RENAME_NOREPLACE)` commit；destination 已存在时只允许同一 target-root dirfd
   上的单次 `renameat2(RENAME_EXCHANGE)`（或语义完全等价、保证 canonical name 始终存在的
   原子 exchange）交换 staging 与 destination，禁止
   `destination → backup → staging → destination` 两次 rename。缺少 exchange primitive
   时已存在 destination 的 apply 明确 unsupported/fail closed，不能退回有缺口的算法。
   exchange 后立即 fsync target-root fd；此时 destination 是新 tree，staging 名指向 old tree。
   递归 cleanup 每一层都从已打开 directory fd no-follow 枚举并用 `unlinkat`/`rmdir`，不得
   退回 pathname `rmtree`。

   每次 installer/doctor preflight 都从 target-root fd 检查上述 fixed record。record 本身
   在解析任何 JSON 前必须先安全打开：仅以 target-root dirfd 上的
   `openat(O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC)` 打开，立即 `fstat` 并要求
   `S_ISREG`、`st_nlink == 1` 且 size 不超过固定 `MAX_TXN_RECORD_BYTES = 64 * 1024`；
   symlink、FIFO、device、多硬链或超限 record 一律在读取前 fail closed 保留现场，读取本身
   也是不超过该 cap 加一个探测 byte 的 bounded read。doctor/dry-run/
   queue 只报告并阻断；只有新的显式 `--apply` 可恢复。读取 closed JSON 后、任何 recovery
   object open/分类/清理前，先按 manifest 与 transaction id 重新计算并验证路径字段：
   `destination` 必须逐 byte 等于当前 locked skill 的 canonical name；`staging` 必须逐 byte
   等于 `.specrail-install-staging-<skill-sha256>-<transaction-id>`，其中两个插值均为固定长度
   lowercase hex。两者都必须是单一 ASCII basename，拒绝空值、`.`、`..`、`/`、反斜线、
   NUL、非规范编码、相等或与 record basename 相等。随后仅在所持 target-root dirfd 下以
   `openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS|RESOLVE_NO_MAGICLINKS)`，或可证明等价的
   single-component `openat(O_NOFOLLOW)` + fd ancestry/identity 复核打开；平台无法提供
   beneath-root 等价保证时 recovery fail closed。伪造/矛盾 record 保留现场，且不得读取、
   删除或改写 target root 外对象。通过该 gate 后才以 record 的 old/new manifest identities
   对两棵 tree 分类。若
   destination 完整匹配 old identity，说明 exchange 未发生：无论 staging 等于 new，还是
   step 7 中被 kill 留下的不完整/不匹配 tree，都属于可恢复的 pre-exchange 状态，只经所持
   target-root fd 安全删除 staging 与 record 并保持 old，后续显式 apply 不得被永久阻断；
   若 destination 完整匹配 new identity，说明 exchange 已发生：无论 staging 等于完整 old
   tree，还是清理阶段被 kill 留下的部分删除残留（甚至任意不匹配内容），都属于可恢复的
   post-exchange cleanup 状态，只经所持 target-root fd 恢复递归删除 staging 残留，完成
   post-check 后清理 record；staging 残留的分类不要求匹配 old identity，因为 exchange 后
   canonical destination 的正确性只由 new identity 证明。若 staging 已不存在，则在
   destination 完整匹配 new identity 时判定 old cleanup 已完成并删除 record，或完整匹配
   old identity 时判定 transaction 未生效/已 rollback 并删除 record；只有 destination 既不
   匹配 old 也不匹配 new identity，或任一对象不安全时才保留现场并 fail closed，
   不得猜测删除或交换。恢复的 cleanup、exchange rollback、record 删除与每个阶段的 fsync 都只用
   stable descriptor chain。由此任意 kill/power-loss 点 canonical destination 都存在，且
   下次显式 apply 能确定恢复。
   commit 前后都从 stable anchor no-follow 重走 target pathname，并要求每一级 inode 与持有
   descriptor chain 一致；root/parent 被换成 symlink、rename/rebind、任一 component/type
   漂移或 rewalk 失败时，必须通过原 target-root fd 清理未交换 staging，或按 durable record
   与 old/new identity 执行 atomic exchange rollback 后 fail closed。
   替代 symlink 指向的 external sentinel 以及任何 target-root 外路径必须保持零写入/零删除；
7. installer 按 shared manifest 创建 staging skill tree 与派生 structural directories，并从
   已打开的 repo/skill directory fd 逐段 no-follow 打开每个声明 source：final component 使用
   `O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC`，立即 `fstat` 且确认 regular file 后，直接从
   **同一 source fd** 复制到由 staging-dir fd create-exclusive 打开的 destination fd 并同步
   计算/核对 lock hash。复制复用 shared manifest 的 `expected_size` 与 8 MiB cap：initial
   size 不同/超限时零读取，正常路径最多读取 `expected_size + 1` bytes，short/extra/growth
   均在 commit 前失败。v2 file 随后在同一 destination fd 上 `fchmod` 为声明的
   `0644|0755`、`fsync`、`fstat` 并校验 exact mode；文件创建时的 umask 不得改变最终 mode。
   source initial `fstat` 还必须在读取前验证 `st_nlink == 1`，final `fstat` 继续为 1 且
   mode 未改变。source hard link/symlink/special file、hash/mode 不匹配
   或 pre/post snapshot 变化时通过 target-root fd 清理 staging/record 并失败，不得读取 escape
   target，也不得替换现有 destination。所有 source 完整稳定后，还必须在
   `RENAME_EXCHANGE`/`RENAME_NOREPLACE` 前自底向上 `fsync` 每个已填充的 structural
   directory descriptor 与 staging root fd：仅 fsync 文件不会使其目录项 durable，step 6
   对 staging 目录的 fsync 发生在填充前，不能替代本次填充后的目录 fsync。之后才进入
   descriptor-relative
   commit；复制对象只来自 manifest，不从未声明目录枚举推断；
8. apply/exchange 后沿所持 target-root fd 重新运行完整 inspect，再完成 anchor-to-path identity rewalk；
   该 internal post-check 必须传入上节定义的 `ActiveInstallTransaction` capability，仅将
   exact held transaction record 作为 authenticated structural entry；public doctor/queue
   在相同现场仍返回 `recovery_required`。只有 new destination 整体 `match`、所有 v2 mode
   精确、pathname 仍绑定同一 descriptor chain 才成功。失败时
   在 transaction record 保持 durable 的前提下用第二次 atomic exchange 回滚；rollback/cleanup
   失败必须保留 record 并显式报错，不能把部分安装表述为成功。成功后先清理 exchange 留下的
   old tree 并 fsync target root，最后 unlink record 再 fsync；中断时按 step 6 恢复。

逻辑安装单位仍是整个 skill，但物理 copy 是 manifest-declared files + derived structural
directories 的闭集，而不是跟随目录树。这样未来引用/脚本随 skill 分发且 source race 不会
读取/落盘逃逸内容；target race 也不能把 staging/replacement 重定向到授权根外。post-check
只信 shared manifest 的 hash + v2 mode，并使用同一 stable target descriptor chain。本 issue
不扩大 apply 授权，也不自动调用 apply。

### 5. queue/install Skill 接线

- `specrail-install` 的 `doctor` 路由直接调用新 checker；`install_local_skills`
  先 doctor/dry-run，人工明确授权后才 `--apply`，随后再次 doctor。
- `implx` startup 在读取本机安装的 queue skill 后、任何 lane/checkpoint/远端写入前，
  从可定位的 SpecRail 源包调用 doctor `--require-installed`。无法定位 checker、
  lock、源包或返回非 `match` 时停止自动 queue，不能把失败降级为 warning。
- `specrail-implement-queue` 重复声明同一 precondition，保证直接调用时也 fail closed。
  它消费 compact JSON 摘要，不把全部文件哈希正文反复注入父上下文。
- 磁盘 doctor 之外，queue preflight 必须消费 host/runtime 在 skill load 时捕获、调用方
  不可写的 closed `loaded_skill_evidence`：`session_instance_id`、`captured_at`、
  `lock_manifest_sha256`。`lock_manifest_sha256` 的 preimage 是版本化的 canonical manifest 编码，而不是
  `skills-lock.json` 的 raw bytes：normalized shared manifest（每 skill 的 name、每文件的
  `(relative_path, sha256, normalized_mode)`，按 skill/path 字节序排序）序列化为带
  encoding-version tag 的 canonical JSON（UTF-8、键排序、无多余空白），对该字节串取
  sha256。v1 hash-only 条目在 canonical 编码中把 `normalized_mode` 固定编码为 JSON
  `null`：不得省略该字段，也不得从磁盘或扩展名推断 mode；v2 条目编码声明的
  `"0644"|"0755"` 字符串。固定 test vectors 必须同时覆盖 v1（`null`）与 v2 两种
  条目，证明 checker 与 provider 得到相同 `lock_manifest_sha256`。repo validator、
  doctor 与 host evidence provider 必须共享同一实现与固定
  test vectors；对 raw lock bytes、非规范化 JSON 或派生字段（如 `expected_size`）哈希
  都不符合本契约。evidence 还包含按 skill/path 排序的
  `loaded_entries[{entry_role,skill,origin,resolved_path,sha256}]`。`origin` 是闭集
  `{source_checkout, installed_target}`，entry role 与 origin 的允许组合也是闭合的：
  唯一 router role 必须为 `source_checkout`，其 `resolved_path` 必须在当前 source repo
  descriptor 下精确等于 shared manifest 的 `skills/specrail-workflow/SKILL.md` source path，
  loaded sha256 与 lock source identity 相同；`implx` 与 queue entrypoint 必须为
  `installed_target`，resolved path 分别精确位于 doctor 选中 target 的对应 manifest path，
  sha256 同时匹配 lock 与 disk doctor。**required role set 按 invocation route 闭合
  派生**：经 source router bootstrap 委派 `implx`/queue 时要求 router 加实际委派链上
  已加载的 installed entrypoints；直接调用 `specrail-implement-queue` 时只要求 queue
  entrypoint（`installed_target`）在场并匹配，未在该 route 加载的 router/`implx` 不作为
  missing evidence。任何 route 下执行 queue 动作的 entrypoint 都必须在场，且 evidence 中
  出现的每个 entry 无论是否 required 都必须满足上述 role/origin/path/hash 约束。所有
  entry 共享同一个
  `lock_manifest_sha256`，evidence 的 session identity 必须等于 current host session。
  source router 不要求落在 installed target；其它 role 不得声明 `source_checkout`，也不得
  用 source checkout 的 matching bytes 替代 installed evidence。CLI flag、environment、
  checkpoint、PR body、agent 自述或磁盘 mtime 都不能构造/覆盖该 evidence。host 不提供可信
  evidence、字段缺失、role/origin 重复或越界、session/manifest/path/hash 漂移时返回
  `session_restart_required` 并在任何 lane/checkpoint/远端动作前停止。
- `checks/installed_skill_integrity.py::validate_loaded_skill_evidence()` 与
  `tools/check_installed_codex_skills.py --loaded-skill-evidence-gate` 提供 deterministic
  gate：同时消费 runtime provider
  交付的 closed evidence envelope、provider-attested current session/route、shared lock
  manifest 与 doctor 的完整 closed JSON（含 target identity/status），逐项执行 required
  role set、origin/path/hash/session/freshness/manifest/doctor cross-binding。任一输入
  missing/malformed/stale/route-inconsistent 都返回 closed
  `decision: blocked, reason_id: session_restart_required`；只有全部精确匹配才返回
  `decision: allowed, allowed_actions: [open_queue_lane]`。CLI 不接受 caller 覆盖
  session/route/role/path/hash，也不从 checkpoint/env/PR body 补字段；provider transport
  与 trust root 属外部 prerequisite。implx/queue 只能消费 gate verdict，不能重新解释 raw
  evidence；raw envelope 不进入父上下文。
- 成功 `--apply` 只证明 disk post-check；它不得更新 current session 的 loaded evidence。
  因而已加载旧 bytes 的同一 session 必然继续阻断，必须由用户/host 启动新 session，重新加载
  entrypoints 并产生 fresh matching evidence。host/runtime evidence provider 是自动 queue
  availability 的外部 prerequisite；未部署时可以继续普通 doctor/install，但不能把 queue
  静默降级为“磁盘 match 即可”。

仅靠"更新后的 installed skill 会自己调用 doctor"是不够的：stale 安装副本里根本没有
这段指令，第一次 drain 仍会静默通过。因此 bootstrap 必须来自 installed queue skill
之外，两层同时生效：

1. **lock 版本闭锁**（见 §1）：多文件 lock 为 `version: 2`，stale v1 reader 读到即
   fail closed，无法把旧安装副本判为有效。
2. **源侧 bootstrap**：仓库 `AGENTS.md` 的 Long Queue Guardrails 与
   `skills/specrail-workflow/SKILL.md`（路由器，源包内、先于分派到 installed queue
   skill 执行）要求在任何 queue/implx 委派之前先运行
   `tools/check_installed_codex_skills.py --require-installed`；未 `match` 时不得
   委派给 installed queue skill。路由器这一层不依赖用户已安装副本的新旧。
3. **活动 session 闭锁**：上述源侧 bootstrap 在委派前还验证 runtime-owned
   `loaded_skill_evidence`；source router 绑定 source checkout manifest，installed
   `implx`/queue 绑定 installed target，二者 origin 不混用。这一步绑定当前 agent 已加载
   bytes，而不是重新读取磁盘后自证。`--apply` 后必须新建 session，直到 fresh evidence
   与 lock/doctor 同一 manifest 匹配。

如果消费者只有安装后的 `SKILL.md`，没有可定位的 SpecRail pack/checker，或 host 不提供可信
current-session loaded identity，本 issue 的 queue preflight 会明确阻断；把 runtime
gate/checker/provider 本身作为全局可执行依赖分发属于后续独立 issue，不在 GH-172 偷偷引入。

### 6. 文档与 lock 收口

更新 `AGENT_USAGE.md` 和 `CHANGELOG.md`，说明普通 pack check 与 installed doctor 的边界。
三个修改后的 skill 重算入口哈希写入 `skills-lock.json`。本 issue 尚不新增 skill 引用
文件，因此 `files[]` 可保持缺省。GH-160 已计划新增
`skills/specrail-implement-queue/references/context-budget.md`，GH-174 也将拆分同一
multi-file skill；两者都依赖 GH-172，并必须在各自实现中把该 skill 的完整文件清单迁移
到 v2 lock。二者谁先实施，谁就是首个生产 multi-file consumer。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-006 B-007 B-020 | shared manifest structural-parent derivation + integrity result aggregation | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "all_files or nested_parent or undeclared or mixed or ordering"` |
| B-002 | `resolve_codex_skills_dir()` + CLI target reporting | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "target or codex_home or default"` |
| B-003 B-012 | `not_installed` status + `--require-installed` caller policy | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "not_installed or require_installed"` |
| B-004 B-005 B-022 | missing/hash-or-mode drift result and exit status | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "missing or drift or mode"` |
| B-008 B-014 B-015 B-022 | `validate_skills_lock()` compatible multi-file/hash/mode contract + all top-level skill discovery | `python3 -m pytest -q tests/test_evaluate.py -k "skills_lock or mode or unprefixed_skill"` |
| B-009 B-019 | repository/install containment + no-follow/nonblocking regular-file open | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "escape or symlink or fifo or special or unsafe or undeclared_artifact"` |
| B-010 B-017 | read-only/idempotent inspection, bounded output and explicit artifact export | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "read_only or target_snapshot_no_write or idempotent or output or undeclared_artifact"` |
| B-011 B-021 B-022 | descriptor-anchored installer transaction + manifest-only same-fd copy/mode + post-check | `python3 -m pytest -q tests/test_install_codex_skills.py -k "apply or source_race or target_parent_swap or target_root_swap or symlink or special or mode or umask"` |
| B-013 | ordinary workflow check remains repo-only | `python3 -m pytest -q tests/test_check_workflow.py -k installed_skill` |
| B-016 | before/after stat snapshot consistency including file ctime | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "unstable or restored_mtime"` |
| B-018 | incomplete/error result cannot pass CLI | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "unreadable or interrupted or invalid"` |
| B-023 | deterministic loaded-evidence gate + AGENTS/router/implx/queue current-session preflight | `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_check_workflow.py -k "loaded_skill or session_restart or route or origin"`；disk match + stale loaded sha → blocked before lane/checkpoint |
| B-024 | doctor CLI stable no-follow artifact-parent descriptor transaction | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "artifact_parent or undeclared_artifact"` |
| B-025 | installer durable transaction record + atomic exchange/recovery + internal post-check capability | `python3 -m pytest -q tests/test_install_codex_skills.py -k "exchange or recovery or post_check_capability or external_recovery_required or kill or power_loss"` |
| B-026 | raw-byte namespace identity/order + percent/base64url JSON display | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "non_utf8 or raw_bytes"` |
| B-027 | initial/final same-fd `st_nlink == 1` enforcement | `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_install_codex_skills.py -k hardlink` |
| B-028 | structural-only traversal + fixed global visit cap/truncation | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "undeclared_directory or traversal_cap or truncated"` |
| B-029 | loaded evidence role/origin closed union：source router 对 source manifest，installed entries 对 doctor target | `python3 -m pytest -q tests/test_check_workflow.py -k "loaded_skill_origin or source_router or installed_entrypoint"` |
| B-030 | held root/structural dirfd namespace snapshot + end-of-inspection pathname/inode revalidation | `python3 -m pytest -q tests/test_installed_skill_integrity.py -k "structural_directory_rebind or structural_directory_mutation"` |
| B-031 | fixed source/file-size cap + expected-size precheck + bounded `expected_size+1` reader | `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_install_codex_skills.py -k "size_mismatch or file_size_cap or append_growth or read_budget"` |
| B-032 | recovery record canonical basename validation + beneath-root descriptor opens | `python3 -m pytest -q tests/test_install_codex_skills.py -k "recovery_record_path or recovery_escape or recovery_basename"` |

## 数据流

```text
skills-lock.json(path + hash + v2 normalized mode) + repo skill files
  -> shared lock validator/manifest(file identity + structural parents)
  -> installed integrity library
       -> explicit target | CODEX_HOME/skills | ~/.codex/skills
       -> held root/structural dirfds + namespace/path binding snapshots
       -> immediate regular-file + nlink=1/expected-size fstat
       -> bounded same-fd hash/mode + final file/directory revalidation
       -> raw-byte namespace + structural-only descent + fixed visit cap
  -> status: match | not_installed | invalid
  -> doctor CLI / installer preflight

runtime-owned current-session loaded entrypoint identity
  -> source_checkout router bound to repo manifest
  -> installed_target implx/queue bound to doctor target
  + installed doctor match on the same lock manifest
  -> implx/queue preflight | session_restart_required

explicit --apply authorization
  -> stable anchor -> no-follow target descriptor chain
  -> dirfd-relative staging + same-fd copy/fchmod
  -> validated single-basename txn paths + beneath-root recovery
  -> durable txn record + atomic exchange/recovery/cleanup
  -> anchor-to-path inode rewalk + installed inspect
```

所有检查均为本地只读。只有 installer 收到显式 `--apply` 才进入既有写路径，写后重新
走同一 inspect 验证；target pathname 不是写入 authority。

## 备选方案

- 把 installed check 接入普通 `check_workflow.py`：拒绝。CI 没有本机安装目录，且
  仓库一致性与运行时部署一致性是两种不同证据。
- 只比较 `SKILL.md`：拒绝。无法支持 GH-174 的 references/scripts，并制造“目录已验证”
  的虚假保证。
- 对整个目录做一个不透明 tree hash：拒绝。无法逐文件报告 drift/missing，也不利于
  稳定兼容与有界诊断。
- 发现 drift 后自动 `--apply`：拒绝。违反 dry-run 默认和人工安装授权。
- 将 doctor 逻辑复制进 installer 与两个 skill：拒绝。会立即产生三套状态和路径语义。
- 对 target 先 `resolve()`/`lstat()` 再用 `Path.replace()`/`shutil.rmtree()`：拒绝。
  precheck 与 pathname 写入之间可发生 parent/root symlink swap，必须以稳定 descriptor
  chain 和 dirfd-relative transaction 作为写入 authority。
- v2 仍只锁 hash、让 copy/umask 决定权限：拒绝。同字节文件失去 executable bit 会令
  分发脚本不可执行，而 hash-only doctor 会静默误判 match。
- 磁盘 doctor `match` 后继续复用当前 session：拒绝。active session 可能已把旧入口加载到
  context；没有 runtime-owned loaded identity 时只能阻断并要求新 session。
- 把 source router 也限制在 installed target：拒绝。source bootstrap 本来就在 checkout
  中先于 installed skill 执行；必须以 closed role/origin 分支分别绑定 repo manifest 与
  doctor target。
- 以两次 atomic rename 模拟替换：拒绝。两个 syscall 之间 crash 会让 canonical destination
  缺失；existing destination 必须使用 exchange 和 durable recovery record。
- size mismatch 后仍读取到 EOF 以填充 `actual_hash`：拒绝。大文件或持续 append 可令每个
  queue preflight 卡住；必须返回显式未计算状态并保持固定 read budget。
- 为 exact undeclared count/artifact 递归扫描所有 descendants：拒绝。攻击者可制造无界 tree；
  undeclared directory 作为 subtree root，global cap 命中即稳定 truncated invalid。

## 风险

- Security: 安装/source 目录可能含用户自建文件、symlink、FIFO 或其它 special file。
  checker 与 installer 只从 no-follow/nonblocking fd 读取 lock 声明且经 immediate fstat 确认的
  single-link regular files；structural directories 由 manifest 派生而非 caller 声明；
  directory descriptor/path binding 持续到 inspection 结束；artifact parent 与 recovery
  object 也使用 stable no-follow/beneath-root descriptor transaction；拒绝 symlink/hardlink/
  forged-record 逃逸且不输出正文，apply 权限没有扩大。
- Compatibility: v1 单文件条目继续合法；v2 `files[]` 要求显式 `0644|0755` mode。依赖 installer
  dry-run 在已存在 drift 时仍返回 0 的脚本会看到非零，这是 issue 明确要求的 fail-closed
  收紧。
- Performance: 声明 source/installed file 受固定 8 MiB 逐文件 cap 与
  `expected_size + 1` reader 限制；size mismatch 不执行哈希。undeclared namespace 只进入有限
  structural directories、遇到未声明目录不递归，并由 4096-entry global cap 硬限制。queue 只保留汇总，
  不加载正文。
- Maintenance: 三个消费者共享 library 和 manifest；`check_workflow` 通过 required-file
  与测试保证 checker 没有从 pack 中遗漏。
- Diagnostics: 标准输出和显式 artifact 都受 4096 visits、50 项/8192 bytes 上限；非 UTF-8
  path 使用 raw-byte identity、percent display/base64url artifact。artifact 经 stable parent fd
  create-only，queue 不创建该 artifact。
- Race: source same-fd pre/post fstat + expected hash/mode 检测可观察变化并 fail closed；
  nonblocking final open 防 FIFO 卡死。target 写入从 stable anchor 建立并保持 no-follow
  descriptor chain，所有 staging/replace/rollback/cleanup 都相对所持 fd，commit 前后重走
  pathname 验证 inode binding，因此 parent/root swap 只能令事务失败，不能把写入重定向到
  外部路径。atomic exchange 保持 canonical destination，durable record 令后续显式 apply
  能区分 exchange 前后状态。不能保证阻止恶意同内容、同 mode 的 source 替换；该 doctor 是
  完整性诊断，不是操作系统沙箱。
- Runtime prerequisite: repo doctor 不能观察活动 agent context；host/runtime 必须提供
  current-session loaded-entrypoint evidence。缺该能力时 queue 明确 unavailable，而不是退回
  磁盘-only success。
- Post-preflight asset load: doctor `match` 与 loaded-entrypoint evidence 都是 preflight
  时点保证；长时 queue 在 preflight 之后按需 open/execute 的 `files[]` 分发资产（reference/
  script）若在该间隙被 writable target 上的写者替换，本 issue 的 gate 不阻断。对每个
  分发资产在实际 load/execute 边界绑定 runtime evidence 或 verified snapshot 需要 host
  runtime 能力，与 loaded-entrypoint provider 同属外部 prerequisite，留待后续独立 issue；
  本 issue 不得声称提供 load-time 逐资产连续保证。

## 测试计划

- [ ] Unit tests: `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_evaluate.py`
- [ ] Coverage gate:
      `python3 -m pip install --disable-pip-version-check coverage==7.15.2 &&
      python3 -m coverage erase &&
      python3 -m coverage run --branch
      --source=checks.installed_skill_integrity,tools.check_installed_codex_skills
      -m pytest -q tests/test_installed_skill_integrity.py &&
      python3 -m coverage report
      --include='checks/installed_skill_integrity.py,tools/check_installed_codex_skills.py'
      --fail-under=80 &&
      python3 -m coverage report --include='checks/installed_skill_integrity.py'
      --fail-under=100`；前一个 report 强制新增 integrity/CLI 模块总覆盖率至少 80%，后一个
      在 `--branch` 数据上强制包含路径安全、快照和状态聚合决策的核心 library 达到 100%。
- [ ] CLI-only coverage gate:
      `python3 -m coverage erase &&
      python3 -m coverage run --branch
      --source=checks.installed_skill_integrity,tools.check_installed_codex_skills
      -m pytest -q tests/test_installed_skill_integrity.py tests/test_check_workflow.py
      -k "installed or required_files or undeclared_artifact" &&
      python3 -m coverage report
      --include='tools/check_installed_codex_skills.py' --fail-under=80`。
- [ ] Installer tests: `python3 -m pytest -q tests/test_install_codex_skills.py
      -k "dry_run or apply or source_race or target_parent_swap or target_root_swap or
      symlink or fifo or special or hardlink or exchange or recovery or kill or power_loss or
      recovery_record_path or recovery_escape or recovery_basename or size_mismatch or
      file_size_cap or append_growth or read_budget or post_check or mode or umask"`；target swap fixtures
      在 preflight 与 staging/commit 间替换 parent/root，并证明 external sentinel 的
      path/type/mode/mtime_ns/hash 均不变；mode fixtures 证明 `0755` 在非零 umask 下仍精确
      安装，且安装副本降为 `0644` 后即使 hash 相同也由 doctor/post-check 判 drift；forged
      recovery path fixtures 在任何 open/cleanup 前失败并保持 outside sentinel 不变；
      kill-during-copy fixture 在 step 7 复制中途中断，证明 destination=old 加不完整
      staging 会被下一次显式 apply 清理恢复，而不是永久 fail closed；kill-during-cleanup
      fixture 在 exchange 后递归清理 old tree 中途中断，证明 destination=new 加部分删除的
      staging 残留同样由下一次显式 apply 恢复清理并删除 record，不会被 catch-all 永久阻断。
- [ ] Session binding: `python3 -m pytest -q tests/test_check_workflow.py
      -k "loaded_skill or session_restart"`；正例要求 runtime-owned current-session entrypoint
      hashes 与 doctor/lock 同一 manifest，并允许 source router 的 `source_checkout` path；
      负例覆盖 evidence 缺失、自报、旧 session、apply 后未 restart、source/installed origin
      冒充、path/hash/session mismatch，且都在 lane/checkpoint/remote write 前阻断。
- [ ] Namespace/artifact safety: `python3 -m pytest -q
      tests/test_installed_skill_integrity.py -k "non_utf8 or raw_bytes or hardlink or
      undeclared_directory or traversal_cap or truncated or manifest_cardinality or
      artifact_parent or
      structural_directory_rebind or structural_directory_mutation or size_mismatch or
      file_size_cap or append_growth or read_budget"`；证明 cap 命中后 sample 固定为空且无
      descendant traversal，artifact parent swap 不会写入 target，structural tree 不会混合
      old/replacement namespace，单文件最多读取 `expected_size + 1` bytes。
- [ ] Workflow integration: `python3 -m pytest -q tests/test_check_workflow.py`
- [ ] Full regression: `python3 -m pytest -q`
- [ ] Pack/spec checks:
      `python3 checks/check_workflow.py --repo . --all-specs &&
      python3 tools/spec_depth_audit.py --spec-dir specs/GH172 --gate`
- [ ] Manual dry-run:
      `python3 tools/check_installed_codex_skills.py --repo . --target-dir <fixture>`;
      校验 match/drift/missing/not_installed 输出与退出码。
- [ ] No-write verification:
      `python3 -m pytest -q tests/test_installed_skill_integrity.py
      -k "target_snapshot_no_write"`；fixture 对 doctor 前后目标的相对路径、类型、mode、mtime_ns
      与 regular-file sha256 做闭合 snapshot 并要求完全一致。
- [ ] Scope/manifest/file ceiling:
      `sed -n '9p' specs/GH172/tech.md |
      jq -e '(.paths|length)==17 and (.paths|unique|length)==17 and
      ([.paths[]|select(startswith("specs/GH160/"))]|length)==0' &&
      test -z "$(git diff --name-only "$(git merge-base HEAD origin/main)"..HEAD --
      specs/GH160)" &&
      for path in $(sed -n '9p' specs/GH172/tech.md |
      jq -r '.paths[]|select(endswith(".py") or endswith("/SKILL.md"))');
      do test "$(wc -l < "$path")" -lt 800 || exit 1; done`。

## 回滚方案

回滚新 checker/library、installer 接线、lock 多文件解析、三个 Skill 入口、测试、文档和
三个 skill 哈希即可恢复原行为。新增 `files[]` 尚未由本 issue 的生产 lock 使用；若后续
GH-160 或 GH-174 已使用，必须先把其引用内容合回对应 `SKILL.md` 并恢复单文件 lock，
不能只删除 validator 支持。回滚不需要修改用户安装目录，且不得自动运行 installer。
