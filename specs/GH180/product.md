# Product Spec

## Linked Issue

GH-180

complexity: large

## 用户问题

SpecRail 目前对同一个 spec packet 给出互相冲突的生命周期要求：
`ready_to_spec` / `write_spec` 只负责形成 `product_spec` 与 `tech_spec`，而
`task_plan` 由 `ready_to_implement` / `implement` 阶段创建；但全量 packet 校验又把
缺少 `tasks.md` 一律视为失败。结果是新的 spec PR 只能在“遵守 route 但 CI 红”与
“提前写 tasks、越过 readiness 边界”之间二选一，也会让三文件齐全被误读为已经
获得实现授权。

## 目标

- 定义 staged spec packet 的单一生命周期，使 spec 写作与 task planning 各自由
  正确 route 和可信 readiness 触发。
- 将 packet 的 artifact shape 与 implementation readiness 分开判定，允许
  product/tech-only packet 通过全量结构校验，但绝不因此获得实现资格。
- 为 spec-first implement route 定义无循环依赖的 task plan 生成顺序。
- 保持既有三文件 packet 兼容，同时为 GH-180 自身及错误地提前生成 tasks 的在途
  spec PR 提供可审计、不可扩权的迁移路径。

## 非目标

- 不改变 issue #165 的 Gate Availability 行为契约。
- 不自动授予 `ready_to_implement`、`spec_approved` 或任何实现、审批、merge 权限。
- 不删除 spec-first task planning，也不允许该路径的代码实现先于有效 `tasks.md` 开始；
  本变更不向原本无 spec packet 的 direct bug 强加 task plan。
- 不把 issue body hint、文件存在、agent 自报或历史成功结果升级为可信 readiness。
- 不弱化 product、tech 或 tasks 各自已有的内容校验。

## Behavior Invariants

1. B-001 当一个 packet 含有效 `product.md` 与 `tech.md`、且不含 `tasks.md` 时，
   其 artifact shape 必须判为 `staged`；`--all-specs` 必须将其视为合法的 spec
   阶段 packet，而不是因为缺少 `tasks.md` 报全面失败。
2. B-002 当一个 packet 同时含有效 `product.md`、`tech.md` 与 `tasks.md` 时，
   其 artifact shape 必须判为 `complete`，并继续执行三类 artifact 的全部既有
   内容约束。
3. B-003 `staged`、`complete` 与 implementation readiness 是不同维度：
   `complete` 只证明 artifact 齐全，不能单独证明 `ready_to_implement`、
   `spec_approved`、route 允许或实现授权；`staged` 也不得被呈现为
   implementation-ready。
4. B-004 当 `product.md` 或 `tech.md` 任一缺失、为空、不可读或内容无效时，packet
   必须判为非法；`tasks.md` 存在、旧成功记录或 readiness 证据均不得掩盖该失败。
5. B-005 当 `tasks.md` 存在但无效，packet 不得从 `complete` 降级成看似成功的
   `staged`；必须明确报告 task plan 失败。文件缺失与文件存在但无效具有不同、
   可审计的判定。
6. B-006 当可信当前状态为 `ready_to_spec` 且 `write_spec` route 为 `allowed` 时，
   route 只要求并创建 `product_spec` 与 `tech_spec`；不创建 `task_plan`，且
   product/tech 写成后必须能以 `staged` 形态通过 packet 校验。
7. B-007 当 spec-first 工作进入 `implement` route 时，入场前提必须是可信当前状态
   `ready_to_implement` 加有效 product/tech；入场检查不得预先要求尚应由该 route
   创建的 `task_plan`。staged packet 的 machine result 必须只授予独立的
   `task_planning` capability，明确阻断 `production_implementation`；route 创建并验证
   `tasks.md` 后，必须对 complete packet 重新取得只授予
   `production_implementation` 的结果，代码实现才可开始，消除“先有 tasks 才能进入创建
   tasks 的 route”循环。consumer 必须声明消费目的，且 production verify 必须确定性拒绝
   staged/task-planning result，即使其通用 gate `decision` 为 `allowed`。
   shared runtime lifecycle mapping 中 `needs_tasks` 只能对应
   `ready_to_implement`，不得继续映射为 `spec_approved` 或更早状态。
