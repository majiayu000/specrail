# Tech Spec

## Linked Issue

GH-190

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":190,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/goal_contract.py","checks/pack_asset_validation.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","schemas/goal_contract.schema.json","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","templates/tranche_checkpoint.md","templates/zh-CN/tranche_checkpoint.md","tests/test_check_workflow.py","tests/test_goal_contract.py","tests/test_pack_asset_validation.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH190/product.md","specs/GH190/tech.md","specs/GH190/tasks.md"]}
-->

## Product Spec

见 `specs/GH190/product.md`。实现 B-001..B-019，不选择 GH-160 的预算值。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Goal guidance | `skills/specrail-implement-queue/SKILL.md:575-605` | 用 prose 要求 objective/预算/终止，但没有 builder。 | 转为唯一 payload 来源。 |
| checkpoint schema | `schemas/runtime_checkpoint.schema.json:269-320` | `goal` 无 required/closed/status enum；candidate 较严格。 | active Goal 需要 closed contract。 |
| gate dispatch | `checks/runtime_ledger_gate.py:473-523` | 调 `_validate_goal_candidate`，不验证 active goal。 | 新增分支与 binding。 |
| current validation | `checks/runtime_gate_rules.py:761-785` | 只检查 candidate 字符串/list 非空。 | 共享 builder/validator，避免重复。 |
| template | `templates/tranche_checkpoint.md:19-23` | 建议记录 Goal 与“保守默认”，没有来源或 digest。 | 输出完整 canonical payload。 |

## 设计方案

### 1. canonical builder 与 immutable contract

新增 `checks/goal_contract.py`：

```text
build_goal_contract(
  repo, auth_mode, queue_mode, capability,
  queue_records, human_decision_records,
  budget_selection_evidence, run_binding
) -> GoalDraft | GoalCandidate
```

builder 接收**原始 queue / human-decision 记录**（issue/pr identity、state、head 等
字段），自己按 identity 稳定排序并生成 RFC8785 canonical JSON，再取 SHA-256 得到不可变的
`queue_baseline_digest` 与 `human_decisions_baseline_digest`。不接受调用方预先算好的
digest，避免每个 caller 各自复刻 canonicalization。

创建前 `GoalDraft` 是独立 closed type，不含 `goal_id`、`status`、`tokens_used` 或
transition；它只作为 `create_goal` 的输入，不能被 checkpoint schema 引用。创建后的
`ActiveGoalContract` 是另一个 closed type，下列字段全部 required：

```text
version, goal_id, objective, objective_digest, contract_digest,
constraints[], termination_conditions[4], reanchor_contract,
token_budget, budget_source, budget_selection_digest,
tokens_used, status, repo_id, run_id, fencing_token,
queue_baseline_digest, human_decisions_baseline_digest
```

`budget_selection_evidence` 为 closed object：

```text
version: 1
user_input: {present, value, source_ref, source_digest}
pack_default: {configured, value, approval_ref, source_digest}
```

它记录 builder 实际评估的 invocation budget 与 pack 配置快照。`present/configured:
false` 时 value 必须为 null，但仍要有稳定的 snapshot source/digest；pack default 只有
正整数、非空维护者 `approval_ref` 与匹配 config digest 同时存在才合法。
`budget_source` 只能由 builder 按 user 优先、approved pack default 次之的固定次序导出；
caller 不能传 `budget_source` 或 disabled reason。builder 不定义 default 数值。两个
输入都明确缺失时导出 `missing_budget`；任一声明存在但值/批准/摘要非法时导出
`invalid_budget`，返回 blocked candidate，不创建 active Goal。checkpoint
`goal_routing` 持久化完整 evidence 与其 RFC8785 SHA-256，gate 重算选择结果；有可用
预算却自称 disabled 必须阻断。

objective 由固定模板渲染，明确全队列目标、四终止条件、checkpoint+remote re-anchor、
不替代 gates 与禁止越权。`objective_digest` 只覆盖 UTF-8 objective；
`contract_digest` 精确定义为以下 object 的 RFC8785 bytes 的 SHA-256：

```text
{
  version, objective, objective_digest, constraints,
  termination_conditions, reanchor_contract,
  token_budget, budget_source, budget_selection_digest,
  repo_id, run_id, fencing_token,
  queue_baseline_digest, human_decisions_baseline_digest
}
```

这使约束、终止、re-anchor、budget、run binding 与创建 baseline 任一漂移都会改变
`contract_digest`。生命周期可变字段 `goal_id`、`tokens_used`、`status`、current queue
与 transition events 不参与该摘要。

