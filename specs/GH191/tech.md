# Tech Spec

## Linked Issue

GH-191

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":191,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/issue_attempt_collector.py","checks/issue_attempt_writer.py","checks/pack_asset_validation.py","checks/issue_progress_gate.py","schemas/issue_attempt_anchor.schema.json","schemas/issue_attempt_ledger.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","templates/issue_attempt_anchor.json","templates/issue_attempt_ledger.json","tests/test_check_workflow.py","tests/test_issue_attempt_collector.py","tests/test_issue_attempt_writer.py","tests/test_pack_asset_validation.py","tests/test_issue_progress_gate.py"],"spec_refs":["specs/GH191/product.md","specs/GH191/tech.md","specs/GH191/tasks.md"]}
-->

## Product Spec

见 `specs/GH191/product.md`。实现 B-001..B-016，是 GH-157 的确定性后续。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| prose breaker | `skills/specrail-implement-queue/SKILL.md:447-477` | 模型自行数 commit/PR/tranche 并判断 near-identical。 | 替换成 collector + offline gate。 |
| runtime history | `schemas/runtime_checkpoint.schema.json:41-320` | 无逐 issue append-only attempt ledger。 | 独立 ledger 避免 current checkpoint 覆盖历史。 |
| retry evidence | `skills/specrail-implement-queue/SKILL.md:785-799` | 只持久化同一 gate 的重复 rejection。 | 可复用 stable fingerprint 思路但不混合语义。 |
| duplicate gate | `checks/duplicate_work_gate.py:1-300` | 处理现有 branch/PR，不衡量 durable progress。 | 保持职责独立。 |
| workflow | `checks/check_workflow.py:485-512` | 无 attempt schema/gate asset 检查。 | 新资产加入 pack required/check。 |

## 设计方案

### 1. 不可变事件 ledger

路径 `.specrail/runtime/issue-attempts/GH<n>.json`。collector/gate 只读，queue 和
orchestrator 也不得直接编辑；所有追加都经过 `checks/issue_attempt_writer.py`。
closed schema：

```text
version, repo_id, issue, current_scope_epoch, events[]
event = event_id, event_type, occurred_at, as_of, snapshot_digest,
        scope_epoch, prev_event_digest, event_digest, payload
event_type = baseline | scope_opened | attempt_started |
             attempt_finished | attempt_interrupted
attempt_started.payload = attempt_id, run_id, fencing_token, tranche_id,
                          before_head, target_ids[], work_fingerprint
terminal.payload = attempt_id, after_head, commit_evidence[],
                   verification/review/coverage evidence,
                   progress_delta[], outcome
commit_evidence = sha, parent_shas[], work_fingerprint,
                  durable_progress_evidence[]
```

开始 round 前，writer 必须先落盘唯一 `attempt_started`；round 结束或中断时为同一
`attempt_id` 追加且只追加一个 terminal event。terminal 不修改 start，重复 start、
重复 terminal、terminal-before-start、字段跨 run/head/tranche 串线或没有 terminal 的
陈旧 attempt 都 fail closed。显式 rescope 追加 `scope_opened`，breaker 只统计当前
epoch，旧 epoch 的事件仍保留。

`event_digest` = 该事件规范化 JSON（不含 `event_digest`）的 sha256，
`prev_event_digest` = 前一事件摘要（首条 baseline 为 `null`）。内部链只负责检测事件
改写、重排与链断裂；它**不**被宣称能单独检测自洽的尾部截断或整体重写。

### 2. 可信外部尾锚点

runtime 必须提供位于 ledger 与 repo checkout 之外、worker 无法直接改写的 anchor
provider。它以 `(repo_id, issue)` 为 key 单调保存：

```text
generation, event_count, tail_event_digest, ledger_digest,
baseline_id, transaction_id, state = prepared | committed
```

provider 返回由配置的 trust root 可验证的 attestation；offline gate 接受显式
attestation 输入并校验 trust root、repo/issue、单调 generation、`committed` 状态以及
三个 digest/count 与 ledger 完全一致。复制在 ledger 内、工作树文件或 agent 可编辑的
checkpoint 字段都不算可信 anchor。anchor 缺失、回退、pending、签名无效或不匹配一律
`blocked`，从而检测内部链无法发现的尾部截断和整体重写。

