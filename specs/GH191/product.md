# Product Spec

## Linked Issue

GH-191

## 用户问题

GH-157 已在 queue Skill 写入 Same-Issue Circuit Breaker，但三个阈值仍靠模型阅读
git/checkpoint 后主观判断，runtime schema 没有逐 issue attempt history，gate 也不计算
熔断。compaction 或新会话因此会忘记已做过的近同工作，继续消耗 token 却不收敛。

## 目标

- 记录 append-only、与 head/run/tranche 绑定的逐 issue attempt evidence。
- 用可机器判定的 durable progress fingerprint 计算 GH-157 三类阈值。
- 在开 lane 和远端动作前由 offline gate 一次报告全部 trip reason。
- 保持 park/draft 等外部动作受当前会话授权控制。

## 非目标

- 不重做 GH-157 的 skip label、Done-When 或阈值产品决策。
- 不按提交数量惩罚真实进展，不读取原始 session transcript。
- 不自动 park/draft/close issue，不处理 GH-160。

## Behavior Invariants

1. B-001 当某 issue 开始一次实现 round 时，必须先追加不可变 `attempt_started`
   事件，记录唯一 attempt ID、issue、run、tranche、before head、work fingerprint
   与目标 acceptance/task IDs；开始事件持久化失败时不得进入该 round。
2. B-002 当 round 结束或中断时，必须为同一 attempt 追加且只追加一个不可变
   `attempt_finished` 或 `attempt_interrupted` 事件，记录 after head、
   verification/review/coverage evidence 与 outcome；不得补写、覆盖或删除开始事件，
   缺少 terminal event 的 attempt 必须作为未完成历史 fail closed。
3. B-003 当且仅当新增具名 acceptance/task coverage、修复一个绑定 head 的失败指纹、
   解决 blocking review finding 或产生 terminal GitHub transition 时，才计 durable progress。
4. B-004 当只有新 commit/message、格式改写、重复测试、相同失败或自报“完成”时，
   不得计 durable progress。
5. B-005 当同一 issue 在当前 scope epoch 内累计**五个引用该 issue 的 commit**
   （GH-157 原阈值，按 commit 计数而非 attempt 计数）仍无 durable progress 时，
   breaker 必须 trip，并列出五项证据。durable-progress 过滤只决定哪些 commit 算作
   进展，不放宽计数口径：一个 attempt 产生多个无进展 commit 时按 commit 累加，
   因此不会出现"多轮多 commit 无进展仍未触发"的空档。
6. B-006 当连续三个引用该 issue 的 commit 具有相同规范化 work fingerprint 且均无
   durable progress 时，breaker 必须 trip；计数单位保持 GH-157 的 commit，而不是
   attempt。一个 attempt 内的三个近同 commit 也必须触发，改写 commit message 不得
   改变 fingerprint。
7. B-007 当三个已结束 tranche 都处理该 issue 且没有 durable progress 时，breaker
   必须 trip，并绑定 tranche/run evidence。
8. B-008 当多个阈值同时满足时，gate 必须一次返回全部 trip reasons，稳定排序且不在
   首个原因停止。
9. B-009 当 history 缺失、被覆盖、重复、跨 issue/head/run 串线、未来时间或证据不可读
   时，gate 必须 fail closed，不得按“无历史”继续；未来时间和事件顺序只相对输入中
   摘要绑定的可信 `as_of` 判断，不得读取评估时的系统时钟。
10. B-010 当 breaker trip 时，queue 不得开新 lane或继续该 issue；park/draft/comment
    只有在当前会话明确授权相应远端写时才执行，否则只报告建议。
11. B-011 当人工重新 scope 并解除 parked 时，旧 history 必须保留；新 scope revision
    作为明确 epoch 开始，不能伪造删除旧失败。
12. B-012 当相同 ledger、可信 anchor attestation、remote evidence 与 `as_of`
    重复验证时，decision、fingerprint、原因顺序与退出码必须相同；collector/gate
    只读且输出有界。
13. B-013 ledger 的 event count、tail event digest 与完整 ledger digest 必须由
    ledger/checkout 之外的可信 runtime anchor provider 以单调 generation 持久化并
    出具可验证 attestation；anchor 缺失、回退、pending 或与 ledger 不一致时必须
    fail closed，不能靠内部自洽哈希链声称检测到尾部截断或整体重写。
14. B-014 queue 只能通过确定性 writer helper 追加 baseline/scope/attempt 事件；
    helper 必须校验 previous digest 与 anchor generation，并用 prepare/CAS、
    temp+fsync+atomic replace 和可恢复 transaction 防止并发丢写。collector、gate
    与 agent 均不得直接改 ledger JSON。
15. B-015 第一次启用必须通过显式 `init-baseline` 或 `migrate-baseline` 命令，追加
    绑定 repo immutable ID、issue、可信 head、`as_of`、历史 evidence digest 与授权
    来源的 baseline event，并同时创建外部 anchor；若 anchor 已存在而 ledger 缺失，
    必须判为 history loss，禁止重新初始化。