### 2. agent-facing CLI、tool payload 与状态 transition

`checks/goal_contract.py` 同时暴露纯函数与 agent 可执行接口：

```text
python3 checks/goal_contract.py build --input <closed-input.json> --json
python3 checks/goal_contract.py bind --input <allowed-build.json> --goal-id <id> --json
python3 checks/goal_contract.py migrate-checkpoint \
  --input <legacy.json> --routing-input <fresh-routing.json> --json
```

命令只从显式文件/参数读入，只向 stdout 输出单个 closed JSON envelope，不访问网络、
Goal API 或 session 正文。`build` allowed envelope 是
`{decision:"allowed",create_goal:{objective,token_budget},goal_draft,...}`；
blocked/invalid envelope 是
`{decision:"blocked",create_goal:null,goal_draft:null,goal_candidate,reason_ids[],errors[]}`。
`bind` 只接受原样的 allowed build envelope，重算 digest，并在非空 `goal_id` 存在时
输出 required-ID active contract。相同输入的 JSON 与 reason/error 顺序字节稳定；
`allowed` exit 0，任何 blocked/invalid/缺字段 exit 1。queue 与 implx 两个 Markdown
skill 必须执行 `build`/`bind`，只把 `create_goal` object 传给 Goal tool、只把 `bind`
输出写入 checkpoint；不得进程内调用或手拼 payload。Goal tool 缺 ID、异常或取消时不得
调用 `bind`。

active status enum：

```text
active → complete | exhausted | interrupted | blocked
```

checkpoint v4 required `goal_transitions[]`。创建成功先追加
`{sequence:0,from:null,to:"active",evidence_digest,prev_event_digest:null,event_digest}`；
后续 transition 使用连续 sequence、前一 event digest 与 canonical evidence digest，
事件本身 immutable。complete 需要 queue empty/fully blocked/only human decisions；
exhausted 需要 `tokens_used == token_budget` 与 handoff（超预算按 B-012 判 blocked）；
interrupted 需要 user interrupt marker；blocked 需要 blocker。gate 要求 current status
等于链尾 `to`，拒绝 sequence 缺口/重复、摘要断链、事件改写，以及任一 terminal 后的新
事件（尤其 terminal → active）；resume 同一 `goal_id` 必须携带完整 transition 链。

### 3. schema、queue rebind 与 gate

active `goal` 的闭合契约独立成 `schemas/goal_contract.schema.json`，由
`schemas/runtime_checkpoint.schema.json` 以 `$ref` 引用。原因是 checkpoint schema 已有
778 行，而 pack 校验对单个 schema 有 800 行上限。新 schema 必须注册进
`checks/pack_asset_validation.py` 的 `SPEC_SCHEMA_FILES` 并同步 ownership 测试。

checkpoint v4 必须持久化 `goal_routing`（`auth_mode`、`queue_mode`、
`goal_capability: available | unavailable`、完整 `budget_selection_evidence` 与
`budget_selection_digest`）以及封闭 `goal_disabled_reason`（`review_mode` |
`bounded_tranche` | `capability_unavailable` | `missing_budget` | `invalid_budget`）。
disabled reason 只能由 builder 输出，gate 必须从 routing evidence 重新导出并逐字段
对账。auto + full_queue_drain + capability available 且预算 evidence 合法时要求 active
goal；只有 evidence 确定为 missing/invalid 时才允许无 active goal 的 candidate。

创建时 canonical baseline records 存在 checkpoint v4 `goal_queue_baseline`，摘要必须
等于 active contract 的 `queue_baseline_digest`。checkpoint 另有 mutable
`queue_current_digest` 与 append-only `goal_queue_rebindings[]`，每个 event required：

```text
sequence, prior_digest, current_digest, remote_truth_digest,
repo_id, run_id, fencing_token, scope_digest,
prev_event_digest, event_digest
```

第一次 `prior_digest` 必须等于 baseline，之后必须等于前一 event 的 current digest；
checkpoint items 重算摘要必须等于链尾 current digest（无 event 时等于 baseline）。
fresh remote truth 中 item state/head 变化、新增或移出 actionable 集合属于合法同 scope
rebind，不修改 active contract/contract digest；repo/run/fencing/scope 变化、断链或绕过
event 直接改 current digest 必须阻断并要求新 Goal/人工决策。

runtime gate 调用共享 `validate_goal_contract()`，一次性交叉校验：

- objective/contract digest 与上述精确 canonical structure；
- immutable queue baseline、current digest 与 rebind hash chain；
- `human_decisions[]` 的创建 baseline；之后变化和 queue current snapshot 一起 rebind；
- repo/run/fencing 与 GH-189 binding（若 GH-189 尚未合并，实现需先 rebase）；
- raw budget evidence、derived selection/digest、tokens/status；
- checkpoint current status 与 append-only Goal transition chain。

