# Tech Spec

## Linked Issue

GH-190

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":190,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/goal_contract.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","templates/tranche_checkpoint.md","tests/test_check_workflow.py","tests/test_goal_contract.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH190/product.md","specs/GH190/tech.md","specs/GH190/tasks.md"]}
-->

## Product Spec

见 `specs/GH190/product.md`。实现 B-001..B-014，不选择 GH-160 的预算值。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Goal guidance | `skills/specrail-implement-queue/SKILL.md:575-605` | 用 prose 要求 objective/预算/终止，但没有 builder。 | 转为唯一 payload 来源。 |
| checkpoint schema | `schemas/runtime_checkpoint.schema.json:269-320` | `goal` 无 required/closed/status enum；candidate 较严格。 | active Goal 需要 closed contract。 |
| gate dispatch | `checks/runtime_ledger_gate.py:473-523` | 调 `_validate_goal_candidate`，不验证 active goal。 | 新增分支与 binding。 |
| current validation | `checks/runtime_gate_rules.py:761-785` | 只检查 candidate 字符串/list 非空。 | 共享 builder/validator，避免重复。 |
| template | `templates/tranche_checkpoint.md:19-23` | 建议记录 Goal 与“保守默认”，没有来源或 digest。 | 输出完整 canonical payload。 |

## 设计方案

### 1. canonical builder

新增 `checks/goal_contract.py`：

```text
build_goal_contract(
  repo, auth_mode, queue_mode, capability,
  queue_snapshot_digest, human_decisions_digest,
  token_budget, budget_source, run_binding
) -> GoalContract | GoalCandidate
```

输入先 canonicalize：排序 queue item identity，但不丢状态/head；摘要用 SHA-256。
active contract 包含：

```text
version, goal_id?, objective, objective_digest,
constraints[], termination_conditions[4],
reanchor_contract, token_budget, budget_source,
tokens_used, status, repo_id, run_id, fencing_token,
queue_snapshot_digest, human_decisions_digest
```

`budget_source` 仅允许 `user` 或 `pack_default`。builder 不定义 default 数值；调用方必须
传入已批准正整数与来源。缺预算时返回 blocked candidate/reason，不创建 active Goal。

objective 由固定模板渲染，明确全队列目标、四终止条件、checkpoint+remote re-anchor、
不替代 gates 与禁止越权。digest 绑定 UTF-8 objective 加结构字段的 canonical JSON。

### 2. tool payload 与创建 binding

`create_goal` 参数直接取 `GoalContract.objective`/`token_budget`。工具成功返回 ID 后，
只允许 `bind_created_goal(contract, goal_id)` 生成 checkpoint `goal`；缺 ID/异常/取消
不生成 active payload。

active status enum：

```text
active → complete | exhausted | interrupted | blocked
```

terminal 不可回到 active。complete 需要 runtime checkpoint 已证明 queue empty/fully
blocked/only human decisions；exhausted 需要 `tokens_used >= token_budget` 与 handoff；
interrupted 需要 user interrupt marker；blocked 需要 blocker。

### 3. schema/gate

checkpoint schema 对 active `goal` 使用 `additionalProperties:false` 和全字段 required。
auto full-drain+capability 要求 active goal；其他分支禁止 active goal并要求合法 candidate
或 disabled reason。

runtime gate 调用共享 `validate_goal_contract()`，交叉校验：

- objective digest 与 canonical structure；
- queue/human decision digest 与 checkpoint items；
- repo/run/fencing 与 GH-189 binding（若 GH-189 尚未合并，实现需先 rebase）；
- budget/tokens/status；
- checkpoint status 与 Goal terminal transition。

gate 只读，无 Goal API/网络/session 访问。

### 4. 迁移与 queue 集成

checkpoint version 升级，旧宽松 `goal` 不能作为 active 证据；resume 时转成
goal_candidate 并要求人工/新 Goal 决策。queue/implx 只调用 builder，不再自行拼
objective 或发明 conservative default。GH-174 已合并时，详细操作放 canonical runtime
reference，主文件保留不可绕过 marker。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-004 B-005 | builder/template | `python3 -m pytest -q tests/test_goal_contract.py -k builder` |
| B-003 | budget source | `python3 -m pytest -q tests/test_goal_contract.py -k budget` |
| B-006 B-011 | checkpoint/run binding | `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k goal` |
| B-007 | routing branches | `python3 -m pytest -q tests/test_goal_contract.py -k branch` |
| B-008 B-009 B-010 | status transitions | `python3 -m pytest -q tests/test_goal_contract.py -k status` |
| B-012 | closed schema/gate | `python3 -m pytest -q tests/test_specrail_schema.py tests/test_runtime_ledger_gate.py -k goal` |
| B-013 B-014 | purity/failure | `python3 -m pytest -q tests/test_goal_contract.py -k "pure or failure"` |

## 数据流

```text
queue snapshot + approved budget + run binding
  → canonical GoalContract → create_goal args
  → returned goal_id → bound checkpoint → runtime gate
```

## 备选方案

- 继续自然语言拼 objective：不可验证，拒绝。
- schema 只要求非空字符串：无法证明终止/re-anchor，拒绝。
- 在本 issue 硬编码默认预算：越过 GH-160/维护者决策，拒绝。
- 用 Goal status 代替 queue truth：违反既有边界，拒绝。

## 风险

- Security: objective 不含 session/secret/raw issue body，只含稳定摘要。
- Compatibility: 旧 active goal checkpoint 需迁移，不能静默 grandfather。
- Performance: builder/gate 是小型本地纯函数。
- Maintenance: builder、schema、template 与 queue 必须由同一 fixture 对账。

## 测试计划

- [ ] Unit: canonicalization、四终止、budget、digest、状态与失败。
- [ ] Integration: schema/runtime gate/queue branch/run binding。
- [ ] Regression: full pytest、all-specs、depth/diff/hash。
- [ ] Forward-use: dry-run 构造 → tool args → fake ID → checkpoint → complete/exhausted。

## 回滚方案

回滚 builder、schema/gate、queue/template、tests/docs/lock 同一实现提交。不得保留新
active checkpoint 却回滚 validator；回滚后 Goal 只能视为 candidate/人工状态。
