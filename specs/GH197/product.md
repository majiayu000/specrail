# Product Spec

## Linked Issue

GH-197

## 用户问题

GH-167 引入的 bounded review manifest v2 要求 round 1 派生的 `base_head_sha` 与
`diff_sha256` 均为 null（artifact 可缺失对应可选字段），并从实际 artifact 集合派生
连续 `1..N` 轮次。真实队列中的
PR #181、#186、#193 已持久化 round-1 artifact：这些 artifact 携带
`round_policy_version: 1`，但至少一个 bounded 字段为非 null（#181/#193 的
`base_head_sha` 与 `diff_sha256` 非 null，#186 的 `diff_sha256` 非 null）。后续
round-2 artifact 本身可通过单 artifact gate，却无法构造能通过
`validate_bounded_rounds()` 的可信 v2 manifest；v1 路径又因 artifact 声明了新策略
字段而显式拒绝。于是内容、CI、线程全绿后 `pr_gate` 仍 fail closed，队列被永久卡住。

直接修改旧 artifact 会破坏不可变审查证据；复制后手工删字段则没有版本化 provenance、
摘要绑定或迁移授权，无法与任意篡改区分。本规格定义一个 fail-closed、可审计、
不可伪造的一次性迁移合同：原 artifact 字节与摘要永久保留，迁移只产出确定性派生
artifact 与绑定 source digest 的迁移记录，任何超出白名单的差异必须 block。

## 目标

- 定义 `legacy_round1_normalization_v1` 迁移合同：仅覆盖 round-1、
  `round_policy_version: 1`、至少一个 bounded 字段非 null 的存量 artifact。
- 提供确定性 CLI、闭集迁移记录与 fresh-provider 授权 schema，把旧 artifact 转换为
  v2 可消费的派生证据，并绑定迁移前 Git commit/blob、source/派生摘要、目标 policy 与
  exact 人工决定。
- 授权与 PR identity 必须来自调用方不可伪造的 fresh provider；本地 JSON、CLI
  字符串或自报 role map 只能作为待校验输入，不能成为授权信任根。
- 白名单只允许把 round-1 的 `base_head_sha` 规范化为 null，并删除
  `diff_sha256`；finding、
  head、时间戳、verdict、content binding 等其余字段永久禁止改动。
- 验证方从原始字节确定性重放派生结果；重放摘要不一致即视为伪造并 block。
- `review_result_semantics.py`、`review_json_gate.py`、`pr_gate.py` 对迁移前后给出
  稳定、可定位的 decision/rejection_items：迁移前明确指向迁移合同，迁移后按正常
  v2 语义评估，不误放行也不误卡。
- 用 PR #181/#186/#193 的真实形态构造正反测试，并明确回滚与兼容策略。

## 非目标

- 不改写、移动或删除任何既有 review artifact 的原始字节。
- 不用 `implx auto` 合并授权替代迁移证据；auto 流程不得自动执行迁移写入。
- 不绕过 round cap、exact-head、独立 reviewer、CI、reviewThreads 或 PR gate 的
  任何既有语义。
- 不为 round >= 2 artifact、非 bounded artifact 或未来新产生的不合规 artifact
  提供迁移通道；新 artifact 必须在产出时即满足 v2 合同。
- 不调整 `bounded_diff_v1` 的 cap、round 派生或 escalation 语义。

## Behavior Invariants

1. B-001 WHEN 迁移候选 artifact 满足 `round_policy_version: 1`、`review_round: 1`
   且 `base_head_sha` 或 `diff_sha256` 至少一个非 null THEN 迁移工具才可受理；
   任何其他形态（round >= 2、非 bounded、字段已全 null、未来新 artifact）必须
   拒绝并给出定位错误，不存在兜底通道。
2. B-002 WHEN 迁移执行 THEN 原始 artifact 文件字节必须保持不变；迁移只能新增
   派生 artifact 与迁移记录两个文件。`source_sha256` 必须由受保护 adapter 绑定到迁移前
   已存在且可达的 exact Git commit/path/blob bytes；当前 source、Git blob 或授权摘要任一
   不一致必须 block，同一提交内自报或重算的摘要不能充当独立锚点。
