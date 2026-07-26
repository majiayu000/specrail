# Product Spec

## Linked Issue

GH-174

## 用户问题

`specrail-implement-queue/SKILL.md` 当前为 799 行、40,985 bytes，是 implx
运行中最大的 Skill 注入源。它同时承载入口合同、阶段细节、证据说明和恢复示例，
导致 agent 为确认某一阶段规则而整篇重读。简单拆文件又会引入漏读、引用漂移或
“主文件与引用互相冲突”的新风险。

用户需要一个小而完整的主入口，以及确定性的按阶段引用机制；未加载引用时也不能绕过
readiness、review、authorization、merge 或 fail-closed 合同。

## 目标

- 将 queue 主 Skill 收缩到不超过 500 行且不超过 28 KiB。
- 在主文件保留所有运行时关键合同和 phase-to-reference 路由。
- 将阶段细节移到单层、受锁定、按需加载的引用文件。
- 用确定性检查保证引用闭集、路径安全、无循环、无冲突并可安装。
- 让 startup 以 loader-owned evidence 绑定实际加载的 entrypoint，并在第一条命令前启用
  output firewall。

## 非目标

- 不改变 queue 的 readiness、route、review、authorization、merge 或 fail-closed 语义。
- 不读取原始 Codex session JSONL，也不承诺固定 token 降幅或读取次数。
- 不修改 GH-160 的 context budget 行为。
- 不在 GH-172 合并前修改 queue、installer、doctor 或 `skills-lock.json`。

## Behavior Invariants

1. B-001 当 agent 加载 queue Skill 时，主 `SKILL.md` 必须不超过 500 行且不超过
   28 KiB；任一上限超出均使 pack check 失败。
2. B-002 当 agent 只读取主文件时，仍必须看到 Startup、skip labels、Done-When、
   Same-Issue Circuit Breaker、停止条件、reviewer lane、authorization、merge gate
   和 fail-closed 的不可绕过摘要。
3. B-003 当某一 queue phase 需要详细步骤时，主文件必须通过稳定 phase ID 将该阶段
   映射到且只映射到一个或多个明确相对引用路径。
4. B-004 当 phase 未发生时，agent 不得被要求预读该 phase 的引用；当 phase 发生时，
   必须在执行该阶段首个动作前加载全部映射引用。
5. B-005 当引用文件缺失、未锁定、hash 漂移、非普通文件、符号链接或路径逃逸时，
   workflow/installed doctor/queue preflight 必须 fail closed，不能 warning 后继续。
   `implx` 外层必须在任何远端状态读取前完成 origin-aware preflight：使用 repo-distributed
   copy 时校验当前 repo copy 且不得要求本机已安装；实际使用 installed copy 时才额外要求
   GH-172 installed doctor `match`。直接调用 queue 主入口必须重复同一 preflight。
6. B-006 当 queue Skill 目录新增、删除或修改引用时，GH-172 定义的 lock、installer
   与 installed doctor 必须消费同一完整文件闭集。
7. B-007 当引用 A 指向引用 B、指回主文件或形成任何多跳/循环图时，确定性引用检查
   必须拒绝；所有引用只能由主文件一跳到达。
8. B-008 当主文件声明未知 phase、重复 phase、同一 phase 内重复路径、空路由或未使用引用时，
   检查必须一次报告全部缺陷并稳定排序；同一引用服务多个不同 phase 是合法复用，不得按
   全局 duplicate path 拒绝。
9. B-009 当主文件与引用出现**可判定的**冲突 normative contract 时，检查必须失败：
   判定范围是两类——(a) 引用中出现主文件同一 `contract_id` 的规范性句子却未逐字复用
   主文件短版文本；(b) 引用中由稳定 marker 显式标记的 normative block 命中封闭的
   weakening pattern 清单。清单不得扫描示例、说明或未标记的普通文本，因此合法的
   “optional local runtime checkpoint”等非规范描述不会误报。引用不得放宽主文件的
   MUST/禁止项或声明自己具有更高优先级；检查器不承诺检出上述范围之外的自然语言矛盾。
