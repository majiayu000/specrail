# Product Spec

## Linked Issue

GH-167

## 用户问题

独立审查已有 lane 复用规则，但缺少跨 `full`、`resumed`、`diff_only` 的可信总轮数上限。当前轮数由单个 artifact 自报，调用者可以反复写同一 `review_round`；`review_json_gate.py` 只看到一份 artifact 与一份 diff，也无法证明同一 PR 的轮次连续，或传入 diff 确实是上一审查 head 到当前 head 的增量。与此同时，`prior_findings[]` 仍携带摘要正文，历史 finding 会被逐轮回放，成本随轮次增长且容易让未闭合 finding 静默消失。

本规格以 manifest artifact 集合为轮次真相：默认最多 3 轮；第 2 轮起只审查上轮未闭合 finding 的证据与可信增量 diff；超限必须取得一次、仅绑定目标 PR/head/round 的 maintainer 裁决。单 artifact 不再自行证明轮数、授权或 diff 来源。

## 目标

- 从 review manifest 的 artifact 集合派生连续、唯一、单调的跨模式轮次，默认总上限固定为 3。
- 第 2 轮起强制 `resumed` 或 `diff_only`，且证明输入 diff 精确等于 `base_head_sha..head_sha`。
- 用带来源绑定的紧凑状态表替代历史 finding 正文回放，并保留“finding 不许口头消失”。
- 超限时要求独立于 reviewer artifact 的 maintainer 授权；授权只允许一个精确目标轮次，不能复用为无限逃生阀。
- 由 PR 终审合同复核 manifest v2 的轮次、模式、diff provenance、carry-forward 与升级移交记录。
- 让 review skill、权威 queue skill 与 threads 集成文档使用同一轮数/升级合同，并用确定性测试阻止文档回漂。

## 非目标

- 不改变 `auth_mode: auto`/`review` 的合并授权语义；轮次超限授权与合并授权是两个独立证据。
- 不改变 reviewer-lane 的线程解决归属、CI gate、issue closing 语义或安全披露边界。
- 不移除 GH-61 的 lane 复用要求；GH-61 控制单轮上下文，本规格控制轮数、范围和 carry-forward。
- 不允许仓库自行调高默认上限；上限固定为 3，歧义 fail-closed。
- 不把 `human_full_review_request` 升格为轮次超限授权。

## Behavior Invariants

1. B-001 WHEN manifest 包含多份独立审查 artifact THEN loader 必须从 artifact 集合验证 `review_round` 恰为 `1..N`、每轮唯一且无缺口/回退；轮数不能由终审调用者单独声明或重复同一数字绕过。
2. B-002 WHEN 派生轮数 `N > 3` THEN 第 `N` 轮必须引用一份外部 `round_cap_authorization`；该授权必须由显式 maintainer role map 证明，并精确绑定 `pr`、上一轮 `head_sha`、本轮 `head_sha`、`review_round`、`authorization_id` 与 `decision: continue_once`。
3. B-003 同一个 `authorization_id` 只能满足一个精确轮次；复制到其它 round/head/PR 必须 block。`human_full_review_request`、artifact 内自报的 `actor/source` 或本次 implx auto 合并授权均不能替代该证据。
4. B-004 WHEN `review_round >= 2` THEN `review_mode` 必须为 `resumed` 或 `diff_only`；`full` 模式必须 block，即使携带 `human_full_review_request`。
5. B-005 WHEN mode 为 `resumed` 或 `diff_only` THEN 必须存在 `base_head_sha` 和 `diff_sha256`，且 `base_head_sha` 必须等于上一轮 artifact 的 `head_sha`；gate 必须验证传入 diff 字节精确等于 Git 的 `base_head_sha..head_sha` 结果并匹配 hash。
6. B-006 新策略的 `prior_findings[]` 每条必须是闭集紧凑结构 `{finding_id, source_artifact_id, status, evidence_pointer}`；不得携带 `summary`、`body`、`full_text` 或历史 artifact 正文。
7. B-007 `evidence_pointer` 必须是闭集结构 `{kind, value}`，其中 `kind ∈ {thread, comment, artifact, commit}`，`value` 必须匹配对应稳定 ID/40 位 commit SHA；`"fixed it"` 等自由散文必须 block。
8. B-008 finding 身份由 `(source_artifact_id, finding_id)` 唯一确定；manifest 内重复键、引用不存在的来源 artifact，或不同 lane/head 对同一键给出冲突定义必须 block。
9. B-009 当前轮必须 carry manifest 中所有仍未闭合的历史 finding；缺失、重复、无来源或无证据的条目必须 block，已 `resolved`/`obsolete` 的关闭状态必须有具体 evidence pointer。
10. B-010 超限轮的 `round_cap_escalation.unresolved_findings[]` 必须精确覆盖“历史 `unresolved` finding + 当前轮 `findings[]` 中 critical/important/actionable finding”的并集；漏项或额外伪造项均 block。
11. B-011 manifest v2 是 bounded-round 策略的 feature discriminator，必须持久化每轮 artifact id、round、mode、base/head、diff hash 与 escalation reference。v2 声明字段缺失或与加载后的 artifact 不一致必须 block。
12. B-012 manifest v1 仅在单 artifact、未声明 bounded-round 新字段时保持原行为；v1 多 artifact 或任一 artifact 声明新轮次策略字段时必须给出迁移错误并 block，不能静默按旧路径放行。
13. B-013 PR evidence 必须通过闭集 schema 携带 loader 派生的 `round_audit` 与可选 `round_cap_authorizations[]`；`pr_review_contract.py` 必须从仓库安全路径重新加载 manifest 并逐字段复核，不能信任嵌入副本。
14. B-014 新的跨 artifact/round/carry 语义应落在共享 `checks/review_result_semantics.py`；`checks/review_json_gate.py` 保持 CLI/diff 定位职责，修改后两文件均不得超过 800 行。
15. B-015 `skills/specrail-review-pr/SKILL.md`、`skills/specrail-implement-queue/SKILL.md`、`skills/implx/SKILL.md` 与 `integrations/threads.md` 必须引用同一 bounded-round 合同；不得残留“full 最多 2 轮后由人工无限追加 full pass”等冲突路径，确定性测试必须在任一权威文档回漂时失败。