8. B-008 对确实从 `ready_to_spec` 进入 spec-first 写作的工作，默认及
   `auth_mode: review` 路径必须同时具备：可信、
   按时间有序且完成 `ready_to_spec → spec_pr_open → spec_review → spec_approved` 的
   lifecycle approval evidence；被接受的 exact-head maintainer `APPROVED` review
   `submittedAt` 必须严格早于被接受的 `spec_approved` label event，后者又必须严格早于
   fresh trusted `ready_to_implement` label event。先打任一 lifecycle/readiness label、
   后补 exact-head review 不得追溯授权；只看采集时间或当前 label 不足以证明该顺序。approval
   必须绑定同一 repository 的 spec PR、该 PR 的不可变 exact head SHA，以及有权限 maintainer
   对该 exact head 的 approval；被接受的 `ready_to_implement` event actor 也必须独立通过同一
   maintainer permission policy，权限缺失、查询失败或低于阈值均 fail closed，不能从“能加
   label”或 approval actor 的权限推断。被批准的 product/tech 摘要必须从该 SHA 的 blob
   计算，不能从当前工作树、当前 base 或调用方给出的 hash 推断。duplicate gate 只可排除这个
   exact approved spec-only PR 及其 exact-head branch：repository id、PR number、head
   repository/ref/SHA 与完整 changed-path 集必须全部匹配 approval source。duplicate collector
   必须先由 repo-owned workflow artifact 配置与 closed role classifier 确定
   `product_spec | tech_spec | task_plan` 的路径 allowlist，再验证 exact-head
   manifest `spec_refs` 是该 allowlist 的无重复子集且与 implementation `paths` 完全 disjoint；
   manifest/caller 不能新增 role 或扩大 allowlist。changed paths 必须包含 product/tech、
   全部属于经分类的 validated `spec_refs`，且不得包含 planned implementation path。其它引用
   本 issue 的 PR/branch、该 PR 的 head/path 漂移或不完整查询仍按 duplicate fail closed。
   只有当前用户明确发起的 `auth_mode: auto` invocation 可以按 `workflow.yaml` 现有 policy
   waive `spec_approval`；runtime 必须在 runtime-owned grant registry 中存在由用户授权、
   与 current invocation/repository identity/issue/route 和精确
   `waived_human_gates: ["spec_approval"]` 匹配的
   active grant。调用方提供的 authorization record 只能作为 grant selector，不能创建、
   改写或证明授权。provider 必须从 registry 取出 grant 并把其稳定摘要连同 current invocation
   identity/generation 与 immutable repository id 绑定到独立签发的 live trust anchor。SpecRail client 必须通过固定的
   authenticated local IPC adapter 执行 fresh challenge-response，并调用 runtime-owned、
   可移植的 RFC8785-JCS/Ed25519 verifier；endpoint/provider/verifier、peer identity 与 trust
   root 均不能由 CLI、environment、authorization record、repository 或 saved result 选择。
   provider、grant registry 或 verifier 未部署/不可用时 auto 必须 fail closed。
   持久化配置、packet shape、readiness label、caller selector、旧 grant、旧 anchor 或旧 saved
   result 均不能构成 waiver。provider/registry/verifier 未部署或不可用、peer/key/signature
   无效、grant/key 被撤销、challenge 重放或 generation 改变时 auto 必须 fail closed；可以显式改走正常
   human-lifecycle review route，但不得 silent downgrade 或声称 auto available。无论是否 waive
   `spec_approval`，fresh trusted readiness、fresh
   duplicate-work evidence、packet validation 和 saved-result binding 均不可 waive。
9. B-009 readiness-sensitive 判定只能消费可信、在配置 freshness 窗口内、与 linked
   issue 一致的 label evidence；CLI `--state ready_to_spec|ready_to_implement`、CLI
   `--label ready_to_spec|ready_to_implement`、缺失采集时间、未来时间、body hint、agent
   声明、过期 evidence、错误 issue 或互相冲突的 readiness label 均不能产生
   implementation-ready 结论。
10. B-010 `--all-specs` 在没有 readiness evidence 时仍必须完整校验并报告 packet
    的 `staged` / `complete` artifact shape，但必须把 implementation readiness
    明确保留为“未证明”，不得把 evidence 缺失静默折算为允许实现。