writer 使用两阶段协议：对 old generation/digest 执行 provider prepare/CAS，写
canonical temp、`fsync` 文件、atomic replace、`fsync` 父目录，再 commit transaction
并保存 attestation。任一步中断都会留下可识别 transaction；幂等 `recover` 只能用
prepared 内容完成或回滚，gate 在恢复前 fail closed，禁止静默接受 ledger/anchor
任一侧的较新值。

### 3. 首次基线与迁移

writer 提供 `init-baseline` 与 `migrate-baseline`。两者仅在 ledger 不存在且 provider
确认该 key 从未创建时可执行，并要求：

```text
repo_id, issue, trusted_head, as_of, snapshot_digest,
history_evidence_digest, authorization = {actor, source, decision_id}
```

baseline 的 history evidence 是 bounded remote inventory，覆盖启用前与 issue 关联的
commit/PR/tranche，不能用空数组假装未知历史为零；`migrate-baseline` 还绑定 legacy
source digest/count。命令通过同一两阶段 writer 同时创建首个不可变 baseline event 与
generation 1 anchor。provider 已有 key 而 ledger 缺失表示 history loss，必须
`blocked`，不得重新 init；授权缺失、repo/head 不匹配或 legacy evidence 不完整也失败。

### 4. bounded collector 与可信 `as_of`

`issue_attempt_collector.py` 接受显式 issue、base/head、checkpoint/run binding、spec task
IDs、PR/review/verification evidence paths；它不扫描 session JSONL，也不做 GitHub write。
它输出 candidate event，不写 ledger。

每份 remote/evidence snapshot 必须包含来源可验证的 `as_of` 与覆盖 canonical payload
的 `snapshot_digest`，并由 ledger event 摘要继续绑定。所有 future-time、事件排序与
head freshness 检查都只相对该 `as_of`，gate 不读取运行时墙钟。因此同一
ledger+anchor attestation+snapshot+`as_of` 无论何时重跑，decision/exit code 都相同。

work fingerprint 是 canonical JSON digest：

```text
issue + scope_epoch + sorted target_ids + affected area IDs +
normalized failing/review fingerprints
```

commit message 不参与。evidence 只允许受控 path/URL/digest/status，不嵌 raw logs。

### 5. 确定性 writer

`issue_attempt_writer.py` 是唯一 mutation boundary，提供 `init-baseline`、
`migrate-baseline`、`append-start`、`append-terminal`、`open-scope` 与 `recover`。
每次调用必须显式提供 expected ledger digest、expected anchor generation、candidate
event 和 anchor attestation；helper 重算 canonical digest，拒绝旧事件的删除/改写、
重复 ID/terminal/commit SHA、非法状态转换和 CAS 冲突。queue Skill 只能调用该 helper，
不能拼装或直接写 JSON。其命令输出有界、错误非零且不静默降级。

### 6. durable progress

gate 重新计算 `progress_delta`：

- 新增通过验证绑定的 acceptance/task ID；
- 同一 failure fingerprint 从 failed 变 passed；
- blocking finding 在新 exact head 上 resolved；
- issue/PR 进入 spec 定义的 terminal state。

新 commit/head 自身不是 progress。自报 delta 与重算不一致即失败。

### 7. breaker decision

`issue_progress_gate.py` 返回：

```text
decision = allowed | warn | needs_human | blocked      # 与 schemas/evaluation_result.schema.json 一致
reason_ids = five_no_progress_commits |
             three_same_work_fingerprint_commits |
             three_no_progress_tranches |
             ledger_unreadable | ledger_chain_broken | ledger_incomplete |
             anchor_invalid | history_loss | baseline_required
```

breaker trip 与非法 history 都编码为 `blocked` + 稳定 reason id（trip 用前三个，
history 缺陷用后三个），不引入 `tripped`/`invalid` 这类仓库共享契约之外的 decision
（`checks/specrail_lib.py` 与 `schemas/evaluation_result.schema.json` 只允许四个值），
以免通用 gate 校验、rejection persistence 与队列调用方误判。

