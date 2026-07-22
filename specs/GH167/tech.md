# Tech Spec

## Linked Issue

GH-167

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":167,"complete":true,"paths":["checks/review_json_gate.py","checks/review_result_semantics.py","checks/pr_review_contract.py","checks/github_pr_evidence.py","checks/github_review_evidence.py","schemas/review_result.schema.json","schemas/pr_review_gate.schema.json","review/agent_first_review.md","skills/specrail-review-pr/SKILL.md","skills/implx/SKILL.md","tests/test_review_json_gate.py","tests/test_review_result_semantics.py","tests/test_pr_gate_terminal.py","tests/test_github_pr_evidence.py","tests/test_github_pr_evidence_cli.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH167/product.md","specs/GH167/tech.md","specs/GH167/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 单 artifact gate | `checks/review_json_gate.py:252` | CLI 只接收一个 `--review` 与 `--diff`；`_validate_review_round()` 信任 artifact 自报轮次，只有 `diff_only` 要求 base，无法看到 artifact 集合 | 只能校验当前 artifact 与可信 diff，不能派生总轮数或授权 |
| 共享 artifact/manifest 语义 | `checks/review_result_semantics.py:363` | 强制旧 `prior_findings` 结构，并由 `load_review_manifest()` 加载全部 lanes/artifacts、检查 carry-forward；manifest 只接受 `version == 1` | B-001/B-006/B-008/B-011 的正确强制点，原规划遗漏 |
| review result schema | `schemas/review_result.schema.json:120` | `additionalProperties: false`；旧 prior 条目为 `{id, source_head_sha, summary, status, closure_evidence}`，允许历史正文增长 | 需用 feature marker 区分旧 v1 单轮与新 bounded v2 形态 |
| PR evidence adapter | `checks/github_pr_evidence.py:568`, `checks/github_review_evidence.py:255` | 可加载 review manifest、human/self-review 与 resolver role map；没有 round-cap 授权输入或 maintainer role binding | 外部 maintainer 授权必须在这里构造，不能由 reviewer artifact 自报 |
| PR 终审合同 | `checks/pr_review_contract.py:282` | 从安全路径重载 manifest，并与闭集 `review_evidence` 字段比对；未复核 round audit/authorization | B-002/B-003/B-013 的最终 fail-closed 点 |
| PR evidence schema | `schemas/pr_review_gate.schema.json:354` | `review_evidence.additionalProperties: false`，没有 `round_audit` 或 `round_cap_authorizations` | 不扩 schema 会让新证据在入口被拒 |
| 文档与 skills | `review/agent_first_review.md`, `skills/specrail-review-pr/SKILL.md`, `skills/implx/SKILL.md` | 允许 full round 2、round>2 用 `human_full_review_request` 解锁；carry-forward 未限制体积 | 需同步停止条件、v2 输出与 maintainer escalation |

## Proposed Design

### 1. Manifest v2 作为轮次真相

`load_review_manifest()` 同时接受两条明确路径：

- v1：仅允许一个 artifact，且 artifact 不含 `round_policy_version`、`diff_sha256`、`round_cap_escalation`。保持现有单轮输出与 gate 行为。
- v2：manifest 必须声明 `version: 2` 与 `round_policy: {name: "bounded_diff_v1", cap: 3}`，并持久化 `rounds[]`。每项闭集为 `{artifact_id, review_round, review_mode, base_head_sha, head_sha, diff_sha256, escalation_authorization_id}`；round 1 的 base/diff/escalation 字段为 null，round>=2 的 base/diff 必填，未超 cap 的 escalation 为 null。

loader 从实际加载的 artifacts 派生并逐项复核 `rounds[]`：

- `review_round` 必须恰为 `1..N`，唯一、连续，无重复/缺口/回退；artifact id 与 head 也必须唯一。
- round 1 可保留既有 mode；round>=2 只能是 `resumed`/`diff_only`，且 base 必须等于上一轮 head。
- v1 多 artifact、v2 缺字段、manifest 声明与 artifact 不一致一律 block。
- 返回的 trusted `review_evidence.round_audit` 由 loader 生成，含 `policy`、`cap`、`total_rounds`、`rounds`，而不是复制调用者输入。

### 2. 紧凑、带来源的 finding

`schemas/review_result.schema.json` 增加可选 `round_policy_version: 1` 作为 artifact 侧 feature marker。启用后 `prior_findings[]` 每项闭集为：

