# SpecRail Agent Harness 架构研究记录

> 状态：探索性、非规范（non-normative）
>
> 日期：2026-07-29
>
> 本文记录现状调查和候选方向，不代表已经批准的最终设计，也不作为
> 实现门禁。后续应从这里提炼 ADR、迁移计划和可验证的实现任务。

## 1. 目标

SpecRail 不应只是被拆小，也不应继续作为安装后自动接管仓库的第二套
治理系统。目标是把它改造成一个建立在 Codex 原生 harness 能力之上的
轻量编排层：

- 默认不激活，不污染普通开发请求；
- Core 帮助单任务更快完成，Heavy 帮助长周期、多任务工作可靠恢复；
- 复用仓库原生测试、CI、权限和 GitHub 状态，不复制另一套真相；
- 保留搜索优先、复用原 Issue/PR、规划、验证、恢复、队列编排等有用能力；
- 可以按需接入 VibeGuard 的质量反馈和 remem 的记忆能力，但三者保持解耦。

Core 和 Heavy 应是同一产品的能力档位或运行 profile，而不是两个长期分叉
的代码分支。

## 2. 当前实现调查

当前源码提供三个入口：

- `skills/specrail/SKILL.md`：Core，75 行；
- `skills/specrail-heavy/SKILL.md`：Heavy，58 行；
- `skills/implx/SKILL.md`：队列入口，33 行。

安装器 `tools/install_codex_skills.py` 有 559 行，主要安装到
`$CODEX_HOME/skills` 或 `~/.codex/skills`。当前 Codex 推荐的仓库级位置是
`.agents/skills`，而源码还没有使用 `agents/openai.yaml` 明确设置
`policy.allow_implicit_invocation: false`。

目前 Heavy 本质上仍是一份工作清单，没有真正的持久化运行时、任务图、
线程恢复或产物协议。当前测试主要覆盖安装器，没有覆盖路由误触发、上下文
开销、吞吐量、恢复成功率等 harness 指标。

消费仓库的历史采用方式把四件本应分离的事情绑在一起：

1. 安装能力；
2. 激活能力；
3. 工作流治理；
4. 交付强制。

典型结果是根级 `AGENTS.md` 广泛路由、多个 phase skill 同时可见、
GitHub Actions 对每个 PR 执行 SpecRail checks，以及仓库内复制
state/schema/ledger/checks，形成第二套状态机。

## 3. 根因判断

“一安装就全部启动”不是单一 skill 文件过大的问题，而是多条激活路径叠加：

- 根级 instructions 在每次任务启动时进入上下文；
- skill 的触发描述过宽，多个 phase skill 会互相路由；
- GitHub workflow 对所有 PR 或主分支 push 自动执行；
- vendored checks、runtime ledger 和 schema 把流程变成仓库级常驻治理；
- 安装器没有把“有哪些能力”和“何时激活”分成两个独立配置轴。

因此，仅删除一批 gate 能解除眼前阻塞，但不能从产品层面解决误激活和上下文
膨胀。

## 4. 候选架构

### 4.1 Host/runtime 层

线程、持久化、授权、沙箱、工具调用、skill 加载和事件流由 Codex Core /
App Server 提供。SpecRail 使用这些能力，不重新实现运行时。

### 4.2 Activation router

路由器必须短小、明确、可观测：

- 普通请求不激活 SpecRail；
- 用户明确说 `SpecRail`、`SpecRail Heavy` 或 `implx` 时激活；
- 可选的仓库条件路由只使用精确的 if/then 规则；
- 显式模式在 `agents/openai.yaml` 设置
  `policy.allow_implicit_invocation: false`；
- 加载哪个 profile、为什么加载，应能在运行记录中看见。

### 4.3 Core：任务内环

Core 只保留完成单个开发任务所需的最小内环：

`探索 → 计划 → 编辑 → 仓库原生验证 → PR/交接`

可以进一步拆成窄入口，例如：

- `specrail-plan`：确认目标、范围、done-when 和受影响对象；
- `specrail-verify`：运行仓库原生验证并保留新鲜证据；
- `specrail-handoff`：汇总 diff、风险、未完成项和下一步。

Core 不复制 GitHub readiness、merge 权限、CI 状态或运行 ledger。

### 4.4 Heavy：长周期执行

Heavy 只能显式启动，并增加 Core 没有的长周期能力：

