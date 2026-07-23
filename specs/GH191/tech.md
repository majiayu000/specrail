# Tech Spec

## Linked Issue

GH-191

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":191,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/issue_attempt_collector.py","checks/issue_progress_gate.py","schemas/issue_attempt_ledger.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","templates/issue_attempt_ledger.json","tests/test_check_workflow.py","tests/test_issue_attempt_collector.py","tests/test_issue_progress_gate.py"],"spec_refs":["specs/GH191/product.md","specs/GH191/tech.md","specs/GH191/tasks.md"]}
-->

## Product Spec

见 `specs/GH191/product.md`。实现 B-001..B-012，是 GH-157 的确定性后续。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| prose breaker | `skills/specrail-implement-queue/SKILL.md:447-477` | 模型自行数 commit/PR/tranche 并判断 near-identical。 | 替换成 collector + offline gate。 |
| runtime history | `schemas/runtime_checkpoint.schema.json:41-320` | 无逐 issue append-only attempt ledger。 | 独立 ledger 避免 current checkpoint 覆盖历史。 |
| retry evidence | `skills/specrail-implement-queue/SKILL.md:785-799` | 只持久化同一 gate 的重复 rejection。 | 可复用 stable fingerprint 思路但不混合语义。 |
| duplicate gate | `checks/duplicate_work_gate.py:1-300` | 处理现有 branch/PR，不衡量 durable progress。 | 保持职责独立。 |
| workflow | `checks/check_workflow.py:485-512` | 无 attempt schema/gate asset 检查。 | 新资产加入 pack required/check。 |

## 设计方案

### 1. append-only ledger

路径 `.specrail/runtime/issue-attempts/GH<n>.json`，由 orchestrator 写，collector/gate
只读。closed schema：

```text
version, repo_id, issue, scope_epoch, attempts[]
attempt = id, run_id, fencing_token, tranche_id,
          started_at, ended_at?, before_head, after_head?,
          target_ids[], work_fingerprint,
          evidence[], progress_delta[], outcome
```

每次更新必须提供 previous ledger digest；写 temp+fsync+atomic replace。validator 拒绝
删除/reorder/改写既有 attempt、重复 ID、时间倒序和 run/head 串线。scope_epoch 只能由
显式 rescope evidence 追加，旧 attempts 不删除。

### 2. bounded collector

`issue_attempt_collector.py` 接受显式 issue、base/head、checkpoint/run binding、spec task
IDs、PR/review/verification evidence paths；它不扫描 session JSONL，也不做 GitHub write。
输出候选 attempt JSON，由 orchestrator append。

work fingerprint 是 canonical JSON digest：

```text
issue + scope_epoch + sorted target_ids + affected area IDs +
normalized failing/review fingerprints
```

commit message 不参与。evidence 只允许受控 path/URL/digest/status，不嵌 raw logs。

### 3. durable progress

gate 重新计算 `progress_delta`：

- 新增通过验证绑定的 acceptance/task ID；
- 同一 failure fingerprint 从 failed 变 passed；
- blocking finding 在新 exact head 上 resolved；
- issue/PR 进入 spec 定义的 terminal state。

新 commit/head 自身不是 progress。自报 delta 与重算不一致即失败。

### 4. breaker decision

`issue_progress_gate.py` 返回：

```text
allowed | tripped | invalid
trip_reasons = five_no_progress_attempts |
               three_same_work_fingerprint |
               three_no_progress_tranches
```

阈值在单次评估中全部计算。unreadable/incomplete history 为 invalid/fail closed。queue 在
开 lane 前调用；trip/invalid 都不继续。gate 不 park/draft/comment，orchestrator 仅在
当前用户已授权外部写时按 GH-157 行为执行。

GH-189 合并后 ledger/attempt 强制 run/fencing binding；GH-174 合并后主 Skill 保留
breaker marker，详细操作进入 canonical runtime/recovery reference。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-009 B-011 | ledger schema/append | `python3 -m pytest -q tests/test_issue_progress_gate.py -k ledger` |
| B-003 B-004 | progress recompute | `python3 -m pytest -q tests/test_issue_progress_gate.py -k progress` |
| B-005 B-006 B-007 B-008 | thresholds | `python3 -m pytest -q tests/test_issue_progress_gate.py -k threshold` |
| B-010 | queue decision boundary | `python3 -m pytest -q tests/test_issue_progress_gate.py -k authorization` |
| B-012 | collector/gate purity | `python3 -m pytest -q tests/test_issue_attempt_collector.py tests/test_issue_progress_gate.py -k deterministic` |

## 数据流

```text
bounded repo/GitHub artifacts → collector candidate → append-only ledger
ledger + fresh terminal truth → offline progress gate → allowed/tripped/invalid
```

## 备选方案

- 只数 commit message prefix：可轻易改写绕过且误伤真实进展，拒绝。
- 存在 current checkpoint：会被覆盖且不能跨 session 审计，拒绝。
- 让 gate 自动 park：混合判断与外部副作用，拒绝。
- 读取 session transcript：高成本且违反 queue state 边界，拒绝。

## 风险

- Security: 路径/URL/digest allowlist，不收 raw log/session/secret。
- Compatibility: 旧运行需显式 baseline；不能伪造历史。
- Performance: 每 issue 有界小 JSON 与 bounded evidence。
- Maintenance: target IDs 与 scope epoch 需和 spec revision 对齐。

## 测试计划

- [ ] Unit: schema、append-only、fingerprint、progress、阈值、错误聚合。
- [ ] Integration: queue pre-lane、run lease binding、rescope epoch。
- [ ] Regression: full pytest、all-specs、depth/diff/hash。
- [ ] Forward-use: 三 compaction/session resume 后仍从 ledger trip。

## 回滚方案

回滚 collector/gate/schema/template/queue/tests/docs/lock 同一提交。保留 ledger 为审计
artifact，不自动删除；回滚期间不得声称 breaker 仍被确定性执行。
