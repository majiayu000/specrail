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
- 提供确定性 CLI、闭集迁移记录与外部 role-mapped 授权 schema，把旧 artifact 转换为
  v2 可消费的派生证据，并绑定迁移前 Git commit/blob、source/派生摘要、目标 policy 与
  exact 人工决定。
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
   必须提供 exact legacy identity evidence；凡 repo/PR/artifact/head 命中该 evidence 的
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
11. B-011 迁移 CLI 默认 dry-run，只输出完整候选计划与 source/derived/policy digests；
    WHEN 未收到显式 `--apply` THEN 不得写任何文件。apply 必须消费一次性 closed
    `migration_authorization` 与显式 maintainer role map：授权精确绑定 repo immutable ID、
    PR、fresh base/head、source path + pre-migration commit/blob/digest、derived path/digest、
    target policy digest、`decision: migrate_legacy_round1_once`、actor/source/time。
    CLI 字符串、自报角色、auto/merge/cap 授权均不能替代或代填。
12. B-012 WHEN 回滚 THEN 删除派生 artifact、迁移记录与 manifest `migrations[]`
    条目即可回到迁移前的 fail-closed 状态；原始 artifact 不受影响，重复执行
    迁移对相同输入与同一授权必须产出逐字节相同的派生结果与记录内容；同一
    authorization ID 只能标识这一组 exact bytes，response-loss retry 或 rollback 后的
    exact reapply 可复用，跨 PR/base/head/artifact/source/derived scope 或不同 bytes
    复用必须 block。

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
- [ ] round >= 2 或字段已合规的 artifact 请求迁移被拒；新产出的 round-1 bounded
  artifact 带非 null base/diff 在 `review_json_gate.py` 即 block（B-001/B-010）。
- [ ] CLI dry-run 不落盘；apply 缺授权/role map、错 actor role、错 repo/PR/head/
  commit/blob/source/derived digest、重复 authorization ID 均拒绝；exact 授权幂等
  （B-011/B-012）。
- [ ] `python3 -m pytest -q`、`python3 checks/check_workflow.py --repo .
  --all-specs`、`python3 tools/spec_depth_audit.py --spec-dir specs/GH197 --gate`
  全绿。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002 B-003 B-006（source/记录/manifest 条目缺失均 block） |
| 错误与失败路径 | covered: B-004 B-005 B-008（重放不一致、声明不符、未迁移均给出定位错误） |
| 授权/权限 | covered: B-011（外部 role-mapped exact authorization；auto/CLI 字符串不得代授权） |
| 并发/竞态 | covered: B-002 B-004（验证按只读摘要比对，检查中源文件变化即失配 block） |
| 重试/幂等 | covered: B-012（重复迁移逐字节确定；重复验证结论一致） |
| 非法状态转换 | covered: B-001 B-010（round>=2 或新 artifact 走迁移通道非法） |
| 兼容/迁移 | covered: B-006 B-009 B-012（迁移显式声明；迁移后按 v2 正常评估；可回滚） |
| 降级/回退 | covered: B-008 B-012（无迁移证据时保持 fail-closed，无 warning 放行） |
| 证据与审计完整性 | covered: B-002 B-003 B-004 B-007（原字节保留、闭集记录、摘要绑定、防复用） |
| 取消/中断 | covered: B-011 B-012（dry-run 无副作用；apply 中断后重放可判定、可回滚） |

## 发布说明

存量 round-1 review artifact 可通过一次性、role-mapped 人工授权的确定性迁移进入
bounded v2 manifest；原始证据由迁移前 Git blob 锚定并永久保留，迁移记录、派生 marker
与 trusted legacy identity 共同绑定，未迁移、手工复制或被篡改的形态继续 fail closed。
