# Product Spec

## Linked Issue

GH-190

## 用户问题

queue 要求 auto full-drain 创建包含完整目标、四类终止条件、每个可观测 queue action
前重锚和 token
budget 的 Codex Goal；但 checkpoint 的 active `goal` 字段几乎都可缺失，runtime gate
只校验 `goal_candidate`。因此缺预算、缺终止条件或 objective 漂移的 Goal 仍可通过
checkpoint，并在 compaction 后继续低产出长跑。

## 目标

- 用纯函数 builder 生成唯一、稳定的 Goal payload。
- 用 closed schema 和 runtime gate 绑定 Goal、checkpoint、queue 与 run lease。
- 强制预算来源、终止条件、re-anchor 和状态转换，拒绝部分/漂移证据。
- 不让 Goal 替代 GitHub truth、SpecRail gate 或 checkpoint。

## 非目标

- 不选择默认 token budget 数值，也不设计父/子 aggregate budget。
- 不修改 GH-160 的 context 水位、soft stop 或 handoff。
- 不在测试中真实创建/完成 Goal，不自动合并或写 GitHub。

## Behavior Invariants

1. B-001 当 auto + full_queue_drain + Goal capability 全部成立时，系统必须先构建并验证
   Goal contract，再调用 `create_goal`；不得手写自由文本绕过 builder。
2. B-002 当 builder 输入相同且 queue snapshot 顺序等价时，objective、constraints、
   termination conditions 与 `contract_digest` 必须字节稳定；该摘要必须覆盖全部不可变
   Goal contract 字段，不能只覆盖 objective。
3. B-003 当 active Goal 被创建时，必须具有正整数 `token_budget` 和明确
   `budget_source`；用户未提供且没有维护者批准的 pack default 时必须 fail closed，
   不得静默猜值或创建无预算 Goal。
4. B-004 当 objective 构建时，必须包含 queue empty/fully blocked、budget exhausted、
   user interrupt、only human_decisions remain 四类终止条件，缺失/重复均失败。
5. B-005 当 Goal 活跃且即将 resume、开 lane、写 checkpoint、rebind、transition 或执行
   其它 queue/remote action 时，必须先从当前 runtime checkpoint、fresh remote truth 与
   runtime-owned 单调 action attestation 重锚；不可观测的“每 chat turn”不作为合规单位，
   仅依赖对话记忆或 Goal status 不合法。
6. B-006 当 `create_goal` 返回后，checkpoint-facing active contract 必须要求并绑定
   goal ID、objective/contract digest、token budget/source、status、repo、run ID 与
   fencing token；创建前 draft 不得被 checkpoint 当作 active Goal 接受。
7. B-007 当 runtime 不支持 Goal、auth_mode 为 review 或 queue_mode 为 bounded 时，
   不得创建 active Goal；builder 必须输出可直接持久化且通过 gate 的 closed disabled
   binding 与可信 reason/evidence，skill 不得手工拼装 `goal_candidate`/disabled reason。
8. B-008 当 queue 仍含 actionable item 时，Goal 不得进入 complete；只剩
   `human_decisions` 或 queue empty/fully blocked 才允许完成。
9. B-009 当预算耗尽时，状态必须通过不可变 transition evidence 转为 exhausted，先写
   有效 checkpoint/handoff，再停止；不得把 exhausted 标为 complete、改回 active 或
   自动创建新 Goal 绕过预算。
10. B-010 当用户中断时，状态只能转为 interrupted，并保留最新 checkpoint；不得吞掉
    中断后继续运行。
11. B-011 当 Goal 跨 tranche/session resume 时，repo、goal ID、contract digest、
    run ID/fencing token、budget、创建时 queue baseline 与其后合法 rebind 链必须全部
    匹配；否则需要新 Goal/人工决策。
12. B-012 当 goal payload 缺字段、未知字段、非法状态、partial update、旧 digest 或
    tokens_used 超预算时，schema/gate 必须一次报告全部错误并 fail closed。
13. B-013 当相同有效 checkpoint 重复验证时，结果和错误顺序必须稳定；验证不得调用
    Goal API、写 checkpoint、读取 session 正文或访问网络。
14. B-014 当 Goal API 调用失败/取消或返回缺失 ID 时，不得写 active/success
    checkpoint；恢复必须从 fresh Goal state 与 remote truth 重新决策。
15. B-015 当系统选择预算或判断预算缺失/非法时，必须持久化 user budget 与
    pack-default 两个已评估输入及其可信来源/批准证据，disabled reason 必须由 builder/gate
    重新计算；不得由调用方自报 `missing_budget`/`invalid_budget` 绕过可用预算。