- 一个可持续更新的 `EXEC_PLAN.md`；
- `pending / running / blocked / done` 任务图；
- Codex App Server thread ID 和事件流；
- worktree、文件所有权、有限并发和交叉审查；
- 详细日志落到 artifact，父线程只接收结构化摘要；
- checkpoint、resume、崩溃恢复和上下文压缩后的重建；
- 指向 Git、GitHub 和仓库 CI 的引用，而不是复制授权状态。

### 4.5 `implx`：显式调度器

`implx` 是建立在 Core/Heavy 之上的队列调度器，不是另一个治理框架。它负责：

- 盘点 Issue、PR、review thread 和 CI；
- 优先复用原分支和原 PR；
- 为独立任务选择 Core 或 Heavy；
- 维护有限并发、依赖关系和关闭审计；
- 不自行授予 push、评论、关闭或合并权限。

### 4.6 外环

发布审批、组织安全策略、部署、制品签名和生产回滚属于 GitHub、Harness 或
仓库原生平台的交付外环。SpecRail 只传递可验证证据，不充当权限来源。

## 5. 安装与激活模型

安装应暴露两个互相独立的配置轴：

| 轴 | 可选值 | 默认值 |
|---|---|---|
| Capability | `core` / `heavy` / `queue` | `core` |
| Activation | `explicit` / `repo-conditional` | `explicit` |

仓库级安装默认只写 `.agents/skills`，不修改根 `AGENTS.md`、CI workflow、
checks 或状态文件。如果用户选择 `repo-conditional`，只添加一个最小、可删除的
精确路由块。

VibeGuard、remem 和 SpecRail 的边界建议为：

- VibeGuard：架构、安全、质量反馈提供方；
- remem：可选的长期记忆和上下文检索提供方；
- SpecRail：任务规划、执行和恢复编排；
- Codex/GitHub/Harness：运行时与交付权威。

## 6. 保留与删除

应保留：

- search-first 和重复工作识别；
- 原 Issue、分支、PR 和 review thread 复用；
- spec / exec plan；
- 仓库原生验证、CI 恢复和交接证据；
- 队列盘点、任务依赖、恢复和模板；
- 外部写操作的授权边界；
- 从历史任务中形成 eval 和反馈闭环。

应永久删除：

- 重复的 GitHub readiness 状态；
- SpecRail 自有的合并/许可 gate；
- Goal/lease/attempt runtime ledger；
- attestation 和全 phase 常驻加载；
- 任何把 SpecRail 状态当成交付权威的设计。

历史实现继续保留在 Git 历史或明确的归档目录中，不恢复为活动路径。

## 7. 评测方案

使用 VibeGuard、remem 和其他真实仓库的历史任务，比较三组：

1. 不使用 SpecRail；
2. SpecRail Core；
3. SpecRail Heavy。

至少记录以下指标：

- false activation rate；
- 启动上下文/token 开销；
- time-to-first-edit；
- 首轮 CI 通过率；
- review 往返轮次；
- 人工介入次数；
- 中断后的恢复成功率；
- 多 Issue/PR 队列吞吐量。

只有在手动运行稳定、指标显示净收益后，才把相应环节提升为 skill 或自动化。

## 8. 外部参考