```json
{
  "finding_id": "F-12",
  "source_artifact_id": "pr-167-round-1",
  "status": "resolved",
  "evidence_pointer": {"kind": "thread", "value": "PRRT_..."}
}
```

`evidence_pointer.kind` 为 `thread|comment|artifact|commit`；value 分别校验 `PRRT_`、`PRRC_`、manifest 内 artifact id、40 位十六进制 SHA。finding 键为 `(source_artifact_id, finding_id)`。`review_result_semantics.py` 复核来源存在、键唯一、状态闭集、pointer 格式，以及当前轮完整 carry 所有历史 unresolved。旧 v1 单轮的空 `prior_findings` 不变；旧非空形态不会被误当作 v2。

### 3. 精确 diff provenance

round>=2 artifact 必须含 `base_head_sha` 与 `diff_sha256`。`review_json_gate.py` 对 bounded artifact：

1. 以参数数组执行 `git diff --no-ext-diff --binary <base_head_sha>..<head_sha> --`，禁止 shell 拼接；任一对象不存在或命令失败即 block。
2. 要求 `--diff` 文件原始字节与该命令 stdout 完全一致。
3. 要求 SHA-256 同时匹配 artifact `diff_sha256`。

`review_result_semantics.py` 再验证 manifest 中 round N 的 base 等于 round N-1 head。这样 full PR diff、伪造 hash、错误 base 都不能作为 scoped review 证据。

### 4. 超限授权与完整移交

round > 3 artifact 可携带 `round_cap_escalation`，但该对象只引用授权，不自证权限：

```json
{
  "authorization_id": "RCA-167-4",
  "unresolved_findings": [
    {"finding_id": "F-12", "source_artifact_id": "pr-167-round-1"}
  ]
}
```

协调器只有在收到该 cap event 的显式人工决定后，才向 `github_pr_evidence.py --round-cap-authorization <json> --maintainer-role-map <json>` 提供外部证据。adapter 输出的 `round_cap_authorizations[]` 每项闭集为 `{authorization_id, pr, prior_head_sha, target_head_sha, review_round, decision, actor, source, authorized_at, authorized_human_maintainer}`；`decision` 仅允许 `continue_once`，role map 不匹配则 adapter fail。auto 合并授权不填充此字段。

`pr_review_contract.py` 对每个 over-cap round 要求唯一授权，并精确匹配 PR、前后 head、round 和 id；一个 id 出现两次或被其它 round/head 引用即 block。artifact 内 `human_full_review_request`/actor/source 不参与判断。

`review_result_semantics.py` 计算升级移交的期望集合：所有历史 carry 中 status=`unresolved` 的键，加当前 artifact `findings[]` 中 severity 为 critical/important 或 actionable=true 的键（当前 finding 的 source 为当前 artifact id）。`unresolved_findings[]` 必须与期望集合完全相等，不得遗漏或多报。

### 5. PR evidence 与可信重载

- `schemas/pr_review_gate.schema.json` 为 `review_evidence` 增加闭集 `round_audit`，并在顶层增加闭集 `round_cap_authorizations[]`。
- `checks/github_review_evidence.py` 负责加载/校验授权文件和 maintainer role map；`checks/github_pr_evidence.py` 暴露 CLI 参数并只复制规范化结果。
- `checks/pr_review_contract.py::_manifest_trust_items()` 把 `round_audit` 加入 trusted manifest 比对；授权单独与 trusted round audit 匹配。
- `review_json_gate.py` 不接受 artifact-set 或自报授权；跨 artifact 规则只在 shared manifest semantics 与 PR contract 强制。

### 6. 文件规模与职责