16. B-016 当 Goal 状态变化时，checkpoint 必须追加带顺序号、前序摘要和证据摘要的
    immutable transition event；任一 terminal 状态之后出现 active、事件改写/缺口或当前
    status 与链尾不一致时，resume 必须 fail closed。
17. B-017 当 fresh remote truth 改变 queue 时，创建时 baseline 必须保持不可变，当前
    snapshot 只能通过连续、可验证的 rebind event 更新；正常队列进展不得改写 contract
    digest，断链、跨 repo/run/scope rebind 或当前摘要不匹配必须阻断。
18. B-018 当读取 checkpoint v1–v3 时，不得把旧宽松 `goal` 直接作为 active 证据；
    必须通过确定性、版本条件化迁移生成 v4，保留 legacy provenance，并要求 fresh
    remote/budget evidence 后创建新 Goal 或进入合法 disabled 分支。
19. B-019 当 queue/implx agent 需要创建或绑定 Goal 时，必须调用具名 builder CLI，
    使用 closed JSON input/output 与稳定 decision/reason/exit code；不得要求 Markdown
    skill 进程内调用 Python 或自行拼接 tool payload。
20. B-020 当 builder 决定 `auth_mode`、`queue_mode` 或 `goal_capability` 时，必须从
    runtime-owned invocation/capability attestation 导出并绑定 repo/run；checkpoint
    或 CLI 中由 caller 自报的 mode/capability 不得启用或禁用 active Goal。attestation
    缺失/无效时必须 `blocked: untrusted_routing`；只有 verified host receipt 才能把
    capability 判为 unavailable 并进入 disabled 分支。
21. B-021 当使用 pack-default budget 时，必须由只读 GitHub evidence adapter 绑定
    trusted default branch、canonical `workflow.yaml` 内容、引入该值的 merged PR 与
    maintainer approval event；caller 提供的 `approval_ref`、摘要或不存在声明均不算
    批准证据，default branch/config/approval 任一漂移必须阻断。
22. B-022 当 active Goal 被绑定时，`goal_id` 必须来自 runtime-owned、可验证且与
    exact `create_goal` request digest 匹配的 result receipt，并由 fresh live Goal
    snapshot 确认；任意非空 CLI 字符串、旧 receipt、跨 run receipt 或 request/result
    不匹配不得生成 active contract。
23. B-023 当 `bind` 成功时，必须一次输出 closed initial checkpoint bundle，至少包含
    trusted routing/budget evidence、immutable queue/human baseline、current queue
    snapshot、零条 rebind、sequence-0 transition、external transition anchor 与 active
    contract；queue/skill 不得补字段或把局部 bind output 拼成 checkpoint。
24. B-024 当 Goal 状态 transition 被追加时，event 必须引用 versioned canonical
    evidence object，并绑定 artifact ID、source/type 与完整内容摘要；gate 必须按
    complete/exhausted/interrupted/blocked 分支重算并验证其 remote/tool/handoff/
    blocker prerequisites，只有不可重算的 `evidence_digest` 必须阻断。
25. B-025 当 Goal 被创建或更新时，runtime 必须在 checkpoint 外持久化不可回退的
    monotonic revision、status 与 transition-tail anchor，并出具可验证 receipt；resume
    必须用 fresh live snapshot 对账。删除/重写 checkpoint 内 terminal history后声称
    active、anchor 回退/缺失或 external terminal 与 local active 不一致均必须阻断。
26. B-026 当 queue current snapshot rebind 时，必须引用 fresh、schema-valid、
    content-bound GitHub adapter artifact；该 artifact 必须绑定 collector identity、
    repo/default-base、完整分页结果、可信 `as_of` 与 canonical payload digest。
    caller 自报的 `remote_truth_digest` 或无法重算的 snapshot 不得推进 rebind。
27. B-027 当 v1–v3 迁移的可信 routing 要求 active Goal 时，迁移必须先产出 closed、
    gate-valid且 queue-action-blocked 的 `migration_pending` 分支；该分支只允许一次绑定
    `pending_build_digest` 的 Goal create request 及其幂等 receipt recovery，随后才允许
    finalize。取得 fresh remote evidence 与 attested create/live result 后，binder 必须
    原子输出最终 active v4 bundle。普通 `goal:null` v4 不得作为中间态绕过或永久阻断迁移。
28. B-028 当 GH-189 active-run lease contract 及其 runtime implementation 尚未合并
    进目标 default branch 时，GH-190 实现与 active Goal 路径必须保持 blocked；合并后
    必须 rebase 并复用其 `run_id`/`fencing_token`/lease evidence，不得由 GH-190 复制
    或自报一套冲突字段。