3. B-003 迁移记录必须是闭集结构，至少绑定：`migration_version: 1`、
   `source_artifact_path`、`source_sha256`、`derived_artifact_path`、
   `derived_sha256`、目标 `{manifest_version: 2, round_policy: {name:
   "bounded_diff_v1", cap: 3}}`、逐字段 `normalizations[]`（含原值）、闭集
   `reason`、`authorization_id` 与 `migrated_at`；迁移前 Git commit/blob identity 及
   exact authorization 的 cross-binding 缺失、额外或不一致必须 block。
4. B-004 WHEN 验证迁移 THEN 必须从原始字节按白名单确定性重放派生结果，并要求
   重放摘要与 `derived_sha256`、派生文件实际摘要三者一致；任何白名单之外的
   字段增删改（含 findings、head_sha、时间、verdict、prior_findings、
   content binding、artifact_id）都会导致重放不一致并 block。
5. B-005 `normalizations[]` 每项只允许
   `{field: base_head_sha, operation: set_null}` 或
   `{field: diff_sha256, operation: delete}`，并记录 non-null 原值；WHEN 源字段本就是
   null/缺失却声明 normalization，或非 null 字段未声明对应 operation THEN 必须 block。
6. B-006 WHEN manifest v2 引用派生 artifact THEN manifest 必须在闭集
   `migrations[]` 中为该 artifact 声明恰好一条 `{artifact_id, record_path}`；
   派生 artifact 自身也必须携带 closed `migration_provenance` marker。受保护 adapter
   必须从 target base 的固定 conventional path 加载 closed repo legacy registry；
   registry 以 exact cutoff、expected identity list/count/digest 和 PR #181/#186/#193
   source Git object entries 自证 allowlist 完整性，调用方不得指定 path、过滤 entries
   或缩小 coverage。凡 repo/PR/artifact/head 命中该 registry-derived evidence 的
   round-1 artifact，即使换路径、手工复制或省略 marker/migrations 条目，也必须 block。
   记录缺失、重复、未知 artifact_id、marker/record/evidence 不一致均必须 block。
7. B-007 一条迁移记录只能绑定一个 source/derived 对；WHEN 同一记录被复用到其它
   artifact、其它 PR 或其它 manifest 声明的路径 THEN 摘要与路径绑定必须使其
   失败，不得作为通用豁免。
8. B-008 WHEN legacy round-1 artifact 未迁移即被 v2 manifest 直接引用 THEN
   `load_review_manifest()` 必须维持 fail-closed，且 rejection item 必须稳定
   指向迁移合同（明确 category 与候选 artifact），不得退化为泛化的轮次错误。
9. B-009 WHEN 迁移完成且记录验证通过 THEN 同一 manifest 在
   `review_result_semantics.py`、`pr_review_contract.py`、`pr_gate.py` 下必须
   按正常 v2 语义评估；相同输入必须产生相同 decision/rejection_items，迁移
   不得改变 round 派生、carry-forward 或 escalation 结论。
10. B-010 WHEN 新的 round-1 bounded artifact 在单 artifact gate
    （`review_json_gate.py`）声明非 null `base_head_sha` 或 `diff_sha256` THEN
    必须在产出时即 block，防止继续铸造需要迁移的 legacy 形态；该规则不追溯
    已持久化的存量文件。
11. B-011 迁移 CLI 默认 dry-run，只输出完整候选计划、source/policy/request digests
    与确定性目标路径；
    WHEN 未收到显式 `--apply` THEN 不得写任何文件。apply 必须消费一次性 closed
    `migration_authorization`：dry-run 先产生只含发布前稳定输入的 closed
    `authorization_request`，人工发布后受保护 provider 再产生绑定 comment
    identity/body、actor/permission/time 的 closed `provider_attestation`；两者摘要共同
    确定 `authorization_id`。request 精确绑定 repo immutable ID、PR、fresh base/head、
    source path + pre-migration commit/blob/digest、确定性 derived/record path、target
    policy 与 normalization plan，但不得包含 comment 元数据、authorization ID、
    `derived_sha256` 或 `record_sha256`。apply 后的 record 是 receipt，才绑定最终
    derived digest；record digest 由 verifier 对最终 record bytes 外部重算，不得被
    request、attestation 或 record 自身预签。record 的 `migrated_at` 必须等于
    `authorized_at`，canonical derived/record bytes 不得由 apply 时另选。
    CLI 字符串、本地 JSON/role map、自报角色、auto/merge/cap 授权均不能替代或代填。