## Acceptance Criteria

- [ ] manifest v2 对轮次重复、缺口、回退、round>=2 full、两种 scoped mode 缺 `base_head_sha` 的输入 fail-closed；连续 `1..N` 输入通过（B-001/B-004/B-005/B-011）。
- [ ] 第 4 轮无授权、伪造 artifact 内授权、错误 role map、跨 PR/head/round 复用授权均被拒；正确的 `continue_once` maintainer 授权只满足其绑定轮次（B-002/B-003）。
- [ ] gate 拒绝全 PR diff 或伪造 hash，仅接受 Git 精确生成的 `base_head_sha..head_sha` 字节（B-005）。
- [ ] 紧凑 carry-forward 拒绝正文回放、自由散文 pointer、未知来源、重复键与漏掉历史 unresolved finding；超限移交还必须包含当前 actionable finding（B-006..B-010）。
- [ ] manifest v1 单 artifact fixtures 零改动通过；v1 多 artifact 与 v2 字段不完整被明确拒绝（B-011/B-012）。
- [ ] PR evidence schema/adapter/contract 完整复核 `round_audit` 和超限授权；`python3 checks/check_workflow.py --repo . --all-specs`、全量 `pytest` 通过，相关文件小于 800 行（B-013/B-014）。
- [ ] review/queue/threads 四处权威合同统一为 cap=3、round>=2 scoped、超限 exact `continue_once`，并有文档一致性测试（B-015）。

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 B-005 B-011（轮次、base、diff、v2 审计字段缺失均 block） |
| Error / failure paths | covered: B-002 B-003 B-010（无授权、授权错绑、移交集合不完整均给出定位错误） |
| Authorization / permission | covered: B-002 B-003（maintainer role map + exact scope；与合并授权隔离） |
| Concurrency / race | covered: B-001 B-003（manifest 集合一次性只读评估；授权 ID 与精确 round/head 绑定，重复消费可确定检测） |
| Retry / idempotency | covered: B-001 B-003（相同 manifest/授权重复评估结果一致；新轮次需新 exact-bound 授权） |
| Illegal state transitions | covered: B-001 B-004（轮次缺口/回退、round>=2 full 均非法） |
| Compatibility / migration | covered: B-011 B-012（v2 显式启用；v1 单轮兼容；v1 多轮显式迁移错误） |
| Degradation / fallback | covered: B-005 B-012（无法证明 diff 或策略版本时 block，无 warning+fallback） |
| Evidence / audit integrity | covered: B-005 B-007 B-008 B-013（Git diff、typed pointer、来源键、trusted manifest 重载） |
| Cancellation / interruption | covered: B-002 B-010（达到 cap 自动停止并把完整未闭合集合交给人工；无授权不继续） |

## Rollout Notes

先落 shared semantics、manifest v2 与 schema，再接 PR evidence/contract，最后更新两个 review skill 和 reviewer 文档。部署后，既有 v1 单轮证据继续通过；首次进入第 2 轮时必须生成 v2 manifest 与可信 scoped diff。达到第 4 轮时自动流程停止，只有新增、精确绑定该轮的 maintainer 授权才能继续一次；auto 模式不自动生成此授权。