11. B-011 既有有效三文件 packet 升级后继续判为 `complete`，无需删除或重写
    `tasks.md`；它们也不会因兼容处理而自动获得当前 implementation readiness。
    既有有效 product/tech-only packet 则按 `staged` 规则验证。
12. B-012 对仍处于 `ready_to_spec` 的在途 spec PR，若曾为迎合旧 validator 提前
    加入 `tasks.md`，在可信 `write_spec` route evidence 下删除该 task plan 必须是
    合法的纠偏，并把 packet 恢复为 `staged`；该纠偏不得制造
    `ready_to_implement` 或 spec approval 证据。
13. B-013 在 spec-first 工作的 `ready_to_implement` 或更晚阶段删除、遗漏或破坏有效 `tasks.md`
    时，implementation-ready 判定必须失效并阻断代码实现；系统不得沿用删除前的
    readiness、验证或 task plan 证据。
14. B-014 spec-first readiness-sensitive 结果必须同时绑定 issue evidence、spec approval authorization
    evidence（review 路径的 ordered exact-head lifecycle 或 auto 路径的 runtime-registry
    grant）、duplicate-work evidence、immutable repository id + canonical repository name，
    以及当前 packet artifact。repository identity 必须贯穿 fresh issue/duplicate evidence、
    auto grant selector、runtime-owned grant、challenge request、signed response、
    `authorization_grant_sha256`、cross-challenge stable binding、saved route result 与 consumer
    重验；缺失、跨仓、rename 后 name 不一致或任一环节不匹配均拒绝，不能只靠相同 issue/route
    复用授权。issue 与 duplicate evidence
    各自必须同时产生：包含 `collected_at` 的完整 envelope audit sha256，以及只排除
    `collected_at`、其余规范化内容全部保留的 stable semantic snapshot sha256；跨 fresh
    capture 只比较 semantic snapshot，且必须独立重验每次 envelope 的 `collected_at`
    freshness，不能因时间戳自然变化误判语义漂移，也不能从 stable digest 删除其它字段。
    approval 必须比较只含 product/tech 的 `spec_snapshot_sha256`；saved-result 与 artifact
    漂移必须另用包含当前已发现 product/tech/tasks 的 `packet_snapshot_sha256`，创建合法
    `tasks.md` 不得使已批准 spec 自动变 stale。
    消费保存的 route 结果时，consumer gate 必须接收重新采集的 fresh issue evidence 与 fresh
    duplicate-work evidence，并重新验证同一 auth mode/grant selector；auto 路径的初次 route
    与 `--verify-result` 必须各自消费 runtime provider 对各自 fresh unpredictable challenge
    的响应，并由 runtime-owned verifier 独立重验 authenticated peer、RFC8785-JCS/Ed25519、
    active/non-revoked key、generation、expiry、challenge、issue/route、runtime-owned grant
    摘要和精确 waived gates。两个响应的 stable cross-challenge binding 必须绑定同一 current
    invocation/generation/grant，但排除 challenge/request、签发/过期时间、signature 与可合法
    rotation 的 `key_id`；每个 fresh response 的 `key_id` 和 key activity 仍须分别 fail-closed
    校验。consumer 随后重验 freshness、open PR 与 remote branch snapshot 再比较 semantic
    摘要；不得只把 saved hash 与 saved result 自身比较，也不得让 caller record 或 saved result
    自报 current invocation、repository identity 或授权。saved result 必须记录闭合的
    `authorization_scope` 与 `allowed_actions`；`--verify-result` 必须要求显式
    `--consume-for task_planning|production_implementation` 并做 exact match，尤其不得让
    `task_planning` scope 满足 production consumer。任一 artifact、linked issue、repository
    identity、approval/grant、runtime
    current generation、duplicate-work semantic snapshot 或 freshness 状态变化后，消费者必须
    确定性拒绝旧结果并基于最新 snapshot 重跑；旧 selector、旧 anchor 与旧结果不得授权新
    invocation 或新内容。
15. B-015 对相同 artifact snapshot 与相同 evidence 重复校验必须得到同一 shape
    与 readiness 结论；失败后重试必须重新验证全部前提，不能只修一个字段后复用
    旧的成功片段或 rejection 之前的授权。
