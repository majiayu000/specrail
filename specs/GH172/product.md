# Product Spec

## Linked Issue

GH-172

## 用户问题

SpecRail 的 `skills-lock.json` 只能证明仓库内的 skill 副本与声明哈希一致，不能证明
Codex 实际加载的已安装副本仍与仓库一致。新守卫合入后如果没有重新安装，运行时会继续
执行旧 skill；仓库检查仍然全绿，维护者却得到“运行时已受保护”的错误印象。当前锁还只
覆盖每个 skill 的入口 `SKILL.md`，无法保护后续按需加载的引用或脚本，这也阻塞了
GH-160 与 GH-174 的安全拆分。

## 目标

- 提供只读、确定性的 installed-skill integrity doctor，逐项报告仓库声明与安装副本。
- 区分未安装、完整匹配、内容漂移和文件缺失，避免任何静默降级。
- 让 installer 与 queue preflight 消费同一份检测结果，而不是各自重新推断。
- 让锁和 doctor 覆盖一个 skill 的全部受分发文件，为按需引用和脚本提供完整性保证。
- 让 lock completeness 覆盖 `skills/` 下所有顶层分发 skill，包括 `implx` 等非
  `specrail-*` 目录。
- 明确 GH-160 与 GH-174 的多文件 skill 变更都依赖本合同，并在各自实现时迁移到 v2 lock。
- 保持安装写入需要人工显式授权，doctor 永不自动修复或覆盖用户文件。

## 非目标

- 不自动执行安装、更新、删除或重启活动 Codex 会话。
- 不修改 `$HOME`、`CODEX_HOME`、仓库权限或 GitHub 状态。
- 不提供跨机器分发、远端配置同步或后台自动更新服务。
- 不实现 GH-160 的 context budget、水位计算或 handoff 行为；这里只约束其多文件
  skill/lock 的依赖顺序。
- 不在普通 CI/pack 校验中强制访问开发者的本机安装目录。
- 不在本 issue 内拆分 `specrail-implement-queue`；GH-174 在本合同落地后单独实施。

## Behavior Invariants

1. B-001 当 doctor 检查一个有效的 `skills-lock.json` 时，必须为每个被锁定的 skill
   以及该 skill 声明的每个受分发文件返回确定性结果；不得只检查入口文件后把整个目录
   表述为匹配。
2. B-002 当调用方提供显式安装目标时，doctor 必须只检查该目标；未提供时按
   `$CODEX_HOME/skills` 优先、否则 `~/.codex/skills` 的唯一规则解析目标，并在结果中
   披露最终路径和来源。
3. B-003 当解析出的安装根目录不存在时，doctor 必须返回显式
   `not_installed`/`skipped` 结果且不伪造逐文件 `match`；独立 doctor 可正常退出，queue
   preflight 不得把该结果当作可执行安装。
4. B-004 当安装根目录存在，但任一被锁定 skill 或受分发文件缺失时，结果必须标记
   `missing`、列出期望哈希和目标路径，并以非零状态结束；其他缺陷仍须一并报告。
5. B-005 当文件存在但内容哈希与 lock 不一致时，结果必须标记 `drift`，同时披露期望哈希、
   实际哈希和目标路径，并以非零状态结束；不得用时间戳、文件大小或目录存在替代哈希。
6. B-006 当且仅当所有声明的 skill 文件都存在、路径安全且哈希匹配，并且安装 skill
   目录中除这些文件及其必要、安全的严格父目录外不存在任何未声明项时，doctor 才能返回
   整体 `match`；单个入口文件匹配不能掩盖引用文件/脚本漂移或 stale undeclared content。
7. B-007 当多个 skill 同时存在 `match`、`drift`、`missing` 与 `undeclared` 时，doctor
   必须按稳定顺序返回全部声明文件结果和整体失败，不得在首个错误处提前结束；未声明项
   的标准输出必须使用有界摘要而不是无界路径列表。声明文件的严格父目录只有在它是
   containment 内的真实目录且恰好属于声明路径前缀时才是 structural entry；structural
   entry 不计为 `undeclared`，其它文件、目录或特殊项仍必须计入并阻断 `match`。
8. B-008 当 lock 缺失、格式非法、哈希非法、声明重复、文件未纳入锁或锁中路径不存在时，
   doctor 必须复用仓库 lock 校验的 fail-closed 结果，不能进入“安装副本匹配”的判定。
9. B-009 当声明路径或安装目标通过绝对路径、`..`、符号链接或其他解析方式逃逸出允许的
   skill 根目录时，doctor 必须拒绝该项并整体失败；不得读取或哈希逃逸目标。
