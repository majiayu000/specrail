# Product Spec

## Linked Issue

GH-208

## 用户问题

PR #210 已落地合同行数上限、CI size gate、一次 gate 审计和分层阅读集，但 GH-208
仍不能关闭。当前缺口集中在三处：

- A 要求在真实队列中验证单 issue fastlane 的启动耗时，以及无真实 finding 时
  multi-lane PR 的 review 收敛轮次；本地 fixture、dry-run 或文字推断不能替代。
- C 的审计报告仍声明 36 个 `checks/*.py` 模块、14,779 行，漏掉
  `checks/github_tier_evidence.py`；当前固定 main 快照实际为 37 个模块、15,158 行。
- D 原始目标是 fastlane 启动阅读集不超过三个具名文件，但 PR #210 把六个文件定义为
  fastlane startup。六文件即使合计不超过 30KB，也没有满足文件数合同。

若继续把“低于字节预算”“已有一张手写表”或“流程看起来更快”当成完成证据，
GH-208 会在缺少真实测量、漏审新 gate 和静默改写验收口径的情况下被提前关闭。

## 目标

- 用可复核的真实运行证据验证 fastlane 启动时间与 multi-lane review 收敛轮次。
- 纠正 PR #210 审计遗漏，并让审计完整性随目标快照动态校验，而不是依赖手写总数。
- 恢复 GH-208 原始三文件 agent-facing fastlane startup 合同，同时完整记录 route
  validator 的必要依赖读取，并保留 30KB/60KB 字节预算。
- 让每个 C 组模块处置绑定可验证且发生于固定审计窗口内的 typed
  incident/security evidence，拒绝自由文本或新鲜采集时间自证。
- 由独立于 caller、agent 和 adapter 的受信 provider 完整中介实际 context 注入及
  session 内全部仓库读取；任何观测旁路或事件丢失都失败闭合。
- 让任何验收口径变更都需要显式人工决定，禁止实现者静默用六文件替代三文件。

## 非目标

- 不重开 PR #210 已完成的 B（Skill 行数硬上限）和 E（既有回归测试）行为。
- 不在本 issue 中执行审计报告列出的合并、删除、warning 降级或 #198 收敛工作。
- 不用合成 fixture、样本演示、旧 transcript 或缓存命中推算真实运行耗时。
- 不改变 review finding 的严重级别、独立审查、人类 merge 授权或 issue 关闭权限。
- 不把 GH-208 的一次性真实运行证据推广成通用 telemetry 产品或新持久化 schema。

## Behavior Invariants

1. B-001 当验收单 issue fastlane 启动性能时，必须执行一次真实、当前 main 上的
   end-to-end fastlane 运行，并从首次 agent-facing 仓库合同读取、启动 validator 或查询
   远端事实三者中最早事件之前开始计时，到目标 issue 已完成资格判定、existing-work
   映射和真实 `implement` route gate，且可进入第一个 scoped implementation action
   时停止计时；agent contract 与 validator dependency 的全部读取及远端前置都在该
   elapsed 内，该区间必须不超过 10 分钟。
2. B-002 每次 B-001 测量必须记录不可变的 repository、base/head SHA、issue、PR（若
   已创建）、开始/结束 UTC、单调 elapsed、执行器版本，以及由 executor/runtime
   控制、独立于 caller、agent、adapter 和被测仓库代码的
   `trusted_observation_provider` 生成的完整 measurement-bound、append-only
   repository read/context-injection event ledger。provider 必须在封闭 session
   namespace 内强制中介全部仓库 byte 进入 agent/model context 的路径，以及 agent、
   validator、import、后代与同 session sibling process 的全部仓库文件读取；ledger
   必须按 reader identity 把事件派生为
   `agent_contract_read_set` 与 `validator_dependency_read_set`，记录 path、bytes、
   command/process/session identity、递增 sequence、run binding 和 phase，并携带
   provider identity/policy/coverage attestation。缺失任一身份、时间边界、事件连续性、
   分类依据、读取/context 事件，或 provider 无法证明无旁路完整中介时不得报告
   fastlane 通过。
3. B-003 真实 fastlane 测量不得由 dry-run、fixture、mock GitHub、预先生成的
   queue plan、旧 session/transcript、手工删去启动步骤或仅计量某个后置 phase 替代；
   实际发生在计时区间内的仓库文件读取和远端前置必须全部进入 elapsed 与 ledger。
   read-set 分类只能由 trusted provider 观察到的 session principal、固定 validator
   command identity、namespace 与 process identity 派生，调用者自报 `phase` 或仅凭
   PID ancestry 不得改变分类；未知 reader、未归类读取、validator 输出仓库原文却未把
   来源计入 agent contract，或 agent 直接读取后改称 validator dependency，均必须
   fail closed。measurement 不得接受调用者、agent 或 adapter 预先提供的 ledger、
   read-set 汇总或可重放的其它 run event stream 作为通过证据；即使其 nonce、sequence、
   hash chain 与 PID 自洽，只要和 provider 直接交付给 verifier 的完整事件集合不一致，
   仍必须失败。provider 不可用、事件 overflow/drop、namespace/process escape、
   unmediated repository access 或 context-injection bypass 时必须拒绝访问并把结果标记
   `incomplete`，不得回退到 self-report。