- [OpenAI — Harness engineering](https://openai.com/index/harness-engineering/)
- [OpenAI — Codex skills for open-source maintainers](https://developers.openai.com/blog/skills-agents-sdk)
- [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills)
- [OpenAI — Unlocking the Codex harness](https://openai.com/index/unlocking-the-codex-harness/)
- [OpenAI — Codex ExecPlans](https://developers.openai.com/cookbook/articles/codex_exec_plans)
- [OpenAI — Building self-improving tax agents with Codex](https://openai.com/index/building-self-improving-tax-agents-with-codex/)
- [Harness — AI writes the code; who delivers it safely?](https://www.harness.io/blog/ai-writes-the-code-who-delivers-it-safely)
- [Harness — The agent loop is the new OS](https://www.harness.io/blog/agent-loop-new-os)
- [Harness — How we secured AI worker agents](https://www.harness.io/blog/how-we-secured-ai-worker-agents-in-harness)

## 9. 待验证假设

- 显式激活可以把普通开发请求的误触发率降到接近零；
- 用单一 router + 渐进加载替代多 phase 常驻 skill，能显著降低启动上下文；
- Heavy 复用 App Server 线程和事件，不需要自建 runtime ledger；
- 真实历史任务上的 Core/Heavy 分流，比两个长期分支更容易维护和评测；
- 移除复制状态机后，原生 CI 和 GitHub 仍能完整承担交付权威。

这些假设需要通过消费仓库盘点和基准任务验证，不能仅凭架构直觉定案。

## 10. 本地消费仓库盘点

### 10.1 范围与方法

对 `/Users/apple/Desktop/code/AI/tool` 做只读扫描，共识别 503 个 Git 根目录。
其中大量目录是同一上游仓库的 worktree 或临时克隆，因此按
`remote.origin.url` 归组，而不是按目录数量计算项目数量。

扫描信号包括：

- 根级 `AGENTS.md` / `CLAUDE.md` 的 SpecRail 或 `implx` 路由；
- `skills-lock.json` 和 repo-local SpecRail skills；
- `checks/route_gate.py`、`pr_gate.py`、`runtime_ledger_gate.py` 等复制检查；
- `.github/workflows` 中的自动执行；
- `.specrail` 运行产物和历史痕迹。

结果是 10 个消费仓库存在信号，覆盖 188 个本地 checkout/worktree。另有
61 个目录属于 SpecRail 自身源码或它的工作树，不计入消费仓库。

### 10.2 结论总表

| 仓库 | 当前信号 | 影响级别 | 本地根数 | 判断 |
|---|---|---:|---:|---|
| `argus` | skills + checks + `workflow-check.yml` | P0 | 2 | CI 自动执行，虽无根级自动路由，仍会影响所有 PR |
| `harness` | router skill + checks + `workflow-check.yml` | P0 | 45 | CI 自动执行，工作树扩散很广 |
| `helixflow` | 根级强制路由 + 14 skills + gates + CI | P0 | 1 | 安装、激活、治理和交付四层全部耦合 |
| `remem` | 根级采用规则 + 11 skills + gates + 3 个 CI workflow | P0 | 51 | 49 个工作树仍有 CI 接线；2 个为无 CI 的中间状态 |
| `vibeguard` | 根级采用规则 + 14 skills + gates + CI | P0 | 67 | 每次相关 agent 工作和每个 PR 都可能进入旧流程 |
| `litellm-rs` | 根级 “SpecRail-governed” + 11 skills + gates | P1 | 9 | 没有发现 CI 接线，但 agent 启动和本地执行仍受影响 |
| `rclean` | 根级 SpecRail 路由文本 | P2 | 1 | 没有 repo-local SpecRail skill、checks 或 CI，属于潜在指令耦合 |
| `claude-hub` | 未跟踪 `.specrail/` | P3 | 3 | 运行痕迹，无安装或自动激活证据 |
| `loom` | 未跟踪 `.specrail/` | P3 | 8 | 运行痕迹，无安装或自动激活证据 |
| `tink`（remote 为 `rnk`） | 未跟踪 `.specrail/` | P3 | 1 | 运行痕迹，无安装或自动激活证据 |

这里的“本地根数”反映复制/工作树扩散范围，不表示存在同等数量的独立远端
项目。历史 worktree 也可能落后于上游，迁移时应先处理每个仓库的权威分支，
再决定旧工作树是保留、归档还是删除。

### 10.3 P0 仓库的具体自动路径

`argus`

- `.github/workflows/workflow-check.yml` 执行
  `checks/check_workflow.py --all-specs`；
- 同时校验 adoption manifest，并运行 SpecRail adoption tests；
- 仓库内仍有 14 个 skill 和完整 route/PR/runtime ledger checks。

`harness`

- `.github/workflows/workflow-check.yml` 执行 workflow check、PR gate 测试和
  SpecRail review regression；
- 仓库内仍有 `skills/specrail-workflow` 和复制 checks；
- 主 checkout 还存在 tracked `.specrail` 内容和大量本地 runtime 产物。

`helixflow`

- 根 `AGENTS.md` 要求先加载 `skills/specrail-workflow`，再加载一个 phase
  skill；
- 产品、架构、跨模块、公共 API、工作流策略和模糊任务默认走 SpecRail；
- `.github/workflows/specrail-check.yml` 对 workflow pack 执行检查。

`remem`

- 根 `AGENTS.md` 依据 `skills-lock.json` 和 router skill 宣告仓库采用
  SpecRail；
- 指示运行 `checks/route_gate.py`，并加载 11 个旧 phase skill；
- `ci.yml` 校验 gate wiring 和同步 checks；
- `closure-audit.yml` 与 `sensitive-governance.yml` 继续创建和消费
  `.specrail/runtime` 证据。

`vibeguard`

- 根 `AGENTS.md` 要求 Issue/PR 工作读取 SpecRail workflow pack；
- 明确写有 `pr_gate.py`、`runtime_ledger_gate.py` 不可绕过；
- `.github/workflows/workflow-check.yml` 对 PR 和主分支 push 运行 workflow
  check 与 adoption smoke tests；
- 仓库内仍有 14 个旧 skill 和完整复制 checks。

### 10.4 全局安装层

`/Users/apple/.codex/skills` 仍安装着 15 个旧 SpecRail 相关 skill：

- `implement-specrail-issues`；
- `implx`；
- 13 个 router/phase/gate skill。

这些 skill 均没有 `agents/openai.yaml`，因此没有机器可读的
`policy.allow_implicit_invocation: false`。其中多数 description 虽写了
“Explicit invocation only”，但这是自然语言约束；`implement-specrail-issues`
的触发描述仍覆盖“实现 open issues、创建 PR、使用 threads”等普通队列工作，
是当前最明显的全局误触发入口。

全局安装状态与当前源码也不一致：当前源码已经收敛为 `specrail`、
`specrail-heavy`、`implx` 三个入口，但全局仍是旧的 15-skill pack。这说明
即使消费仓库完成迁移，只要全局 pack 不更新，隐式激活风险仍然存在。

全局 `/Users/apple/.codex/AGENTS.md` 没有要求自动运行 SpecRail；它只把
“用户明确指定 SpecRail”列为硬约束。因此全局问题主要来自 skill 可见性与
触发元数据，而不是全局 instructions。

### 10.5 风险判断

当前问题存在三个独立层次：

1. **全局能力泄漏**：旧 skill pack 对所有仓库可见；
2. **仓库启动污染**：根级 instructions 在 agent 启动时进入上下文；
3. **交付自动执行**：GitHub Actions 不需要 agent 激活也会运行旧 checks。

只修其中一层都不能彻底解决：

- 只删 CI，agent 仍可能被根 instructions 或全局 skill 路由；
- 只删 repo-local skills，CI 仍会执行复制 checks；
- 只更新全局 skills，已经采用的仓库仍保留 instructions、checks 和 workflow。

### 10.6 建议迁移顺序

1. **先修全局安装器和元数据**：只安装三个新入口，使用
   `agents/openai.yaml` 禁止隐式调用，移除旧 pack 的活动安装，但在 Git 历史
   或 archive 中保留其实现；
2. **建立消费仓库迁移命令**：只读 inventory、预览 patch、显式 apply，
   能分别移除 AGENTS 路由、CI 接线、checks/runtime 状态和旧 skills；
3. **先迁 P0 五库**：`argus`、`harness`、`helixflow`、`remem`、
   `vibeguard`，每库在权威分支单独验证原生 CI；
4. **再迁 P1/P2**：`litellm-rs` 移除旧 pack 和治理文本，`rclean` 把
   SpecRail 专用路由改为普通仓库开发规则或精确的显式触发；
5. **最后处理 P3 运行痕迹**：先确认是否还有恢复价值，再归档或清理
   `claude-hub`、`loom`、`tink` 的未跟踪 `.specrail` 目录；
6. **建立回归 eval**：确保普通 issue、普通 PR 修复和普通 CI 诊断不会加载
   SpecRail；只有显式 `SpecRail` / `SpecRail Heavy` / `implx` 会激活。

迁移不能通过把旧 gate 换一个名字继续保留。完成标准应是：消费仓库只剩
原生 instructions/test/CI 作为权威，SpecRail 成为显式、可卸载、可评测的
帮助层。

## 11. 实施状态

2026-07-29 开始按本记录逐项实施。第一项只处理 SpecRail 自身的安装和激活
边界：

- 三个入口增加 `agents/openai.yaml`，机器级禁止隐式调用；
- 用户级默认目标从旧 `~/.codex/skills` 改为官方 `~/.agents/skills`；
- lock v2 同时校验 `SKILL.md` 和 agent metadata，避免安装副本静默漂移；
- 旧清理清单补齐 `specrail-pr-gate` 与
  `implement-specrail-issues`；
- 安装器支持显式指定旧目标和 archive，在安装新 profile 后把已知
  SpecRail-managed 目录移出活动路径并保留可恢复副本。

消费仓库尚未在这一项中修改；它们继续按 10.6 的顺序逐库迁移。