16. B-016 GH-180 在旧 validator 下使用一次性 `auth_mode: auto` bootstrap exception：
    live issue 的 `ready_to_spec` label 与后续 direct label transition 可观察，coordinator
    报告 `write_spec: allowed` 后形成 product/tech，并报告 `implement: allowed` 后创建
    `tasks.md`，使旧 CI 能验证本 packet；但两个 route decision 的原始 issue evidence
    不可从 tracked checkout 独立恢复。该 direct transition 没有经过 B-008 的
    `spec_pr_open → spec_review → spec_approved` 正常链；聊天中的 auto 授权只能作为本次
    exception 的 reported 来源。tracked checkout 缺少 invocation id、route、精确
    `waived_human_gates`、可判定的 exact `implx auto` trigger 与独立 runtime trust anchor，
    因而不得断言历史 waiver 已成立，也不能把未发生的中间状态或不可恢复的 route evidence
    变成已证明事实。
    `bootstrap-evidence.json` 必须逐项区分 observed、reported 与 unproven：原 issue evidence
    的 `collected_at` 和内容 hash 若不能从 tracked checkout 恢复，就必须显式记为
    `unproven`，不得从 label timeline、duplicate timestamp 或文件名推断。
17. B-017 B-016 只审计 GH-180 本次 lifecycle-contract 迁移，不是正常 route success、
    当前实现授权或其它 issue 的先例。tracked evidence 缺失、字段标为 `unproven`、采集失败、
    权限不足、issue/head/packet 不匹配，均不得被宽泛授权补齐或复用。新 validator 落地后，
    在途 `ready_to_spec` packet 必须使用 B-012 的 staged 纠偏路径，不能继续提前创建 tasks；
    所有 spec-first packet 都必须遵守 B-008；合法 direct/mixed 入口按 B-021 判定。
18. B-018 每次 packet 判定必须给出可审计结果，至少能区分 linked issue、artifact
    shape、发现的 artifact、各 artifact 校验结果、readiness 是否被证明、evidence
    来源与阻断原因；使用 bootstrap 或纠偏路径时还必须标明对应依据。
19. B-019 若校验、spec 写作或 task planning 被取消/中断，已落下的部分文件只能按
    当前真实 shape 重新校验；半写文件、临时成功状态与未完成 transition 不得被
    提升为 `staged`、`complete` 或 implementation-ready。
20. B-020 通用 artifact role classifier 只能从 repo-owned workflow templates 派生
    `product_spec | tech_spec | task_plan | invalid`，不得认识
    `bootstrap-evidence.json`、`packet_evidence` 或其它 issue-specific role。仅 GH-180
    consumer overlay 可以把精确路径 `specs/GH180/bootstrap-evidence.json` 判为
    `gh180_bootstrap_audit`，且必须同时验证 `version: 2`、`issue: 180`、顶层、
    `observed` 与 `evidence_verdict` 三处 `authorization_effect: none`，以及
    `evidence_verdict.status: partial_unproven`。该
    overlay 只允许本 spec PR 的 exact changed-path equality 纳入审计；任何复制、改名、错误
    issue/path/content 都必须失败，且它永不产生 readiness、approval、waiver 或可复用授权。
21. B-021 实现入口必须由可信 evidence 确定性分类为闭集
    `implementation_entry_kind: spec_first | direct_bug | mixed_impl`，不得由 caller、PR body
    或 manifest 自报。`spec_first` 必须有从 `ready_to_spec` 开始的有序 lifecycle 与 exact-head
    spec PR；`direct_bug` 必须没有 spec packet，并满足 `SPEC.md` 已有 accepted-small-bug
    evidence 与可信 `triaged → ready_to_implement`；standard/fastlane 的 `mixed_impl` 必须由
    queue-derived tier 与同一 PR 的 mixed relation 证明，不要求先有独立 spec-only PR，也不得
    声称 `approved_spec_pr_exemption`。三者继续分别执行其现有 duplicate、readiness、
    approval/final-review gates；证据缺失、冲突或同时匹配多类时 fail closed。
22. B-022 `sensitive` 不得由 open spec PR approval 单独授权 production implementation。
    spec-first sensitive 工作可用 exact-head open PR 建立 lifecycle/order，但还必须等待该精确
    revision merge 到 trusted default base，并重新采集 existing sensitive `approved_spec`
    evidence，验证 `merged_at`、`merge_commit_sha` 与 ancestry 后才能进入生产实现。
    direct/mixed sensitive 路径同样保留 existing sensitive evaluator；无法产生 merged-base
    evidence 时必须 `blocked`/`needs_human`，不得以 open PR、auto waiver 或 route 类型绕过。