29. B-029 当 active initial bundle 生成 sequence-0 event 时，event 只能绑定一个显式
    closed pre-event projection；该 projection 不得包含 sequence-0、其摘要、transition
    anchor 或最终 bundle digest。最终 bundle digest 必须在 event 生成后计算，任何字段
    不得直接或间接覆盖自身，重复计算必须稳定。
30. B-030 当调用 `build` 时，invocation、Goal capability、GitHub queue/policy 与
    GH-189 lease 必须作为四个独立 closed evidence reference 显式传入并分别验证；
    capability 缺失、被塞入 routing envelope 或跨 repo/run 时必须阻断。
31. B-031 当调用 `bind` 时，除了 exact build 与 create-result receipt，还必须显式
    提供 fresh live Goal snapshot evidence；create receipt 不得替代 bind-time live
    state，snapshot 与 goal/repo/run/request/revision 不匹配时不得产出 active bundle。
32. B-032 当 `migration_pending` 需要创建 Goal 时，唯一允许的 remote action 必须是
    builder 产出的 one-shot create request，精确绑定 migration/pending/build/request
    digest 与 provider idempotency key；崩溃重试必须恢复同一 receipt/goal ID，禁止
    重复创建或绕过 pending 直接 finalize。
33. B-033 当 GH-190 implementation route 评估 upstream dependency 时，必须由
    read-only issue adapter 收集 dependency issue/PR、target default-base ancestry、
    contract/runtime implementation merge 与 planned-path overlap evidence，再由
    `route_gate.py` 离线判定；手工 handoff 文本、open spec PR 或调用方自报 merged 不得
    解除 blocked。
34. B-034 当 builder 生成 `create_request_digest` 时，必须使用具名 domain/version、
    closed canonical object 与 RFC8785+SHA-256，精确覆盖实际 `create_goal` tool args、
    repo/run/fencing 和 build binding；host receipt 的 `request_digest` 必须与其字节相等，
    不得在“只 hash tool args”与“hash 整个 envelope”之间自行选择。
35. B-035 当 active Goal 执行 queue rebind 或状态 transition 时，agent 只能调用具名
    closed CLI commands；命令必须声明 required input references、allowed/blocked output、
    stable reason/exit code 与完整 bundle output，skill 不得手工组装 rebind/event 链。
36. B-036 当准备把 Goal 更新为 complete 时，必须先持久化 pending transition 和
    pre-update queue evidence；runtime update 成功后还必须收集因果上晚于该 receipt 的
    fresh queue evidence。若期间新增 actionable item，finalize 不得产生 complete
    checkpoint，必须保留 terminal receipt 并 fail closed 请求人工/新 Goal 决策。
37. B-037 当任一 terminal Goal update 已成功但本地 transition/checkpoint 尚未持久化
    就崩溃时，resume 必须从持久化 pending transition、provider receipt lookup 与 fresh
    live snapshot 确定性补写同一个 event；重复 finalize 必须幂等。缺 pending 或 receipt
    mismatch 时阻断，不得把 external terminal 恢复为 active。
38. B-038 当 verified review/bounded/capability-unavailable 或可信地证明 budget
    missing 时，builder 必须直接输出 closed disabled binding 与相应
    `allowed|needs_human` decision；untrusted routing 或 invalid budget 仍为 blocked 且不
    产出可写 binding。不存在“先 blocked/null 再由 skill 手工补 disabled”的路径。
39. B-039 当任一受保护 queue action 被执行时，必须持久化 runtime-owned 单调
    `action_sequence`，绑定 action type/ID、prior checkpoint digest、fresh GitHub/Goal
    evidence、repo/run/fencing 与前序 action digest；缺号、复用 evidence 或 action 没有
    对应 re-anchor 时 gate 必须阻断，且无需读取 session transcript。
40. B-040 当 checkpoint 与 Goal status 对账时，必须使用完整闭集映射并同时验证
    `stop_reason`：active 仅对应 planning/running/handoff+null；complete 仅对应
    complete+queue terminal reason；exhausted/interrupted/blocked 分别对应
    handoff+budget_exhausted、handoff+user_interrupt、blocked+blocked。其它组合一律失败。
41. B-041 当 GH-174 contract 或其 runtime implementation 尚未合并到 target default
    branch、GH-190 尚未在其后 rebase，或七个共享 queue/lock planned paths 的 ownership
    overlap 尚未消解时，GH-190 implementation route 与 SP190-T4 必须 blocked。集成顺序
    固定为 `GH-172 → GH-174 → GH-189 → GH-190`；该顺序是共享资产串行门，不得用复制
    未合并设计或跳过相邻 rebase 规避。

## 验收标准

- [ ] builder 输出稳定，四终止条件、re-anchor、预算与约束不可省略。
- [ ] active Goal schema closed，draft/active 类型分离，runtime gate 验证
      contract/queue/run/checkpoint binding。