16. B-016 每个用于时间判断的 ledger/remote evidence snapshot 必须包含可信来源的
    `as_of` 与覆盖完整输入的 snapshot digest；同一份绑定输入不会因稍后重跑而改变
    “未来时间”判定。
17. B-017 每次公开 breaker 评估必须先以受保护 runtime 生成的单次 challenge，从
    anchor provider 获取绑定 `repo_id`、issue、evaluation ID、challenge、当前
    generation/event count/tail/ledger digest 与可信有效期的签名 current-state proof；
    只提供历史 committed attestation、旧 proof、已消费 challenge 或调用方自报
    “latest”时必须 fail closed，旧 ledger + 旧 attestation 不得一起回放为当前历史。
18. B-018 `open-scope` 只能消费一次由可信 adapter 验证为 maintainer 的人工
    rescope/unpark 授权；授权必须精确绑定 repo/issue、旧/新 epoch、旧 anchor
    generation/tail、批准后的 scope/target digest、远端决定来源与一次性 authorization
    ID。writer 权限本身不构成授权，缺失、伪造、错 scope 或重放授权必须失败，provider
    必须在同一 CAS 中原子记录授权消费与 `scope_opened`。
19. B-019 所有影响 progress、head、review、verification、coverage、terminal state
    或 `as_of` 的 evidence snapshot 必须带 allowlisted issuer/adapter 身份、版本与
    adapter-run provenance，绑定 repo/issue/head、完整查询/分页状态、canonical payload
    digest，并由配置的 trust root 验证；调用方 JSON、自报 adapter、未知 issuer、签名
    无效或不完整 collection 必须 fail closed。
20. B-020 GH-191 实现只能在 fresh GitHub truth 证明 GH-172/PR #186、GH-174/PR #192、
    GH-189/PR #193 已按 `GH-172 → GH-174 → GH-189` 串行合入目标 base，且 GH-191 已
    逐步 rebase 后开始；任一依赖仍 open、未合并、head/base 漂移或跳序都必须阻断，
    不得把“有 PR”或条件性 handoff 当作“已合并”。
21. B-021 当 provider 为一次 breaker evaluation 签发 current-state proof 时，必须原子
    建立绑定该 evaluation、generation 与 ledger digest 的短期独占 reservation；在
    offline result 生成后，受保护 runtime 必须以同一 reservation 对 provider current
    generation 执行 compare-and-finalize，并返回绑定 result digest 的签名 decision
    receipt。`append-start` 必须在同一 provider transaction 中 create-only 消费该
    receipt，并以 receipt 绑定的 generation、ledger digest 与 result digest 对 current
    record 做 CAS，成功落下 `attempt_started` 后才可 dispatch lane。只有这条原子链成功
    的 result 才可开 lane。receipt 必须有可信时间源签名绑定的有效期；finalize 后中断时，
    未过期 receipt 只可幂等 retry/recover 同一 `append-start`，过期或明确放弃时只能
    原子 cancel/expire receipt、恢复普通 writer 并阻断当前 action，不得把 candidate
    转成成功。签发后 generation 前移、reservation/receipt 过期或重放、writer 与
    evaluation 竞态、finalize/append-start CAS 失败或 receipt/result 不匹配都必须阻断。
22. B-022 当 `issue_progress_gate.py` 返回 evaluation result 时，输出必须是
    `schemas/evaluation_result.schema.json` 的完整闭合投影：包含 `decision`、`route`、
    `mode`、`current_state`、`issue`、`pr`、`reasons`、`satisfied`、`missing`、
    `required_artifacts`、`human_gates`、`allowed_actions`、`blocked_actions` 与
    `verification_commands`，且不得以 `reason_ids` 代替 `reasons`；任一 decision 分支
    缺字段、额外字段或动作集合与 decision 矛盾时必须被调用方拒绝。
23. B-023 当 baseline/migration 覆盖启用前的 tranche history 时，必须使用受信 runtime
    history adapter 从受保护 checkpoint archive 与可验证的 tracked checkpoint history
    生成 closed、签名且完整性有界的 evidence；每条 tranche 必须绑定 source path/blob
    digest、repo/issue/run/tranche/head/status 与 coverage window。archive 缺段、git
    history 不可达、checkpoint schema/gate 失败、重复/冲突 tranche 或调用方自报 history
    必须 fail closed，不得按零次 tranche 迁移。
24. B-024 当 gate 判断 commit 是否进入 B-005/B-006 计数时，trusted adapter 必须对每个
    commit SHA 使用仓库稳定 issue-reference 谓词派生 `references_issue`，并把 issue、
    commit message digest、predicate ID/version、布尔结果与 evidence digest 一起签名；
    ledger 只持久化该 provenance digest，gate 必须与同一可信 envelope 重新关联。缺失、
    错 issue/SHA、predicate 漂移或 provenance digest 不匹配的 commit 不得被猜测计数，
    而应使 history fail closed。
25. B-025 current-state proof、evaluation reservation 与 decision receipt 必须分别受
    独立 closed schema 和 pack ownership 校验；三者缺少各自必需的
    repo/issue/evaluation、generation、ledger/result digest、有效期、
    provider/trust-root 或签名字段，出现未知字段，cross-binding 不一致，或任一 schema
    未在 pack validator 注册时，公开 gate 必须失败。