10. B-010 默认 doctor、library inspect 与所有 queue/installer preflight 必须只读：不得
    创建目录、写 checkpoint、更新 lock、修改安装副本、调用 `--apply` 或自动修复。唯一
    例外是调用方显式传入 B-019 的 artifact 路径时，CLI 可 create-only 写入该新诊断文件；
    这项授权不允许覆盖文件，也不允许写入安装目标。
11. B-011 当 installer 以默认 dry-run 运行时，必须先调用同一完整性检查并明确显示现状与
    将要执行的计划；只有调用方另外给出既有的人工 `--apply` 授权时才可写入。apply 必须
    仅从 lock 声明的 source regular file 的 stable no-follow snapshot 复制；若 source 路径
    在验证与复制之间变成 symlink/special file、逃逸或发生变化，必须在替换已安装 skill 前
    fail closed，且不得读取或复制逃逸目标内容。
12. B-012 当 queue/`implx` runtime preflight 启动时，必须要求当前运行所需的锁定 skill
    全部为 `match`；`not_installed`、`drift`、`missing`、不安全路径或 doctor 运行错误
    均阻断自动队列，并给出 dry-run 安装或人工处理的下一步。
13. B-013 当普通 `check_workflow.py` 在 CI 或没有本地安装根的环境运行时，必须保持纯仓库
    校验且明确不声称已检查 runtime 安装；installed-copy 检查由显式 doctor/queue/install
    preflight 触发。
14. B-014 当 skill 新增、删除或修改受分发引用、脚本等文件时，lock 必须随之更新完整文件
    集和哈希；completeness discovery 必须枚举 `skills/` 的每个顶层分发 skill 目录，
    不得只匹配 `specrail-*` 前缀。未锁定的顶层 skill（包括 `implx` 一类无前缀目录）、
    未锁定的分发文件、锁定但未分发的文件、路径越界或重复声明全部被确定性拒绝。
15. B-015 当现有只包含 `SKILL.md` 的合法 lock 被读取时，它必须保持可验证和可安装；升级
    后的多文件声明不得把既有单文件 skill 静默解释为目录内任意文件均受信任。任一条目
    声明多文件时，lock 顶层版本必须提升，使旧 reader 直接失败而不是忽略未知字段后
    误判通过。
16. B-016 当检查期间安装文件发生变化，导致同一项无法获得稳定快照时，doctor 必须报告
    不一致并失败，而不是把检查前路径与检查后哈希组合成 `match`。
17. B-017 当重复运行 doctor 且 lock 与安装目录均未变化时，输出顺序、逐项状态、未声明
    项总数/样本/省略数和退出码必须一致；先前失败或后续成功都不得修改被检查对象。
18. B-018 当检查被取消、读取失败或依赖异常导致结果不完整时，调用方不得缓存或复用部分
    `match` 作为后续 queue 证据；恢复后必须重新完整检查。
19. B-019 当读取已安装文件时，最终路径组件必须以 no-follow、nonblocking 方式打开，并在
    open 后立即对同一描述符执行首次 stat；只有确认为 regular file 后才能读取/哈希，随后
    再比较同一描述符的 stat。symlink、FIFO、socket/device 等特殊文件或任一 snapshot
    不一致必须 fail closed，不得先跟随/阻塞/读取后再事后判定不稳定。标准 human/JSON
    诊断中的未声明项只允许输出 `undeclared_total`、`undeclared_omitted` 和按 UTF-8 字节序确定的有界
    `undeclared_sample`：最多 50 项且合计最多 8192 UTF-8 bytes。只有调用方显式指定
    create-only artifact 时才能写出完整、稳定排序的相对路径清单；不得覆盖既有 artifact，
    queue preflight 不得启用该导出。任何输出均不得包含文件正文、凭据或环境变量值。
20. B-020 当 GH-160、GH-174 等后续变更使用多文件 skill 时，installer、doctor 与 lock
    validator 必须消费同一文件清单语义并迁移到 v2 lock；任一组件只处理入口文件都视为
    合同不完整。GH-160 与 GH-174 的 multi-file 实现都必须在 GH-172 合并后再开始。
21. B-021 当授权 `--apply` 对安装目标 staging、替换、回滚或清理时，installer 必须先从
    稳定 trust anchor 逐段 no-follow 打开目标父目录/根目录 descriptor，并只用该 descriptor
    的 dirfd-relative 操作完成事务；pathname precheck、`resolve()` 结果或随后重新按路径打开
    不能充当写入授权。若 target root/任一 parent 在 preflight、staging 或 commit 期间被换成
    symlink、移出原 namespace、重新绑定到不同 inode，或无法证明当前 pathname 仍绑定所持
    descriptor，必须 fail closed、经同一安全 descriptor 清理 staging/回滚，并保证替代
    symlink 指向的目录及其它授权根外对象零写入、零删除。