4. B-004 当 fastlane 运行失败、取消、被人工打断、证据采集不完整或 head/issue
   eligibility 在测量中漂移时，本次结果必须标记为未完成或失败；重试使用新的
   measurement ID，不能覆盖、拼接或挑选旧片段形成通过结果。
5. B-005 当验收 multi-lane PR 流程时，必须使用一个真实 PR、明确的 lane roster 和
   exact-head review artifacts；若该 head 没有真实 code/spec finding，则从首轮
   review dispatch 到 terminal review evidence 的收敛轮次必须不超过 1。
6. B-006 artifact shape、manifest 或元数据修复在 head 与 reviewer conclusion
   均未变化时不增加 review round；head 变化、真实 finding、审查范围缺失或 reviewer
   输出不可恢复时必须进入正常 re-review，不能为了满足一轮目标把它改名为格式修复。
7. B-007 若 B-005 的真实 PR 出现 code/spec finding，证据必须如实记录 finding 与后续
   round，本样本不得冒充“无真实 finding”的一轮正例；完成 GH-208 仍需另一个满足前提
   的真实样本，除非 maintainer 明确修改该验收条件。
8. B-008 A 组证据必须以可定位的 issue comment 或等价 GitHub durable link 附到
   GH-208，包含 measurement ID、边界、结果和原始 artifact 路径/链接；只给汇总结论、
   私有本地路径或无法复核的聊天文字不满足关闭条件。
9. B-009 对固定 `origin/main@6b6e1f702a2098325ba34dd81f5f0c565f3c0134`
   的 C 组审计必须覆盖排序后的全部 37 个 `checks/*.py` 模块，逐文件行数合计为
   15,158，并显式包含 219 行的 `checks/github_tier_evidence.py`。
10. B-010 审计完整性必须由目标 git ref 动态枚举 `checks/*.py` 得出模块集合、逐文件
    行数、模块数和总行数；validator 不得以手写 allowlist、预期 37 或预期 15,158
    代替枚举结果，基线常量只能用于证明 B-009 的固定快照。
11. B-011 审计表中的每个动态发现模块必须且只能有一行，并包含 path、line count、
    处置结论及唯一 typed basis。basis 闭集为：由 fresh same-repository provider 验真、
    绑定准确 source event 且其权威 `occurred_at` 位于固定 UTC 窗口
    `2026-06-28T00:00:00Z` 至 `2026-07-27T23:59:59Z`（含端点）的 `incident`
    reference；同时绑定稳定 property ID、
    immutable contract anchor 与可执行负例的 `security_property`；或绑定固定 30 天
    窗口、module-derived query、fresh provider 与 immutable-ref repository search
    完整负向结果的 `no_record`。自由文本、仅格式正确但无法解析的
    URL/commit/artifact、未绑定本模块的事件、安全声明缺 contract/test anchor、调用者
    自报空搜索结果均不得支持处置。`incident.collected_at` 必须与 `occurred_at` 分离；
    新鲜采集旧事件、缺失/越界/自报发生时间、仅靠可伪造 author/committer date 的
    fix commit，或未绑定 trusted publication/run event 的仓库 artifact 均不得满足
    incident window；旧事件只可作上下文。`no_record` 不得支持“因真实拦截/安全属性而
    保留”的结论。处置也必须来自闭集并与 basis 类型兼容；合并/收敛处置缺可解析 target、
    `no_record + retain` 或 Markdown 与 evidence record 处置不一致时必须 block。
12. B-012 当审计表漏项、重复、额外列出目标 ref 不存在的模块、行数不匹配、行数和
    不等于总数，或摘要处置计数不能覆盖全部行时，审计验证必须 fail closed 并一次性
    报告完整差异，不能只改标题总数形成表面通过。
13. B-013 当审计目标从一个 git ref 变为另一个 ref 时，必须重新动态生成/验证完整
    inventory；新增、删除或重命名模块不能沿用旧 ref 的“全量审计”结论。