10. B-010 当现有 queue 行为测试运行时，拆分前的 readiness、planning、review、
    CI、authorization、merge、checkpoint 与 rejection 语义必须保持通过。
11. B-011 当 queue/implx 入口引用已拆分资产时，入口不得递归整篇重读 queue 主文件；
    compaction/resume 只重读主文件与当前 phase 的引用。
12. B-012 当相同仓库重复运行引用图校验时，phase 路由、错误顺序、hash 与退出码必须一致。
13. B-013 当安装目标不存在时，doctor 按 GH-172 返回 not-installed；当目标存在但
    任一引用缺失时，必须是完整性失败而非 skipped。
14. B-014 当安装 apply 在复制过程中失败或被取消时，不得报告成功；post-check 必须
    覆盖主文件与每个引用。
15. B-015 当 GH-182 等后续 issue 修改等待合同时，`wait-contract-v1` 语义必须在
    拆分后仍有唯一规范位置并由主入口路由，不得因移动而失去静态校验。
16. B-016 当合并后观测真实运行指标时，读取次数/token 注入仅作为独立观测；结构、
    完整性与行为门禁全绿即可完成本 issue。
17. B-017 当 `implx` 或 direct queue 启动时，origin preflight 必须消费当前 invocation
    的 fresh loader-owned loaded-entrypoint binding：direct queue 绑定实际加载的 queue
    entrypoint；`implx` outer 绑定实际加载的 implx entrypoint 以及 loader-resolved queue
    dependency descriptor。checker 根据两者的实际路径/bytes digest、delegation relation、
    canonical bundle/source root 与受信 installed-root binding 推导
    `repo_copy | installed_copy`。CLI、environment、repository、checkpoint、agent 提供的
    `--repo`/`--entrypoint`/origin 值或旧 binding 均不得选择或证明 origin；loader resolver、
    peer verification、freshness、path containment、digest 或 invocation binding 缺失/不匹配时，
    必须在任何 remote fetch/list/map 前 fail closed。repo copy 仍不得因本机未安装而失败；
    installed copy 仍必须额外通过与同一 source manifest 绑定的 doctor `match`。
18. B-018 当 `startup_planning` 开始时，`implx` 与 queue 主 `SKILL.md` 必须分别在其
    第一条 preflight、诊断或 remote command 前激活同一最小 output-firewall normative
    contract：潜在大输出的 raw
    stdout/stderr 只进入 artifact，parent 只接收 exit status、有界 tail、targeted summary 与
    artifact path，并禁止 raw CI log、full-suite log、session JSONL 或 broad generated-tree
    search 进入 parent context。该合同不得只存在于 `evidence-and-recovery.md`；startup
    planning reference 可以补充操作细节，但未加载 recovery reference 也不得使 firewall 失效。
19. B-019 当任一 phase 在 startup 之后首次加载映射引用时，loader 必须在该 phase 首个动作前
    以 startup 固定的 source root、source-lock digest 与逐文件 digest 重新校验实际路径和
    bytes，并直接消费同一份已校验 bytes；startup 曾通过、旧缓存或重新打开文件均不得替代
    这次 load-time 校验。任一路径、类型、containment、source-lock 或 bytes 漂移都必须在引用
    内容生效前 fail closed。
20. B-020 当 merge 获得远端确认后，无论该项是否发生 handoff 或 retry，queue 都必须进入稳定
    `post_merge_closure` phase，在第一项 closure-audit 动作前加载其全部映射引用；正常成功
    路径不得因没有进入 `runtime_handoff`/`retry_recovery` 而缺失 closure-audit 详细合同。
21. B-021 当 origin preflight 判定 `repo_copy` 时，必须按 attested `skill_id` 使用闭集 canonical
    repo path：direct queue 校验实际 queue entrypoint；`implx` outer 同时校验实际 implx
    entrypoint 与 loader-resolved queue dependency。两条路径必须处于同一 canonical source
    root 并绑定同一 source-lock chain；只校验 queue canonical path、混用 root/lock 或存在未知
    skill ID 均 fail closed。

## 验收标准