gate 只读，无 Goal API/网络/session 访问。

### 4. checkpoint v4 迁移与 queue 集成

本变更目标明确为 `checkpoint_version: 4`。schema 使用 version-conditional `oneOf`：
v1、v2、v3 保留原结构的读取/诊断分支；v4 分支才允许新的 closed active contract，且
required-ID goal、routing/budget evidence、baseline/rebind、transition chain 均 required。
runtime gate 对 v1–v3 可完成旧结构诊断，但 resume/continue 或 legacy `goal` 非空时稳定
返回 `blocked: legacy_checkpoint_requires_migration`，绝不 grandfather 旧宽松 goal。

`migrate-checkpoint` 要求 fresh routing/budget evidence，并按 source version 固定处理：

- v1：保留通用 checkpoint/queue 字段，旧 goal 只转为 candidate/provenance；重新选预算；
- v2：同上，保留 tranche budget，但不得把它推断为 Goal budget；
- v3：同上，保留 trusted runtime counters/telemetry，旧 goal 仍不能 active。

三条路径都输出 v4、`goal:null`、`legacy_goal_provenance`（`from_version`、legacy goal
canonical digest、migration digest），且不调用 Goal API。缺 fresh routing input、
unsupported version 或迁移后 schema 不合法时 exit 1 且不输出可写 checkpoint。迁移后
必须 refresh remote truth，再调用 `build`；随后要么创建并 `bind` 新 Goal，要么持久化
builder 导出的合法 disabled/candidate 分支。

queue 与 implx 两个入口都只调用 CLI，不再自行拼 objective 或发明 conservative default；
`skills/implx/SKILL.md` 的 Goal 指引必须同步改写并重新 lock。GH-174 已合并时，详细操作
放 canonical runtime reference，主文件保留不可绕过 marker。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-004 B-005 B-019 | builder/CLI/template | `python3 -m pytest -q tests/test_goal_contract.py -k "builder or cli"` |
| B-003 B-015 | budget evidence/selection | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k budget` |
| B-006 B-011 B-017 | checkpoint/run/queue binding | `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k "goal and (binding or rebind)"` |
| B-007 | routing branches | `python3 -m pytest -q tests/test_goal_contract.py -k branch` |
| B-008 B-009 B-010 B-016 | append-only status transitions | `python3 -m pytest -q tests/test_goal_contract.py tests/test_runtime_ledger_gate.py -k transition` |
| B-012 | closed schema/gate | `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k goal` |
| B-013 B-014 | purity/failure | `python3 -m pytest -q tests/test_goal_contract.py -k "pure or failure"` |
| B-018 | v1–v3 → v4 migration | `python3 -m pytest -q tests/test_goal_contract.py tests/test_specrail_schema.py -k migration` |

## 数据流

```text
raw queue/human records + budget evidence + run binding
  → `build` CLI → GoalDraft + create_goal args
  → returned goal_id → `bind` CLI → v4 active contract
  → baseline/rebind + transition evidence → runtime gate
```

## 备选方案

- 继续自然语言拼 objective：不可验证，拒绝。
- schema 只要求非空字符串：无法证明终止/re-anchor，拒绝。
- 在本 issue 硬编码默认预算：越过 GH-160/维护者决策，拒绝。
- 用 Goal status 代替 queue truth：违反既有边界，拒绝。

## 风险

- Security: objective 不含 session/secret/raw issue body，只含稳定摘要。
- Compatibility: v1–v3 只能诊断或显式迁移到 v4，旧 active goal 不能静默 grandfather。
- Performance: builder/gate 是小型本地纯函数。
- Maintenance: builder、schema、template 与 queue 必须由同一 fixture 对账。

## 测试计划

- [ ] Unit: canonicalization、四终止、raw budget evidence、完整 contract digest、CLI
      envelope/exit code、transition/rebind hash chain 与失败。
- [ ] Integration: draft/active schema、runtime gate、queue branch/run binding、v1–v3
      version-conditional migration。
- [ ] Regression: full pytest、all-specs、depth/diff/hash。
- [ ] Forward-use: dry-run 构造 → tool args → fake ID → checkpoint → complete/exhausted。

## 回滚方案

回滚 builder、schema/gate、queue/template、tests/docs/lock 同一实现提交。不得保留新
active checkpoint 却回滚 validator；回滚后 Goal 只能视为 candidate/人工状态。