## 验收标准

- [ ] 有效 product/tech-only packet 被报告为 `staged` 并通过全量结构校验；补上
  有效 tasks 后被报告为 `complete`，两者均不会仅凭文件形态获得实现资格。
- [ ] 缺 product、缺 tech、无效 tasks、tasks-only 与空/不可读 artifact 均有
  稳定负例，且不得通过降级成 `staged` 掩盖错误。
- [ ] `write_spec` 在 `ready_to_spec` 只形成 product/tech；`implement` 在 review 路径凭
   same-repository spec PR 的 immutable exact-head maintainer approval 与 ordered human
   lifecycle 入场，且必须满足 exact-head `APPROVED submittedAt < spec_approved event <
   ready_to_implement event`；所接受 readiness actor 必须独立满足 maintainer permission
   policy。duplicate gate 只排除 exact approved spec-only PR/branch，其 `spec_refs` 必须先
   通过 repo-owned closed artifact-role allowlist 分类并与 implementation `paths` disjoint；
   caller/manifest 不能把实现文件声明成 spec ref，任何 identity/head/path/query 漂移仍阻断；
   在明确的
  auto invocation 中凭 runtime-owned grant registry 中的 active `spec_approval` waiver 入场，
  caller record 仅作 selector。selector、grant、response、stable binding 与 saved result 均绑定
  immutable repository id。两者都仍须 fresh trusted readiness、fresh duplicate-work evidence
  与有效 product/tech；staged result 只授予 `task_planning`，创建并验证 tasks 后须用
  `production_implementation` scope 重新验证，最后才允许代码实现。
- [ ] Host integration 明确区分 runtime provider/verifier owner 与 SpecRail client owner：
  runtime owner 部署 authenticated local IPC、current-generation 与 authorization-grant
  registry、Ed25519 signer/private key、OS/runtime-owned trust store，以及 guaranteed
  portable RFC8785-JCS/Ed25519 verifier；SpecRail client owner 实现 adapter、闭合 schema、
  route binding、fail-closed 与测试，不在 fresh checkout 假设未声明的 Python crypto/JCS
  dependency。provider、grant registry 或 verifier 未部署时 auto 不可用，但正常
  human-lifecycle review route 保持可用。
- [ ] readiness/lifecycle/auto-waiver 缺失或冲突、readiness event 不晚于 approval、spec PR
  非同仓、approval 不绑定 exact head、exact-head review 不早于 `spec_approved`、先打 label
  后补 review、超出 freshness 窗口、未来时间、错误 issue、body hint、
  CLI `--state`/readiness `--label` 自报，以及 artifact/duplicate-work 并发漂移或 caller
  record/saved result 自报 invocation/grant、旧 selector/anchor/result 重放均不能产生
  implementation-ready 结论；fresh evidence 的完整 envelope hash 用于审计，排除且只排除
  `collected_at` 的 semantic snapshot 用于跨采集比较，freshness 单独校验；approval 使用
  product/tech `spec_snapshot_sha256`，saved result 使用完整 `packet_snapshot_sha256`。
  runtime signing key 可在两次 challenge 间合法 rotation：stable binding 排除 `key_id`，但
  每份 response 仍由 portable verifier 独立校验其 active/non-revoked key。
- [ ] 既有完整 packet 保持兼容；提前生成 tasks 的 `ready_to_spec` 在途 PR 可以在
  可信 route evidence 下删除 tasks 并恢复为 `staged`。
- [ ] GH-180 bootstrap 的 tracked evidence 诚实记录 observed direct label transition、
  reported route decisions 与无法恢复的 issue-evidence `collected_at`/hash=`unproven`；
  历史 auto/waiver 也只能标为 `reported_unproven`，不得写成已证明 invocation-scoped waiver；
  它不声称完成 B-008 正常链，不充当当前 route authorization，且不能跨 issue 复用。
- [ ] 通用 classifier 不包含 bootstrap/packet-evidence role；仅 GH-180 exact-path +
  exact-content overlay 可识别 `gh180_bootstrap_audit`，复制到其它 issue 或修改
  authorization/status 字段都 fail closed，且 overlay 只参与本 PR path equality。