26. B-026 GH-191 的 PR 编号、串行依赖与 planned-path overlap 必须只存在于本仓库显式
    dependency overlay，由 read-only repository preflight helper 以 fresh GitHub evidence
    评估；通用 `check_workflow.py` 与 consumer 安装包不得硬编码、查询或阻断
    #186/#192/#193。overlay 缺失/非法、fresh 查询不完整或 B-020 任一条件不满足时只阻断
    本仓库 GH-191 implementation preflight。

## 验收标准

- [ ] 5 commits、3 same-fingerprint commits、3 tranches 三阈值均有边界正反测试。
- [ ] 5-commit 测试至少覆盖 attempts 与 commits 数量不同：两个 attempts 分别含
      3+2 个无进展 commit 时触发，五个 attempts 只有四个 commit 时不触发。
- [ ] 单个 attempt 内三个相同 fingerprint 的无进展 commit 触发第二阈值。
- [ ] 多提交真实进展不误触发，改写 message 不能绕过。
- [ ] start/terminal events 不可变，确定性 writer、外部 anchor 与并发/中断恢复测试
      证明 ledger append-only 且绑定 issue/head/run/tranche。
- [ ] `as_of` 边界测试证明相同输入跨墙钟重跑结果不变。
- [ ] old ledger + old committed attestation/proof 回放、错/已消费 challenge、过期 proof、
      proof 签发后 provider generation 前移、reservation 过期/重放与 finalize CAS 失败均
      阻断；finalize 后到 `append-start` 前 generation 前移、receipt 重放或消费失败同样
      阻断；finalize 后 crash/abandon/expiry 的 retry/recover/cancel 状态机不会永久阻塞
      writer，也不会放行当前 action；fresh proof + reservation + 未过期 decision receipt
      被 `append-start` 原子消费并落下 `attempt_started` 的正例通过。
- [ ] allowed/blocked evaluation fixtures 都完整匹配共享 `evaluation_result`，使用
      `reasons`，缺字段、额外字段、`reason_ids` 替代或动作矛盾均被拒绝。
- [ ] 迁移从可信 checkpoint archive/tracked history 恢复完整 tranche；缺段、浅历史、
      schema/gate 失败、重复/冲突记录与 caller-authored history 均阻断。
- [ ] mixed commit fixture 证明只有可信 `references_issue: true` 的 SHA 进入 commit
      阈值，prefix collision、错 issue/SHA、predicate/version/digest 漂移均 fail closed。
- [ ] current-state proof、reservation、decision receipt closed schemas 均在 pack
      ownership manifest 注册，并有 unknown/missing-field 负例。
- [ ] `open-scope` 缺少人工决定、非 maintainer、错 repo/issue/epoch/scope、授权重放与
      CAS 竞态均阻断；成功路径在 provider 中原子留下 authorization consumption。
- [ ] progress snapshot 的未知 issuer/adapter、伪造 `as_of`、签名/adapter digest 错误、
      分页不全与 caller-authored JSON 均阻断，可信完整 adapter run 正例通过。
- [ ] fresh dependency gate 证明 #186/#192/#193 任一仍 open 或跳过串行 rebase 时不得
      开始 GH-191 实现，并覆盖三者按序合入后的正例；PR 编号只出现在 repo overlay，
      consumer 的通用 workflow check 不受影响。
- [ ] 首次 baseline/migration 可启动；anchor 已存在但 ledger 丢失时不可伪装首次启用。
- [ ] trip 在 lane/remote write 前阻断，外部写仍需授权。
- [ ] compaction/resume forward test 不丢历史，full suite 全绿且无 GH-160 diff。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001 B-002 B-009 B-013 B-015 B-022 B-023 B-024 B-025 B-026 |
| 错误与失败路径 | covered: B-008 B-009 B-010 B-021 B-022 B-023 B-024 B-025 B-026 |
| 授权/权限 | covered: B-010 B-011 B-018 B-019 |
| 并发/竞态 | covered: B-002 B-009 B-013 B-014 B-017 B-018 B-021 B-024 |
| 重试/幂等 | covered: B-002 B-011 B-012 B-014 B-017 B-018 B-021 B-023 B-024 |
| 非法状态转换 | covered: B-002 B-009 B-010 B-011 B-015 B-018 B-020 B-021 B-022 B-026 |
| 兼容/迁移 | covered: B-011 B-015 B-020 B-023 B-026 |
| 降级/回退 | covered: B-009 B-010 B-013 B-017 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 |
| 证据与审计完整性 | covered: B-001 B-002 B-003 B-004 B-008 B-012 B-013 B-016 B-017 B-018 B-019 B-021 B-022 B-023 B-024 B-025 B-026 |
| 取消/中断 | covered: B-002 B-009 B-013 B-014 B-017 B-018 B-021 B-023 |

## 发布说明

本变更不改变 GH-157 阈值，只把其判断改为 durable evidence。已有历史不足时 fail
closed 并要求一次显式 migration/baseline，不能假装从零开始。
