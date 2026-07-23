# Product Spec

## Linked Issue

GH-182

## 用户问题

`implx` 长队列把大量高上下文 turn 消耗在“还没完成”的等待上。仓库已经要求
“单次阻塞等待”，但当前 `skills/specrail-implement-queue/SKILL.md` 同时要求把
direct `exec_command` 的 `yield_time_ms` 提到配置最大值，并在需要时指数增加多次
wait。Codex direct exec 的有效上限实际为 30000 ms，这段指导既无法延长首次等待，
又会诱导模型继续发起多个空等待 turn。

用户需要一份与实际工具边界一致、可被确定性检查的等待合同：长命令只允许一次续等，
子 agent 只允许一次长等待，CI 使用阻塞 watch；任何超时都不能自动退化成 30 秒轮询。

## 目标

- 消除 queue/implx 中关于 direct exec yield 的错误与冲突指导。
- 为本地长命令、CI 和 subagent 三种等待路径定义唯一、有限的调用形态。
- 用确定性仓库检查阻止错误等待模式重新进入受分发 Skill。
- 保留实现后的 post-policy cohort 验收，区分“合同正确”与“真实运行有效”。

## 非目标

- 不修改 Codex 工具运行时、30 秒 direct exec 上限或系统级 developer instructions。
- 不读取、改写或发布用户的 Codex session JSONL。
- 不处理 GH-160 的上下文预算、水位、compaction 或 handoff 行为。
- 不实现通用进程管理器、后台 daemon 或定时采样服务。
- 不在本 issue 中自动安装 Skill、重启活动会话、合并 PR 或关闭 issue。

## Behavior Invariants

1. B-001 当 Skill 指导直接调用 `exec_command` 时，必须声明有效
   `yield_time_ms` 上限为 30000；不得建议给 direct exec 传入更大的值来延长等待。
2. B-002 当 code-mode 编排一个可能超过 30 秒的命令时，必须在同一个外层工具调用内
   使用长等待预算，并让内层 `exec_command` 使用 `yield_time_ms: 30000`。
3. B-003 当且仅当 B-002 的内层 exec 返回 `session_id` 时，同一个外层调用才可执行
   一次空 `write_stdin`，其 `yield_time_ms` 必须为 1800000。
4. B-004 当内层 exec 已完成且没有 `session_id` 时，编排不得调用 `write_stdin`，
   也不得为了“确认完成”再次查询相同命令。
5. B-005 当单次长 `write_stdin` 返回后任务仍非终态时，模型不得再次空轮询；必须基于
   已返回证据报告未完成，或执行一次有新信息的诊断/终止动作。
6. B-006 当调用方只能使用 direct `exec_command` 且命令转入 session 时，必须只追加
   一次 `write_stdin(chars: "", yield_time_ms: 1800000)`；不得循环或指数增长等待。
7. B-007 当等待 reviewer 或其他 subagent 完成时，必须优先执行一次
   `wait_agent(timeout_ms: 1800000)`，且不得在该等待前后用 `list_agents` 做状态轮询。
8. B-008 当 B-007 的长等待超时时，系统必须只检查一次当前状态；没有可信进展时应
   interrupt/stop-and-return，不得自动开始第二轮等待。
9. B-009 当等待 GitHub CI 时，必须使用单次阻塞的 `gh pr checks --watch` 或
   `gh run watch --exit-status`；不得用 `sleep` 加 `gh ... view` 的模型驱动循环替代。
10. B-010 当运行长本地测试或检查时，原始大输出必须进入 artifact，父上下文只接收
    状态、短摘要、有界 tail 和 artifact 路径。
11. B-011 当实现等待合同后，确定性校验必须检查 queue 与 implx 的必需正向约束，
    并拒绝“direct exec 用最大 yield”“指数增加多次 wait”“重复空
    `write_stdin`”等已知反模式。
12. B-012 当普通 `check_workflow.py` 运行时，等待合同校验必须只读取仓库内受控文件，
    不访问用户 session、`$HOME` 安装副本、GitHub 或网络。
13. B-013 当工具能力缺失、调用报错或等待被取消时，系统不得把部分输出或先前状态
    表述为完成；恢复后必须重新取得当前终态证据。
14. B-014 当相同静态仓库重复运行等待合同校验时，错误顺序、退出码和通过判定必须
    完全一致。
15. B-015 当 queue Skill 因本变更增加说明时，文件仍必须低于 800 行；不得以违反
    VibeGuard 文件上限换取更详细的等待指导。
16. B-016 当实现合并且积累一轮可比的 post-policy implx cohort 后，验收必须分别报告
    `POLL:wait_cell`、`POLL:write_stdin_empty`、`POLL:wait_agent` 和总 turn 数，
    不得用跨策略全历史累计值冒充效果。
17. B-017 当 post-policy cohort 不满足 `wait_cell + write_stdin < 5%`、
    pure poll `< 10%` 或同等工作量 turn 数至少减半时，issue 不得因静态合同通过而
    宣称性能目标完成。
18. B-018 当实现需要修改 queue Skill 或 `skills-lock.json` 时，必须等待 GH-172
    合并并基于最新 main 执行；不得并行覆盖其多文件完整性合同。

## 验收标准

- [ ] queue/implx 明确区分 direct exec 30 秒上限与外层 1800000 ms 长等待。
- [ ] 一个长命令最多产生一次空 `write_stdin`；subagent 等待最多产生一次长
      `wait_agent`，且没有 `list_agents` 轮询包围。
- [ ] 静态校验对正确合同通过，并对每个已知错误模式给出稳定的失败证据。
- [ ] 普通 workflow check 不读取用户 session 或安装目录。
- [ ] queue Skill 最终低于 800 行，lock hash 与最终字节一致。
- [ ] 实现后的独立 cohort 满足三项运行指标后才可关闭 issue。
- [ ] diff 和运行行为均不涉及 GH-160。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-004 B-011 B-013 |
| 错误与失败路径 | covered: B-005 B-006 B-008 B-011 B-013 B-017 |
| 授权/权限 | covered: B-012 B-018 |
| 并发/竞态 | covered: B-003 B-005 B-008 B-013 |
| 重试/幂等 | covered: B-004 B-005 B-006 B-008 B-014 |
| 非法状态转换 | covered: B-004 B-013 B-017 B-018 |
| 兼容/迁移 | covered: B-001 B-002 B-006 B-015 B-018 |
| 降级/回退 | covered: B-005 B-006 B-008 B-013 |
| 证据与审计完整性 | covered: B-010 B-011 B-012 B-014 B-016 B-017 |
| 取消/中断 | covered: B-008 B-013 |

## 发布说明

这是等待编排合同的纠错，不改变业务队列语义。静态校验通过只证明受分发 Skill
包含正确指导；真实 token/turn 改善仍需实现后按独立 cohort 验证。现有活动会话可能
继续使用旧 Skill，更新安装副本与重启仍须走 GH-172 定义的人工边界。