14. B-014 默认 GH-208 `agent_contract_read_set` 必须是 trusted provider 从实际
    context-injection 事件派生的以下三个文件闭集，数量
    `<=3`：`skills/implx/SKILL.md`、`skills/specrail-implement/SKILL.md`、
    `skills/specrail-pr-gate/SKILL.md`。该集合包括计时区间内直接进入 agent context
    的所有仓库合同 bytes；任何第四个此类文件都会使 D 组失败。真实 route gate 在隔离的
    固定 validator process 内读取的 `workflow.yaml`、`states.yaml`、`labels.yaml` 与
    Python module 必须进入独立 `validator_dependency_read_set` 并计入 B-001 elapsed，
    但不冒充 agent-facing startup contract；同一路径一旦被 agent 直接读取或由 validator
    输出原文到 agent context，仍必须进入 `agent_contract_read_set`。
15. B-015 B-014 的三个 agent contract 文件按实际进入 context 的 UTF-8 bytes 求和必须
    `<=30 KiB`；文件数和字节数是两个同时成立的门禁，六文件 `<=30 KiB`、三文件超预算、
    把 agent read 改称 validator/bootstrap、隐藏 validator dependency 或让 validator
    转发原文规避计数均不得通过。
16. B-016 只有 maintainer 在 GH-208 或其实现 PR 上给出显式决定，精确声明替代文件
    集合、上限、理由和适用 revision，才可修改 B-014；普通 review/merge/queue
    authorization、PR body 自报或实现者解释均不能把六文件替代升级为已授权合同。
17. B-017 `full_queue_drain` 的 agent-facing startup contract 集合仍必须由同一
    reader-principal 规则动态计量并保持 `<=60 KiB`，validator dependencies 也必须独立
    记录并计入端到端 elapsed；修复 fastlane 三文件合同不得通过把 agent contract 文件
    或 validator 成本转移到未计量的 full-drain/bootstrap phase 来制造通过。
18. B-018 当 startup 测量期间文件、ref、任一 read set、provider
    identity/policy/coverage、validator identity 或 session namespace 变化，或计量被
    取消/中断时，结果必须失效并从同一不可变 ref 重新测量；并发运行之间不得复用彼此的
    provider attestation、ledger、read-set 或 elapsed 证据。

## 验收标准

- [ ] 一次真实 single-issue fastlane 运行具有完整身份/时间/read-set 证据，启动耗时
  `<=10 min`，并附到 GH-208。
- [ ] 一次无真实 finding 的真实 multi-lane PR 在一个 review round 内收敛，或如实
  报告 finding 后另取合格样本；证据附到 GH-208。
- [ ] 固定 main 快照的审计动态证明 37 个模块、15,158 行，包含
  `checks/github_tier_evidence.py`，每行均由 verified `incident`、
  `security_property` 或 `no_record` basis 绑定处置。
- [ ] 审计 validator 对漏项、重复、额外项、行数/总数/摘要不一致，以及自由文本 basis、
  不存在/跨仓库/未绑定模块的 evidence、缺 contract/test anchor 的 security property、
  `no_record + security retain` 全部 fail closed；incident 的发生时间必须来自准确
  trusted source event 且落在固定窗口，fresh collection 不能让旧事件合格。
- [ ] fastlane `agent_contract_read_set` 为三个具名 Skill 且 `<=30 KiB`；真实
  route-gate YAML/Python dependencies 在独立集合完整可见并计入端到端耗时；第四个
  agent contract、未知/漏报读取、调用者重分类或 adapter 省略事件但提交自洽 ledger
  均明确失败；provider 不可用、overflow、escape 或 context/read 旁路只能得到
  `incomplete`。
- [ ] full-drain agent-facing startup set 仍动态计量并 `<=60 KiB`，validator dependency
  与 elapsed 不被隐藏，所有 focused workflow/depth 验证通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002 B-008 B-010 B-011 B-014 B-016 |
| 错误与失败路径 | covered: B-004 B-007 B-012 B-015 B-018 |
| 授权/权限 | covered: B-007 B-008 B-016 |
| 并发/竞态 | covered: B-004 B-013 B-018 |
| 重试/幂等 | covered: B-004 B-006 B-012 B-013 B-018 |
| 非法状态转换 | covered: B-004 B-007 B-008 B-016 |
| 兼容/迁移 | covered: B-013 B-014 B-017；PR #210 的 B/E 既有行为保持 |
| 降级/回退 | covered: B-004 B-007 B-012 B-015 B-016 |
| 证据与审计完整性 | covered: B-002 B-003 B-005 B-008 B-009 B-010 B-011 B-012 B-014 B-015 B-018 |
| 取消/中断 | covered: B-004 B-018 |

## 发布说明

这是 GH-208 剩余 A/C/D 的规格补全。PR #210 的 B/E 不被撤销；C 的历史审计将绑定
固定 main ref、typed trusted evidence 并补齐遗漏；D 恢复 issue 原始三份
agent-facing contract 文件口径，同时把 route validator 的必要读取单独披露并纳入
端到端耗时。implementation PR 与真实证据使用 `Refs #208`，在 A/C/D 全部有可复核
证据前 GH-208 保持 open。
