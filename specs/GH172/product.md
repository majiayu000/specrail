# Product Spec

## Linked Issue

GH-172

## 用户问题

`skills-lock.json` 与普通 `check_workflow` 只能证明仓库内的 skill 副本和
lock 一致，不能证明 Codex 实际读取的已安装副本一致。用户目前会看到
`SpecRail check passed`，同时继续运行缺少最新守卫的旧 skill；随着后续
skill 继续演进，漂移还会从单个文件扩大到多个文件。

用户需要一个显式、只读、可重复的 installed-skill doctor：它既不能把
“目标目录不存在”冒充“全部匹配”，也不能让本机 `$HOME` 状态污染普通
pack/CI 校验，更不能未经授权自动安装或修复。

## 目标

- 为已安装 Codex skill 提供显式、只读的完整性检查。
- 复用同一套 target 解析语义：显式 override、`$CODEX_HOME/skills`、
  `~/.codex/skills`。
- 对 lock 中每个 skill 给出确定性的 `match | drift | missing` 结果，并
  一次报告全部缺陷。
- 让 queue startup 与 `specrail-install` doctor 消费该检查，在运行旧
  skill 前 fail closed。
- 保持普通 `python3 checks/check_workflow.py --repo .` 与 CI 完全基于
  仓库内容，不读取或依赖用户 `$HOME`。

## 非目标

- 不自动运行 `tools/install_codex_skills.py --apply`，不写入或删除本地
  skill。
- 不证明当前已启动的 Codex 会话已经重新加载磁盘上的新副本。
- 不实现跨机器分发、后台同步、发布 hook 或 CI 向用户机器推送。
- 不创建、删除或同步 GitHub labels；尤其不在本 issue 中 provision
  `parked`。
- 不改变现有安装命令的 dry-run-first 与人工授权边界。
- 不在 `ready_to_spec` 阶段提前创建 `specs/GH172/tasks.md`；task plan
  仍属于后续 `implement` 生命周期。

## Behavior Invariants

1. B-001 当用户运行普通 pack 校验且未显式选择 installed-skill doctor
   时，校验不得读取 `CODEX_HOME`、`~/.codex/skills` 或其他安装目录；
   相同仓库内容在不同机器上必须得到相同 pack 判定。
2. B-002 当用户显式选择 installed-skill doctor 并提供 target override
   时，系统必须只使用该 override；未提供 override 时必须先使用
   `$CODEX_HOME/skills`，仅在 `CODEX_HOME` 未设置时使用
   `~/.codex/skills`。
3. B-003 当 doctor 开始检查时，输出必须明确记录最终 target 路径及其
   来源（`explicit | CODEX_HOME | default_home`），不得让调用方从路径
   字符串反推来源。
4. B-004 如果最终 target root 不存在，doctor 必须返回显式
   `not_installed/skipped`，且不得输出 `match` 或“installed skills
   passed”；该状态不是完整性成功证据。
5. B-005 如果 target root 存在，doctor 必须按 `skills-lock.json` 的
   稳定顺序为每个 locked skill 产生且只产生一条
   `match | drift | missing` 记录，包含 name、expected hash、actual
   hash（缺失时为 `null`）及目标路径。
6. B-006 如果一个或多个记录为 `drift` 或 `missing`，doctor 必须非零
   退出并一次报告全部不匹配项；不得在首个错误处停止，也不得用仍匹配
   的多数项覆盖失败。
7. B-007 只有 target root 存在且每个 locked skill 都是 `match` 时，
   doctor 才能报告 installed-skill integrity success。
8. B-008 如果 target root 存在但其中一个或全部 locked skill 缺失，
   必须归类为 `missing` 并失败；不得降级成 B-004 的
   `not_installed/skipped`。
9. B-009 如果 `skills-lock.json` 缺失、结构无效、path 非法、frontmatter
   无效或 repo hash 不匹配，doctor 必须先沿用现有 lock validation
   失败，不得对无效 lock 产生可信 runtime 结论。
10. B-010 如果某个 installed `SKILL.md` 含 descendant symlink 或其他
    重定向，解析后必须仍位于 target root 且保留 locked path identity；
    逃出 root 或改写 identity 时 doctor 必须失败并报告 unsafe path，不得
    读取重定向目标后把相同 hash 判为 `match`。
11. B-011 无论 doctor 得到 `match`、`drift`、`missing`、
    `not_installed`、无效 lock 或读取错误，它都不得创建 target root、
    写文件、删除文件、修复 symlink 或调用 installer。