- [ ] 预算缺失、terminal transition、queue rebind 与 v1–v3 migration 都有确定性正反
      例，不能靠调用方自报或改写旧状态。
- [ ] queue/implx 通过 agent-facing CLI 取得 tool payload 与 bound active contract。
- [ ] auto/review/bounded/unavailable 与 complete/exhausted/interrupted 路径全覆盖。
- [ ] routing/capability、pack default 与 Goal ID 只接受 runtime/GitHub trusted
      evidence；伪造 mode、capability、approval 或 `goal_id` 的负例全部 blocked。
- [ ] `bind` 一次产生完整 initial bundle，migration pending 只能执行绑定 pending
      digest 的 one-shot create、receipt recovery 与 finalize，不存在需要 skill 手工补
      字段或无法通过 gate 的普通 v4 中间态。
- [ ] sequence-0 使用无自引用 pre-event projection，`create_request_digest` 有唯一
      domain/canonical coverage；相同输入的 projection/event/final bundle digest 可重算。
- [ ] `build` 显式消费四类独立 evidence；`bind` 显式消费 fresh live snapshot；
      disabled、rebind、prepare/finalize transition 都有唯一 closed CLI producer。
- [ ] migration one-shot create、terminal update 后崩溃与重复 finalize 可从相同 receipt
      幂等恢复，缺 pending/receipt 或重复 Goal create 均 blocked。
- [ ] complete 路径包含 post-update remote recheck；update 窗口新增 actionable item 时
      不生成 false-complete checkpoint。
- [ ] 每个受保护 queue action 的单调 attestation/re-anchor 可由 gate 验证，不读取
      session transcript；checkpoint/Goal status+stop_reason 笛卡尔负例全覆盖。
- [ ] remote rebind 与每类 transition 都绑定可重算 canonical evidence；外部 live
      anchor 能检测 terminal history 截断后伪造 active。
- [ ] dependency adapter/route fixtures 覆盖 GH-174/GH-189 open、只合并 spec、runtime
      未合并、七路径 overlap 未 rebase、跳序与完整按序 merged/rebased 正例。
- [ ] 测试无 Goal API 副作用，full suite 与 forward dry-run 全绿。
- [ ] 不选择 GH-160 的预算值，不含 GH-160 diff。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-004 B-012 B-014 B-015 B-020 B-021 B-022 B-025 B-026 B-030 B-031 B-037 B-038 |
| 错误与失败路径 | covered: B-003 B-006 B-012 B-014 B-019 B-022 B-023 B-024 B-027 B-028 B-029 B-032 B-033 B-034 B-035 B-036 B-037 B-041 |
| 授权/权限 | covered: B-003 B-007 B-011 B-015 B-020 B-021 B-022 B-028 B-030 B-032 B-033 B-038 B-039 B-041 |
| 并发/竞态 | covered: B-006 B-011 B-016 B-017 B-022 B-023 B-025 B-026 B-027 B-028 B-029 B-032 B-036 B-037 B-039 B-041 |
| 重试/幂等 | covered: B-002 B-011 B-013 B-014 B-016 B-017 B-019 B-022 B-023 B-025 B-026 B-027 B-029 B-032 B-034 B-035 B-037 B-039 |
| 非法状态转换 | covered: B-007 B-008 B-009 B-010 B-016 B-024 B-025 B-027 B-032 B-036 B-037 B-038 B-040 |
| 兼容/迁移 | covered: B-007 B-011 B-018 B-027 B-028 B-032 B-033 B-038 B-040 B-041 |
| 降级/回退 | covered: B-003 B-007 B-014 B-018 B-020 B-025 B-027 B-028 B-031 B-032 B-033 B-036 B-037 B-038 B-041 |
| 证据与审计完整性 | covered: B-005 B-006 B-012 B-013 B-015 B-016 B-017 B-020 B-021 B-022 B-023 B-024 B-025 B-026 B-029 B-030 B-031 B-032 B-033 B-034 B-035 B-036 B-037 B-038 B-039 B-040 B-041 |
| 取消/中断 | covered: B-010 B-014 B-024 B-025 B-027 B-032 B-035 B-037 B-039 B-040 |

## 发布说明

active Goal 从松散备注升级为强类型执行合同。没有已批准 token budget 时不再创建
无界 Goal；host 缺少可验证 invocation/Goal receipts 时也不会把 caller 自报数据当作
capability。实现等待 `GH-172 → GH-174 → GH-189` 的 contract/runtime implementation
按序合并并完成 GH-190 rebase，再复用最终 queue/lease contract。这不决定预算值，
预算策略仍由 GH-160/维护者单独处理。
