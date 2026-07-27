# Product Spec

## Linked Issue

GH-189

## 用户问题

同一仓库的多个 Codex 会话可以同时运行 `implx`。现有 GitHub duplicate-work gate
只能发现 PR/branch 重复，`.specrail/runtime/current.json` 也没有 owner、lease 或
fencing token。两个会话因此可能重复开 lane、覆盖 checkpoint、串用 Goal，并把大量
token 消耗在同一队列上。

## 目标

- 为同一 Git common dir 下的所有 worktree 提供唯一 active-run lease。
- 在 lane、checkpoint 与发起远端写入前用 fencing token 阻止旧/并发 owner，并在
  同步远端调用期间用持久 operation guard 阻断 takeover。
- 支持同一 run 跨 compaction/session 的显式 resume，以及可审计 stale takeover。
- 保持检查有界、无 polling、无进程终止和无隐式远端动作。

## 非目标

- 不实现跨机器/网络文件系统的强一致分布式锁。
- 不 kill、暂停或关闭其他 Codex 进程，不用 GitHub label 充当 mutex。
- 不声称本地 fencing token 能撤回或取消已被 GitHub 接收的请求；远端结果不确定时
  fail closed，不能以本地 lease turnover 伪装成 provider-side fencing。
- 不替代 GitHub truth、runtime checkpoint、Goal 或 SpecRail gate。
- 不防御同一 OS principal 协调回滚整个 Git common dir 的全部 lease/counter/witness/audit
  资产；单独回滚或替换 counter、allocation witness、symlink、非普通文件或二者 high-water
  不一致必须检测。
- 不处理 GH-160。

## Behavior Invariants

1. B-001 当两个 worktree 共享同一 Git common dir 时，它们必须解析到同一 lease
   位置和 repo identity；该 identity 不得依赖当前 branch upstream、remote 名称/URL
   或 worktree 路径，运行期间修改 remote 配置也不得改变既有 owner 的 identity。
2. B-002 当不存在 lease 时，多个并发 acquire 中最多一个 run 可以原子获得有效
   `run_id` 与单调递增 `fencing_token`；acquire 与其他 lease 修改必须共享同一
   repo-wide mutation mutex。
3. B-003 当有效 lease 已由另一个 run 持有时，新 run 必须在创建 lane、写 checkpoint
   或执行 GitHub write 前阻断，并报告非敏感 owner/expiry 证据。
4. B-004 当持有者在关键边界续租时，必须提交匹配的 run ID、owner marker、
   fencing token、当前 lease digest 与不超过实现上限的 TTL；任一不匹配或 TTL
   越界均不得更新。
5. B-005 当 lease 到期时，它必须进入 `stale` 而不是自动变成 `free`；不同 run
   takeover 需要本轮显式人工授权与原因，且 deterministic core 不得把同一请求者
   自报的 actor/marker/reason 当作授权证据。
6. B-006 当授权 takeover 成功时，新 fencing token 必须大于旧 token，并在 canonical
   common-dir audit 资产中持久保留旧/new run ID、旧/new token、旧/new lease digest、
   independently verified authorization ID/digest、授权 actor 与 reason digest；新 lease
   必须绑定显式新 owner 且先处于
   `checkpoint_bound: false`/null digest，审计未 durable commit 时不得报告 takeover
   成功。新 owner 随后只能写入携带新 identity 的 v4 checkpoint 并立即 bind，bind 前
   不得创建 lane、resume 或 remote write。
7. B-007 当同一 run 跨 compaction 或新 session resume 时，只有 checkpoint 与
   lease 的 repo、run ID 和 fencing token 全部匹配，且 lease 中记录的
   checkpoint digest 与磁盘 checkpoint 完全一致，才可在 mutation mutex 内轮换
   owner marker 与 fencing token、重写 checkpoint identity 并重新绑定；旧 session
   的 token 必须立即失效。Goal 只提供连续性与预算上下文，不参与安全授权。
8. B-008 当 lease、mutex、fencing allocation 资产、authorization consumption 或 takeover
   audit 路径/JSON 缺失字段、损坏、部分写入、符号链接、identity 不一致、权限错误或路径
   逃逸时，inspect 必须返回 `corrupt/unsafe` 并 fail closed；allocation/consumption/audit
   inspect/create/replace/prune/recovery 不得跟随 common dir 外的路径。
9. B-009 lease expiry 必须绑定持久化的 boot identity 与同一 boot 内跨进程可比较的
   monotonic deadline；wall-clock 前跳/回拨、PID 被复用或进程不存在不得单独据此
   释放或接管 lease。boot identity 变化只将 lease 判为 `stale`，仍需显式 takeover；
   clock/boot 原语不可用或证据不一致时必须 fail closed。
10. B-010 当 owner 正常完成或收到用户中断时，只能在 repo-wide mutation mutex
    内释放与自己 run ID/owner marker/token/digest 匹配的 lease；不得删除其他 owner
    或更新后的 lease。