- [ ] 主 Skill 同时满足 ≤500 行与 ≤28 KiB。
- [ ] 关键运行合同全部保留在主文件，阶段细节按稳定 phase ID 一跳加载。
- [ ] 引用图检查拒绝缺失、未锁定、漂移、越界、循环、未使用与可判定冲突引用；required
      header 中唯一的 `SKILL.md` token 被窄豁免，其他裸主文件/引用路径仍被拒绝。
- [ ] repo copy 不要求本机安装即可启动；installed copy 必须 doctor `match`；两种路径及
      `implx` 外层都在任何远端状态读取前完成 origin-aware preflight。
- [ ] 每个 phase 只加载自己声明的引用：startup 仅 planning，runtime_handoff 恰为
      planning+evidence，review 仅 review，post-merge closure 仅 evidence，recovery 仅
      evidence；跨 phase 复用不算重复。
- [ ] startup 不接受 caller-selected origin/path：fresh loader-owned descriptor 精确绑定
      current invocation、direct loaded queue 或 loaded implx + resolved queue dependency 的
      path/bytes/delegation 与 canonical roots；repo copy 正例不依赖
      installed copy，installed copy 正例必须 doctor match，旧/伪造/不可达 resolver 均在 remote
      read 前失败。
- [ ] output firewall 的最小 normative contract 保留在主入口，并在 preflight 与任何 remote
      list/map 前生效；只加载 startup planning reference 的正例也必须把大输出导向 artifact，
      不得等待 runtime_handoff/retry_recovery。
- [ ] 每个 phase 在首次使用引用前按 startup 固定的 root/lock/digest 校验并消费同一份 bytes；
      startup 后引用发生任何漂移的负例都在 phase 动作前失败。
- [ ] 正常 merge 成功路径进入 `post_merge_closure` 并加载 `evidence-and-recovery.md`，无需借道
      handoff 或 retry 即可取得 closure-audit 详细合同。
- [ ] `repo_copy` 对 direct queue 校验 queue canonical path，对 `implx` outer 同时校验 implx
      与 delegated queue canonical paths，且两者属于同一 source/root/lock chain。
- [ ] lock、installer、installed doctor 对多文件闭集语义一致。
- [ ] 现有行为测试与全量测试全绿，且不含 GH-160 diff。
- [ ] 合并后的真实注入指标作为独立、非阻断 follow-up 记录，不属于本 issue Done-When、
      spec approval、merge 或关闭硬门。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-005 B-008 B-013 B-019 B-021 |
| 错误与失败路径 | covered: B-005 B-008 B-009 B-014 B-019 B-020 B-021 |
| 授权/权限 | covered: B-002 B-009 B-010 B-017 B-021 |
| 并发/竞态 | covered: B-014 B-019 |
| 重试/幂等 | covered: B-011 B-012 B-014 B-019 |
| 非法状态转换 | covered: B-004 B-005 B-010 B-017 B-018 B-019 B-020 B-021 |
| 兼容/迁移 | covered: B-002 B-006 B-010 B-015 B-017 B-020 B-021 |
| 降级/回退 | covered: B-005 B-009 B-013 B-014 B-017 B-018 B-019 B-020 B-021 |
| 证据与审计完整性 | covered: B-006 B-008 B-012 B-016 B-017 B-018 B-019 B-020 B-021 |
| 取消/中断 | covered: B-014 B-019 |

## 发布说明

queue 的入口和行为保持不变，详细规则改为按 phase 一跳加载。安装旧单文件副本的用户
必须在 GH-172 多文件完整性能力可用后显式更新；活动会话可能需要重启。真实 token
改善作为合并后观测，不替代结构和行为验证。loaded-entrypoint resolver 是 origin-aware
startup 的 host prerequisite；不可用时 queue 明确 fail closed。output firewall 仍由主入口
在 startup 首条命令前生效，不因 reference 拆分延后。phase loader 以 invocation 固定的
root/lock/digest 对每次首次加载闭锁 bytes；正常 merge 后通过第五个
`post_merge_closure` phase 加载 closure-audit 细节。