12. B-012 对同一静态 repo、lock、环境和 target 连续运行 doctor，输出
    顺序、状态、hash 与退出码必须相同；重复检查不得改变下一次结果。
13. B-013 如果安装目录在检查期间被并发替换，任何观察到的缺失、读取
    失败、unsafe path 或 hash 不一致都必须 fail closed；不得用 fallback
    内容补成 `match`。
14. B-014 当 queue startup 使用 installed skill 时，必须先消费 doctor
    结果；只有 `match` 可以声明已安装副本已验证。`drift`、`missing` 或
    unsafe/error 必须在打开 implementation lane 前停止；`not_installed`
    只能声明“无已安装副本”，不能声明其完整性通过。
15. B-015 当 `specrail-install` 的 `doctor` 或 `install_local_skills`
    route 发现漂移时，必须先报告 doctor 证据并可展示 installer dry-run；
    除非当前用户显式授权安装，否则不得自动追加 `--apply`。
16. B-016 doctor 的摘要必须包含 target、target source、locked 总数以及
    `match`、`drift`、`missing` 计数，使“全部匹配”无法由省略单项记录
    伪造。
17. B-017 即使磁盘上的所有 hash 已匹配，若本轮刚执行过安装或更新，
    输出仍必须提醒“活跃会话可能需要重启”；磁盘匹配不得被表述成当前
    会话已加载新文本。
18. B-018 doctor 的 `match` 只证明 locked `SKILL.md` 与 repo lock 一致，
    不证明外部 GitHub 契约已具备；在 `parked` label provisioning 依赖
    未满足时，不得宣称 GH157 queue guard 已 operational。
19. B-019 现有 `tools/install_codex_skills.py` 的默认 dry-run、显式
    `--apply`、`--target-dir` 与 unsafe source/target 拒绝语义必须保持
    兼容；新增 doctor 不得把安装变成普通 check 的副作用。
20. B-020 如果 doctor 被取消或中断，系统不得留下 partial completion
    标记；重新运行必须从 repo lock 和当前 target 重新计算完整结果。

## 验收标准

- [ ] 普通 `check_workflow --repo .` 在安装目录为 match、drift、missing
      或不存在时均保持同一 pack 判定，且不读取安装目录。
- [ ] 显式 doctor 覆盖 explicit target、`CODEX_HOME`、default home 三种
      target 来源，并稳定报告来源。
- [ ] 缺失 root 显式输出 `not_installed/skipped`；存在但不完整的 root
      非零退出并列出所有 `missing`。
- [ ] 单项漂移、多项漂移、全部匹配、无效 lock、读取失败、symlink
      escape 与并发替换均有确定性正/负测试。
- [ ] doctor 的测试证明 target 与 repo 都无写入。
- [ ] queue startup 与 `specrail-install` doctor 文档要求在使用安装副本
      前运行显式检查，并区分 `match` 与 `not_installed`。
- [ ] 安装器已有 dry-run/apply/unsafe-target 测试继续通过。
- [ ] `parked` provisioning 被记录为独立依赖，未被 doctor 的成功状态
      隐藏。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-004, B-008, B-009 |
| 错误与失败路径 | covered: B-006, B-009, B-010, B-013 |
| 授权/权限 | covered: B-011, B-015, B-019 |
| 并发/竞态 | covered: B-013 |
| 重试/幂等 | covered: B-012, B-020 |
| 非法状态转换 | covered: B-004, B-007, B-008, B-014 |
| 兼容/迁移 | covered: B-001, B-017, B-019 |
| 降级/回退 | covered: B-004, B-013, B-014 |
| 证据与审计完整性 | covered: B-003, B-005, B-006, B-016, B-018 |
| 取消/中断 | covered: B-020 |

## 发布说明

新增的是显式只读 doctor，而不是自动安装。普通 pack/CI 校验保持确定性；
需要验证本机已安装副本时，用户或 queue/install entrypoint 显式启用
installed-skill check。修复后的磁盘 hash 仍不证明已启动会话完成 reload。

本 spec packet 在 `ready_to_spec` 阶段故意只有 `product.md` 与 `tech.md`。
当前 main 的 validator 仍无条件要求 `tasks.md`，因此完整 packet/CI 验证
blocked by #180 / PR #181；不得为绕过该生命周期冲突提前创建 tasks。