- [ ] route gate 确定性区分 `spec_first | direct_bug | mixed_impl`：spec-first 执行 staged
  lifecycle；accepted small bug 的 direct route 与 standard/fastlane 单 PR mixed route 保持
  可用且不伪造独立 spec PR，任何歧义 fail closed。
- [ ] sensitive spec-first 只有在 exact approved revision merge 到 trusted default base 且
  existing `approved_spec` merged-base/ancestry gate 通过后才能生产实现；direct/mixed
  sensitive 也不能绕过该 evaluator。
- [ ] 同一输入重复校验结果稳定，失败重试、取消和中断不会复用旧授权或产生部分成功。
- [ ] validator、route 与审计输出对同一 packet 的 shape、readiness 和阻断原因一致。
- [ ] shared runtime mapping 把 `needs_tasks` 精确映射到 `ready_to_implement`；runtime
      checkpoint/lifecycle audit 不得把 task planning 记录为 `spec_approved` 阶段状态。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004, B-005, B-009（缺 tasks 是合法 staged；缺 product/tech、空文件或缺 evidence 分别 fail closed） |
| 错误与失败路径 | covered: B-004, B-005, B-013, B-017, B-019（无效 artifact、采集/权限失败、部分写入均不可伪装成功） |
| 授权/权限 | covered: B-003, B-007..B-009, B-016, B-017, B-020..B-022（shape/readiness/bootstrap overlay 不单独授权；spec-first review 验证同仓 spec PR exact-head 人类 approval、readiness actor authority 与后续 event；auto 只接受 repository-bound runtime-owned registry grant；direct/mixed 保留既有 gates；sensitive 追加 merged-base gate） |
| 并发/竞态 | covered: B-008, B-014, B-021, B-022（artifact、repository identity、issue、route kind、lifecycle/grant、spec PR exact head/path/merge ancestry、runtime current generation 或 duplicate-work semantic snapshot 漂移后必须重判） |
| 重试/幂等 | covered: B-015, B-019（同输入同结论；失败或中断后全量重验，不复用旧片段） |
| 非法状态转换 | covered: B-006..B-008, B-012, B-013, B-021, B-022（spec-first staged lifecycle 与 direct/mixed 合法入口分离；禁止靠文件、open sensitive approval 或 staged allowed decision 跳状态） |
| 兼容/迁移 | covered: B-011, B-012, B-016, B-017, B-020..B-022（旧完整 packet、direct/mixed routes、sensitive merged-base enforcement 与 GH-180-only bootstrap overlay 均保持窄化合同） |
| 降级/回退 | covered: B-005, B-010, B-013, B-017（结构可验证不等于授权；错误 tasks/evidence 不得静默回退成功） |
| 证据与审计完整性 | covered: B-008..B-010, B-014..B-018, B-020..B-022（fresh envelope 与 semantic snapshot、spec/packet snapshot、route kind、sensitive merge ancestry、GH180-only audit overlay 与授权分离均可追溯） |
| 取消/中断 | covered: B-019（只认中断后的真实文件与状态，部分完成不升级） |

## 发布说明

这是 staged packet lifecycle 的兼容性迁移。升级后，product/tech-only packet 是
合法的 spec 阶段形态；既有三文件 packet 保持有效，但 artifact 齐全不再暗示
implementation readiness。GH-180 的一次性旧-validator bootstrap 被诚实记录为 direct
`ready_to_spec → ready_to_implement` auto exception，且缺失的原 issue-evidence
`collected_at`/hash 明确为 `unproven`；历史 auto/waiver 仅为 `reported_unproven`，因为缺少
current-invocation trust anchor 与 runtime-owned grant，不能证明当次 `spec_approval` waiver 成立，
更不是正常生命周期、standing authorization 或其它 gate 的 waiver。其它在途 spec PR 必须使用
staged 纠偏，不能通过提前创建 tasks、伪造 readiness 或跳过校验完成迁移。迁移只约束
spec-first 工作：既有 accepted-small-bug direct route 和 standard/fastlane 单 PR mixed route
继续按可信 route 分类与原 gates 运行；sensitive 路径继续要求 approved revision 落入 trusted
default base，open PR approval 不能替代 merged-base evidence。