12. B-012 WHEN 回滚 THEN 删除派生 artifact、迁移记录与 manifest `migrations[]`
    条目即可回到迁移前的 fail-closed 状态；原始 artifact 不受影响，重复执行
    迁移对相同输入与同一授权必须产出逐字节相同的派生结果与记录内容；同一
    authorization ID 只能标识这一组 exact bytes，response-loss retry 或 rollback 后的
    exact reapply 可复用，跨 PR/base/head/artifact/source/derived scope 或不同 bytes
    复用必须 block。
13. B-013 WHEN 验证 `migration_authorization` THEN actor 身份、maintainer 权限、
    授权事件及其 request payload 必须由 fresh GitHub provider 查询并在查询前后保持
    一致；provider 必须在事件发布后独立形成 `provider_attestation`，不得要求事件
    payload 预先包含自身 node/URL/time、attestation digest 或任一下游产物 digest；
    调用方提供的 authorization JSON、role map、actor/source 字符串或其任意自洽组合
    不得单独建立授权，provider 缺失、不可用、权限不足、事件被编辑/删除或双读漂移
    必须 fail closed。
14. B-014 WHEN CLI 执行 dry-run THEN repo immutable ID、PR base/head 与 migration
    base 必须由受保护 provider/registry 取得并绑定到输出的
    `authorization_request`；request digest 与目标路径只能由这些稳定输入确定。
    dry-run 不得把缺少远端授权事件及 `provider_attestation` 的 request 宣称为完整
    authorization。provider 不可用或 identity 不完整时不得输出可用于 apply 的候选。
15. B-015 `migration_base_sha` 必须进入 migration record 与 authorization 的闭集
    shape，并与 trusted registry cutoff、provider snapshot、cross-binding 和 replay
    比较完全一致；只存在于 CLI 参数、缺失、额外或任一处不一致必须 block。
16. B-016 authorization、record、registry identity 与 provenance 必须分别携带
    `source_artifact_head_sha` 和 `authorized_pr_head_sha`；前者匹配 legacy round-1
    artifact，后者匹配 fresh 当前 PR head，两者不得由单一 `head_sha` 字段代替，
    且合法多轮流允许二者不同。
17. B-017 source Git commit 的 ancestry 必须相对 trusted
    `authorized_pr_head_sha` 验证；`migration_base_sha` 只用于 registry/cutoff
    identity，不得被误用为 source ancestry 目标。
18. B-018 WHEN 源 artifact 缺失 `base_head_sha` 或其值已为 null THEN 派生 artifact
    必须保持同一形态且不得声明 `set_null`；仅源字段存在且 non-null 时才允许
    `base_head_sha/set_null`。`diff_sha256/delete` 同理只适用于存在且 non-null 的源字段。
19. B-019 `authorization_id` 必须由 canonical `authorization_request` digest 与
    发布后 trusted `provider_attestation` digest 确定性派生并由 verifier 重算，不得由
    调用方任意选择；request、attestation、authorization ID、derived bytes、record
    receipt 的依赖必须严格单向，任一对象的 canonical digest 都不得包含自身 digest，
    上游也不得包含下游 digest。rollback 删除 derived/record 后，同一 ID 仍只能重建
    同一 exact scope/bytes；不同 scope/bytes 必须产生不同 ID，强行复用必须 block。
20. B-020 WHEN loader 遇到 registry 命中的 legacy artifact THEN 必须在通用
    round-1 origin 规则之前完成 trusted legacy classification：未迁移时只产生稳定
    `legacy_round1_migration_required` rejection；creation-mode 的新 artifact 仍由
    origin gate 拒绝。不得因验证顺序先产生泛化 schema/origin 错误而遮蔽迁移路径。

## 验收标准

- [ ] PR #181（base+diff 非 null）、#186（仅 diff 非 null）、#193（base+diff
  非 null）三种真实 round-1 形态各有 fixture：迁移前 manifest v2 被稳定拒绝且
  rejection 指向迁移合同；迁移后全链路通过（B-001/B-008/B-009）。
- [ ] 篡改派生 artifact 任一非白名单字段、伪造 `derived_sha256`、替换 source
  文件、source 与 pre-migration Git blob 不一致、复用迁移记录到其它 artifact 均被拒
  （B-002/B-004/B-007）。