当前 `checks/review_json_gate.py` 约 682 行，不再承载 artifact-set/carry/authorization算法。新增共享逻辑进入 `checks/review_result_semantics.py`，CLI gate 只增加 bounded diff 的薄适配。实现后用 `wc -l` 断言两文件均小于 800 行；若 shared semantics 接近上限，再在同一实现 PR 中拆出专用模块并同步 planned paths，不允许超过硬上限后再补救。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | manifest v2 loader 派生轮次 | 重复 round、缺口、回退、乱序均 block；连续 1..N 通过 |
| B-002/B-003 | adapter + PR contract 授权 | 无 role map、错 PR/head/round、重复 id、复用 id 均 block；exact `continue_once` 通过 |
| B-004 | shared semantics | round 2 full 即使有 `human_full_review_request` 仍 block；两种 scoped mode 通过 |
| B-005 | review JSON gate + manifest | resumed/diff_only 缺 base/hash、错误上一 head、全 PR diff、伪造 hash 均 block |
| B-006/B-007 | result schema + semantics | 正文/额外字段、自由散文 pointer、错误 kind/value block；typed pointer 通过 |
| B-008/B-009 | manifest carry | 未知 source、重复键、漏 carry、冲突定义 block |
| B-010 | escalation union | 漏历史 unresolved、漏当前 actionable、额外键均 block；精确并集通过 |
| B-011/B-012 | version routing | v2 audit 缺失/不一致 block；v1 单 artifact fixture 零改动通过；v1 多 artifact block |
| B-013 | PR evidence schema/contract | 嵌入 `round_audit` 篡改被 trusted reload 发现；闭集 schema 接受规范字段、拒绝未知字段 |
| B-014 | file-size gate | `wc -l checks/review_json_gate.py checks/review_result_semantics.py` 每项 `< 800` |

## Data Flow

reviewer 输出当前 artifact + 精确 scoped diff → `review_json_gate.py` 校验 artifact、Git range 与 hash → manifest v2 汇总全部 artifact → `load_review_manifest()` 从实际文件派生连续 round audit 与 carry/escalation 集合 → `github_pr_evidence.py` 加载独立 maintainer role map/round authorization → PR evidence 闭集 schema → `pr_review_contract.py` 重载 manifest、比对 round audit、逐轮匹配一次性授权 → `pr_gate.py`。任何一层不完整均返回 block，不以 warning 降级。

## Alternatives Considered

- 给 `review_json_gate.py` 增加调用者自报的 artifact 数量：被否，单 artifact 输入无法验证集合真相。
- 只在 artifact 里写 `escalated_by/source`：被否，reviewer 可自填，不能证明 maintainer 授权。
- 只校验 `base_head_sha` 存在：被否，调用者仍可传全 PR diff。
- 仅用 `finding_id`：被否，不同 lane/head 可能同名；必须绑定 `source_artifact_id`。
- 保持 manifest v1 并把新字段全部可选：被否，无法判定何时缺失应 block；v2 discriminator 更明确。
- 把新语义继续堆入 `review_json_gate.py`：被否，文件已约 682 行，且跨 artifact 逻辑本就属于 shared semantics。

## Risks

- Security: 授权只来自外部 role-mapped evidence，所有 Git 命令使用参数数组；artifact 自报内容不能扩权。
- Compatibility: v1 单 artifact 保持不变；既有多轮流首次迁移到 v2 时会显式 block，这是防止无轮次证据静默放行的预期变化。
- Correctness: Git diff 字节必须使用固定命令；测试覆盖 rename/binary/空 diff 与缺对象错误，避免调用方式漂移。
- Data integrity: `(source_artifact_id, finding_id)` 与 exact set equality 防止 finding 丢失、重名和伪造额外项。
- Operations: 第 4 轮起需要人工逐轮授权，长队列会暂停；这是目标行为，不得由 auto 模式绕过。
- Maintenance: v2 round audit 只由 loader 派生，避免 schema、adapter、contract 各自计算产生漂移。

## Test Plan

- [ ] Schema/semantics：v1/v2 routing、轮次连续性、compact finding、typed pointer、carry 与 escalation union。
- [ ] Diff provenance：真实临时 Git 历史下校验 resumed/diff_only 正确 range；全 PR diff、错误 hash/base、缺 commit、binary diff 负例。
- [ ] Adapter/contract：role map 正反例、exact authorization、跨 round/head/PR 复用、round audit trusted reload 篡改。
- [ ] Compatibility：现有单轮 review fixtures 与现有 PR gate tests 零改动通过。
- [ ] Full verification：`/usr/bin/python3 -m pytest -q`、`python3 checks/check_workflow.py --repo . --all-specs`、`git diff --check`、两文件 `<800` 行。

## Rollback Plan

回滚 manifest v2 routing、bounded artifact 字段、PR evidence round audit/authorization、diff provenance 和文档即可。v2 证据回滚后会被旧 loader 明确拒绝，不会误当作 v1；v1 单轮证据不迁移、不改写。若 rollout 阶段需暂停，只停止生成 v2 多轮证据并保留 cap block，不得恢复 artifact 自报授权或 full-diff fallback。