11. B-011 当 lease 操作被取消，或文件、rename、remove、受影响父目录 fsync 任一步骤
    失败时，不得产生已获取/已续租/已释放/已接管结论；下一次操作必须从 canonical
    磁盘状态重新读取并按 takeover journal 恢复或 fail closed。
12. B-012 当普通 pack check 运行时，它只校验 schema/tool 资产，不 acquire、renew、
    release 或读取活动 repo 的 lease。
13. B-013 当 lease 状态静态不变时，queue-facing CLI 的闭合 JSON 状态、摘要与退出码
    必须一致；inspect/acquire/renew/release/resume/takeover/recover 都不得要求 agent
    解析 human text，且输出不得包含 session 正文、secret、authorization/reason 原文、
    绝对 home 路径或 PID 细节。
14. B-014 当文件系统不支持所需原子替换、父目录 fsync、跨进程 mutation mutex，
    或 repo/boot/monotonic identity 无法稳定解析时，系统必须报告 `unsupported`
    并阻断所有 lease-protected `implx` 模式（包括 `review` 与 `auto`），不得降级成
    无锁继续；仅纯只读 inspect/pack check 可继续。
15. B-015 当 owner 准备发起 push/comment/label/PR mutation 等远端写入时，必须先在
    mutation mutex 内验证当前 lease 并持久写入绑定 repo/run/token/operation ID 的
    `remote_operation` guard；guard 清除前，即使 lease TTL 已过期也不得 takeover、
    resume、release 或启动另一远端写入。只有同步调用返回 provider 的确定终态后原
    owner 才能 compare-and-clear；timeout、transport interruption、进程消失或结果不确定
    必须保持 `remote_operation_unknown` 并 fail closed，本 issue 不提供强制清除或本地
    takeover escape hatch。
16. B-016 当请求 stale takeover 时，CLI 只可接受 opaque `authorization_ref`，deterministic
    core 必须据此调用由 host 配置、调用者不能替换或注入输入文件的独立 human-gate
    evidence adapter；adapter 返回 closed authorization artifact 与 maintainer role map。
    授权必须精确绑定
    authorization ID、repo ID、旧 lease digest/run/token、新 run/owner、reason digest、
    decision=`takeover_once`、actor/source 和短时有效期。core 必须独立重载/复核 role、
    exact binding 与 freshness，并在 canonical common dir 内通过逐段 no-follow、稳定 parent
    dirfd 与 closed consumption tombstone durable 标记该 ID 已消费；
    缺失、adapter 不可用、请求者自报/自带 artifact 或 role map、actor 非 maintainer、
    错绑、过期、重复消费或 auto/merge 授权替代均 fail closed。
17. B-017 当 acquire/resume/takeover 分配 fencing token 时，counter、永久 high-water
    allocation witness、prepared allocation journal 及各自 parent 必须从 canonical common-dir
    descriptor 逐段 no-follow 打开，并是 closed-schema regular file 且 lstat/fstat identity
    稳定。每次 allocation 必须先 durable reserve journal，再按固定顺序推进 counter 与
    witness；token 只有在二者 exact high-water 一致且 journal durable close 后才可使用。
    witness 不随正常 release 或 takeover audit retention prune 删除，因此单独回滚任一文件、
    symlink、非普通文件、竞态替换或无 exact prepared journal 的 high-water 不一致均
    `unsafe/corrupt`。崩溃恢复必须把 journal 已保留的 token 推进为 burned/skipped 后要求
    fresh retry，不得回收。takeover 必须在该 allocation durable 完成后才计算新 lease
    digest/写 prepared takeover audit；之后任一步失败时该 token 同样永久 skipped。
18. B-018 当 queue-facing CLI 输出 closed envelope 时，base keys 必须始终出现并使用
    明确 nullable 表示：`operation` 仅在无法解析 subcommand 时为 null；`repo_id` 在参数
    错误或 identity 尚未/无法解析时为 null；`lease_digest` 在 `free`、未安全读取 lease、
    参数/schema 错误或 identity unsupported 时为 null。不得伪造 sentinel string；每种
    null/non-null 组合、unknown field、argument/schema error 都必须有稳定 state/reason/exit。
19. B-019 当不 acquire canonical lease 的普通长运行使用通用 tranche checkpoint template
    时，必须继续得到当前实际的非 lease-aware `checkpoint_version: 2`；v1–v3 历史
    checkpoint 仍可离线校验，但只有成功 acquire 的 implx queue 才选择专用 v4 template。

## 验收标准

- [ ] 跨两个 worktree 的并发测试证明最多一个 owner 获得 lease。
- [ ] 两个 worktree 使用不同 branch upstream，且运行中新增、删除或改写 remote 后，
      仍得到相同 repo identity，既有 owner 仍可 renew/release。