- [ ] 迁移记录缺字段、多字段、`reason` 越界、normalization 声明与源值不符均被拒
  （B-003/B-005）。
- [ ] manifest `migrations[]` 缺条目、重复条目、指向未知 artifact、
  `migration_provenance` 缺失/伪造，以及命中 trusted legacy identity 后手工复制或改路径
  规避记录均被拒（B-006）。
- [ ] registry path 由 PR gate 固定、从 exact target base 加载；缺 registry、错 repo/
  cutoff、entries 与 expected identity list/count/digest 不一致、caller 传空/子集或改
  coverage scope 均 fail closed（B-006/B-009）。
- [ ] round >= 2 或字段已合规的 artifact 请求迁移被拒；新产出的 round-1 bounded
  artifact 带非 null base/diff 在 `review_json_gate.py` 即 block（B-001/B-010）。
- [ ] CLI dry-run 不落盘；authorization request 仅含发布前稳定 scope，GitHub comment
  不预含自身 node/URL/time 或 derived/record digest；apply 缺 fresh provider
  attestation、错 actor permission、错 repo/PR/head/
  commit/blob/source/derived/record path 或 digest、`migrated_at != authorized_at`、同 ID
  不同 bytes 均拒绝；request → attestation → authorization ID → derived → record
  receipt 可有限构造且 exact 授权幂等
  （B-011/B-012）。
- [ ] 本地 authorization/role-map 自证、伪造 actor/source、GitHub actor 无
  maintain/admin 权限、authorization comment 编辑/删除、provider 前后快照漂移均
  fail closed；dry-run 只输出 provider-bound `authorization_request`，不能直接 apply
  （B-013/B-014）。
- [ ] record/authorization 均持久化并重放 `migration_base_sha`，legacy artifact head
  与 fresh PR head 使用两个独立字段；source commit 只对 trusted current PR head
  做 ancestry 校验（B-015/B-016/B-017）。
- [ ] #186 形态保持缺失/null `base_head_sha`，不新增字段或虚构 normalization；
  authorization ID 从 request/attestation 两个 canonical digest 确定性派生，任何对象
  均不自哈希或反向绑定下游 digest，rollback 后跨 scope/bytes 复用仍拒绝
  （B-018/B-019）。
- [ ] registry 命中的未迁移 legacy artifact 在通用 origin gate 前分类，仅产生稳定
  `legacy_round1_migration_required`；creation-mode 新 artifact 仍被源头 gate 拒绝
  （B-020）。
- [ ] `python3 -m pytest -q`、`python3 checks/check_workflow.py --repo .
  --all-specs`、`python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate`
  全绿。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002 B-003 B-006 B-013 B-014 B-015（source/记录/provider/identity 缺失均 block） |
| 错误与失败路径 | covered: B-004 B-005 B-008 B-018 B-020（重放不一致、声明不符、未迁移均给出定位错误） |
| 授权/权限 | covered: B-011 B-013 B-014 B-019（fresh provider exact authorization；本地 JSON/role map 不自证） |
| 并发/竞态 | covered: B-002 B-004（验证按只读摘要比对，检查中源文件变化即失配 block） |
| 重试/幂等 | covered: B-012 B-019（重复迁移逐字节确定；ID 从 request + attestation 派生） |
| 非法状态转换 | covered: B-001 B-010 B-020（creation 与 legacy migration 路由不可混用） |
| 兼容/迁移 | covered: B-006 B-009 B-012 B-016 B-018 B-020（多轮 head 分离、缺失字段形态与迁移路由保持） |
| 降级/回退 | covered: B-008 B-012 B-013（无迁移或 provider 证据时保持 fail-closed） |
| 证据与审计完整性 | covered: B-002 B-003 B-004 B-007 B-015 B-016 B-017 B-019（完整 identity/ancestry/scope 绑定且无循环摘要） |
| 取消/中断 | covered: B-011 B-012 B-013（dry-run 无副作用；provider 双读与 apply 重试可判定） |

## 发布说明

存量 round-1 review artifact 可通过一次性、fresh-provider 人工授权的确定性迁移进入
bounded v2 manifest；原始证据由迁移前 Git blob 锚定并永久保留，迁移记录、派生 marker
与 trusted legacy identity 共同绑定；人工授权与当前 PR identity 来自 fresh GitHub
provider，未迁移、手工复制、本地自证授权或被篡改的形态继续 fail closed。