阈值在单次评估中全部计算。第一阈值统计当前 epoch 中引用 issue 且无 durable progress
的 commit，达到 5 个即 trip；同一 attempt 的多个 commit 分别计数。第二阈值按 commit
祖先/ledger 顺序统计连续 3 个相同规范化 work fingerprint 的无进展 commit，一个
attempt 内也可触发；attempt 数量不参与这两个阈值。第三阈值仍按已结束 tranche。
重复 commit SHA 或无法确定稳定顺序时 fail closed。unreadable/incomplete history 为
invalid/fail closed。queue 在开 lane 前调用；trip/invalid 都不继续。gate 不
park/draft/comment，orchestrator 仅在当前用户已授权外部写时按 GH-157 行为执行。

GH-189 合并后 ledger/attempt 强制 run/fencing binding；GH-174 合并后主 Skill 保留
breaker marker，详细操作进入 canonical runtime/recovery reference。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-009 B-011 | event ledger/state validation | `python3 -m pytest -q tests/test_issue_progress_gate.py -k "ledger or event"` |
| B-003 B-004 | progress recompute | `python3 -m pytest -q tests/test_issue_progress_gate.py -k progress` |
| B-005 B-006 B-007 B-008 | thresholds | `python3 -m pytest -q tests/test_issue_progress_gate.py -k threshold` |
| B-010 | queue decision boundary | `python3 -m pytest -q tests/test_issue_progress_gate.py -k authorization` |
| B-012 B-016 | collector/gate purity and `as_of` | `python3 -m pytest -q tests/test_issue_attempt_collector.py tests/test_issue_progress_gate.py -k "deterministic or as_of"` |
| B-013 | external anchor continuity | `python3 -m pytest -q tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py -k anchor` |
| B-014 | deterministic writer/CAS/recovery | `python3 -m pytest -q tests/test_issue_attempt_writer.py -k "append or cas or recover"` |
| B-015 | baseline/migration/history loss | `python3 -m pytest -q tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py -k "baseline or migration or history_loss"` |

## 数据流

```text
bounded repo/GitHub artifacts → collector candidate → deterministic writer
writer ↔ trusted anchor provider → immutable event ledger + anchor attestation
ledger + attestation + bound as_of snapshot → offline gate → allowed/blocked
```

## 备选方案

- 只数 commit message prefix：可轻易改写绕过且误伤真实进展，拒绝。
- 存在 current checkpoint：会被覆盖且不能跨 session 审计，拒绝。
- 让 gate 自动 park：混合判断与外部副作用，拒绝。
- 读取 session transcript：高成本且违反 queue state 边界，拒绝。
- 只用 ledger 内部哈希链：不能检测自洽的尾截断/整体重写，拒绝。
- 让 queue/agent 直接编辑 JSON：绕过 CAS、fsync 与状态机，拒绝。

## 风险

- Security: 路径/URL/digest allowlist，不收 raw log/session/secret。
- Compatibility: 旧运行需显式 baseline/migration；anchor 已存在时不能伪装首次启用。
- Availability: anchor provider/pending transaction 不可用时 fail closed，由 writer
  `recover` 恢复，不降级成本地自报 anchor。
- Performance: 每 issue 有界小 JSON 与 bounded evidence。
- Maintenance: target IDs 与 scope epoch 需和 spec revision 对齐。

## 测试计划

- [ ] Unit: event schema、start/terminal、anchor、writer CAS/recovery、baseline/migration、
      `as_of`、fingerprint、progress、commit 阈值与错误聚合。
- [ ] Integration: queue pre-lane 只调用 writer、run lease binding、rescope epoch、
      provider pending/history-loss fail closed。
- [ ] Regression: full pytest、all-specs、depth/diff/hash。
- [ ] Forward-use: 三 compaction/session resume 后仍从 ledger+anchor trip。

## 回滚方案

回滚 collector/writer/gate/anchor+ledger schema/template/queue/tests/docs/lock 同一提交。
保留 ledger 与外部 anchor 为审计 artifact，不自动删除或回退 anchor generation；
回滚期间不得声称 breaker 仍被确定性执行。