22. B-022 当 v2 lock 声明分发文件时，入口与每个 `files[]` 项都必须显式绑定规范化
    `mode`（闭集 `0644 | 0755`）以及内容哈希；source validator、installer same-fd snapshot、
    staging copy 和 installed doctor 必须保留并逐项验证 exact mode。可执行脚本以 `0755`
    分发后若变成 `0644`，即使 bytes/hash 未变也必须报告 drift、post-check 失败并阻断 queue；
    缺失/越界 mode、setuid/setgid/sticky、group/world-write bits、umask 导致的偏差或检查期间
    mode 变化均 fail closed，不得按扩展名、shebang 或调用方式猜测执行权限。

## 验收标准

- [ ] 显式目标、`$CODEX_HOME` 和默认目录三种解析路径都有确定性结果。
- [ ] 每个锁定 skill 的全部分发文件均产生 `match | drift | missing` 证据。
- [ ] 安装根不存在被明确报告；存在但漂移或缺失时返回非零且列出全部问题。
- [ ] 符号链接、FIFO/special file、路径逃逸、重复声明、未锁定分发文件和检查中变化
      全部 fail closed；嵌套声明文件所需的真实父目录不被误报为 undeclared。
- [ ] 默认 doctor 与 preflight 完全只读；installer 保持 dry-run 默认且从不自动调用
      `--apply`。显式 B-019 artifact 导出是唯一诊断写入例外，且只能 create-only。
- [ ] queue/`implx` 在 runtime 安装不匹配时被阻断，普通 CI 不访问本机安装目录。
- [ ] 既有单文件 lock 保持兼容，多文件 skill 的 validator/installer/doctor 语义一致；
      installer 不使用会跟随 source race 的 whole-directory copy。
- [ ] installer 的 target root/parent 在 preflight 与 staging/commit 间被替换为 symlink 或
      重新绑定时，事务 fail closed；所有 staging/backup/replace/rollback/cleanup 均为
      no-follow descriptor/dirfd-relative 操作，外部 sentinel 保持 byte-for-byte 不变。
- [ ] v2 lock 对入口和每个分发文件显式声明 `0644 | 0755`；installer 不受 umask 影响地保留
      exact mode，doctor 对“hash 相同但 executable bit 丢失”返回 drift，queue/preflight 阻断。
- [ ] 未声明项标准输出固定包含总数、省略数和不超过 50 项/8192 bytes 的稳定样本；
      完整相对路径仅可写入显式、create-only artifact，queue 不产生该 artifact。
- [ ] 新增无 `specrail-*` 前缀的顶层 skill fixture 会因未入 lock 被拒绝，既有 `implx`
      明确属于 completeness discovery 集合。
- [ ] GH-160 的功能文件、状态和行为不在本变更范围内，但其 multi-file lock 迁移明确
      依赖 GH-172，与 GH-174 一样不得抢先实施。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-004 B-008 B-014 |
| 错误与失败路径 | covered: B-004 B-005 B-008 B-009 B-016 B-018 B-021 B-022 |
| 授权/权限 | covered: B-010 B-011 B-012 B-021 B-022 |
| 并发/竞态 | covered: B-011 B-016 B-017 B-019 B-021 B-022 |
| 重试/幂等 | covered: B-007 B-017 B-018 |
| 非法状态转换 | covered: B-003 B-006 B-012 |
| 兼容/迁移 | covered: B-013 B-014 B-015 B-020 B-022 |
| 降级/回退 | covered: B-003 B-011 B-012 B-013 |
| 证据与审计完整性 | covered: B-001 B-005 B-006 B-007 B-011 B-014 B-019 B-020 B-021 B-022 |
| 取消/中断 | covered: B-016 B-018 |

## 发布说明

该变更新增显式、只读的 runtime 安装完整性检查。普通仓库/CI 校验行为保持不变；queue
与 installer 会在实际运行前披露安装状态。安装根存在但内容漂移或缺失时将从静默继续改为
fail closed。维护者仍需显式运行带 `--apply` 的安装命令并重启需要重新加载 skill 的活动
会话；doctor 本身不会写入或自动修复。v2 multi-file lock 还会固定每个文件的 `0644|0755`
mode；target pathname 在安装事务中发生 symlink/inode rebinding 时安装会安全失败，不能改写
替代路径。