- [ ] acquire/renew/release/resume/stale/takeover/损坏路径均有确定性测试。
- [ ] 跨 session resume 原子轮换 fencing token/owner marker 并重新绑定 checkpoint，
      旧 session 即使读取最新 lease digest 也不能再 renew 或通过 boundary gate。
- [ ] checkpoint/lease 单向 digest 绑定可达到稳定状态，修改任一侧均会 fail closed。
- [ ] runtime gate 只接受从当前 repo common dir 以 no-follow 方式解析出的 canonical
      active lease；保存副本、symlink 或显式替代路径均被拒绝。
- [ ] renew/release/takeover 的 compare-and-replace 在 mutation mutex 内串行化，
      并发测试证明旧 token 不能覆盖 takeover 后的新 lease。
- [ ] takeover audit 的 path、closed schema、prepared/committed 恢复顺序与 256 条
      retention 上限均有测试；audit directory/file symlink 或 identity swap、审计或父
      目录 fsync 失败不得返回成功。
- [ ] takeover durable commit 后得到新 owner/new token 的 unbound lease；只有新 owner
      写入 v4 checkpoint 并立即 bind 后才允许 lane/resume/remote write。
- [ ] 同 boot 的两个进程以 persisted monotonic deadline 得到同一 expiry 判定；boot
      变化只产生需授权的 stale，wall-clock 跳变不单独触发 takeover。
- [ ] renew 的 TTL 必填且有硬上限；超过上限的等待必须先 checkpoint/handoff。
- [ ] 所有 lane、checkpoint 和 remote-write 边界都验证当前 fencing token。
- [ ] lease-aware resume 明确使用 checkpoint+lease；不得把未独立绑定的 Goal
      描述为第三个安全证据。
- [ ] `unsupported` 在 plain review 与 auto 两种 lease-protected queue 中都阻断；
      无自动 takeover、无 kill、无 polling、无 GitHub mutex。
- [ ] queue-facing CLI 的每个 operation 都有参数、closed JSON、敏感字段裁剪与稳定
      state-to-exit-code 回归；`free`/`unsupported`/argument error 的 identity/digest
      nullability 有闭集用例；通用长运行 checkpoint 模板保持实际的非 lease v2，只有成功
      acquire 的 implx queue 使用专用 v4 模板。
- [ ] counter/witness/allocation journal 与各自 parent 的 dirfd/no-follow/type/identity、
      counter↔witness high-water 一致性及“先 durable 分配 token、再 prepared audit”有
      barrier/crash 回归；normal release、resume、audit prune 与后续失败后 witness 仍覆盖
      所有已分配 token，journal 恢复只留下永不复用的 skipped token。
- [ ] takeover 缺独立 role-mapped authorization、错 stale digest/new owner、过期、复用
      authorization ID、以 auto/merge authorization 替代时均阻断；exact `takeover_once`
      只消费一次；consumption parent/file symlink、identity swap、非普通文件与 malformed
      closed tombstone 均 fail closed，且不得写入 common dir 外 sentinel。
- [ ] 每个远端写入先 durable begin guard、确定响应后 compare-and-clear；stalled/timeout
      调用留下 `remote_operation_unknown` 并使 stale takeover 阻断，测试不声称 GitHub
      provider 会解释本地 fencing token。
- [ ] planned implementation 中当前 1092 行及 778–799 行的文件均按 tech manifest 的
      明确目标拆分；exact-head 验证证明每个 planned text asset 都少于 800 行，不能以新增
      内容继续推高或只豁免既有超限文件。
- [ ] full tests 与跨 worktree forward test 全绿，diff 不含 GH-160。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002 B-008 B-018 |
| 错误与失败路径 | covered: B-003 B-004 B-008 B-011 B-014 B-015 B-016 B-017 B-018 |
| 授权/权限 | covered: B-005 B-006 B-008 B-010 B-015 B-016 |
| 并发/竞态 | covered: B-001 B-002 B-004 B-008 B-010 B-011 B-014 B-015 B-016 B-017 |
| 重试/幂等 | covered: B-004 B-007 B-010 B-013 B-016 B-017 |
| 非法状态转换 | covered: B-003 B-005 B-006 B-007 B-010 B-015 B-016 B-017 |
| 兼容/迁移 | covered: B-001 B-012 B-014 B-019 |
| 降级/回退 | covered: B-008 B-009 B-014 B-015 B-017 B-018 |
| 证据与审计完整性 | covered: B-004 B-006 B-007 B-013 B-016 B-017 B-018 |
| 取消/中断 | covered: B-010 B-011 B-015 B-017 |

## 发布说明

启用后，同一 Git 仓库默认只允许一个 active implx run。发现 stale lease 时只报告
takeover 所需证据，必须由独立、一次性、exact-bound 的人工授权放行；远端调用结果不确定时
会保留 operation guard 并阻断 takeover。现有普通长运行模板继续输出非 lease v2。
