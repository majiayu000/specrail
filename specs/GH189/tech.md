# Tech Spec

## Linked Issue

GH-189

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":189,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/active_run_lease.py","checks/check_workflow.py","checks/pack_asset_validation.py","checks/runtime_budget_dimensions.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/session_telemetry.py","examples/fixtures/runtime-active-run-lease-v4.json","schemas/active_run_lease.schema.json","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","templates/tranche_checkpoint.md","templates/zh-CN/tranche_checkpoint.md","tests/runtime_ledger_test_support.py","tests/test_active_run_lease.py","tests/test_check_workflow.py","tests/test_pack_asset_validation.py","tests/test_runtime_gate_rules.py","tests/test_runtime_ledger_budget.py","tests/test_runtime_ledger_gate.py","tests/test_runtime_ledger_queue.py","tests/test_session_telemetry.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH189/product.md","specs/GH189/tech.md","specs/GH189/tasks.md"]}
-->

## Product Spec

见 `specs/GH189/product.md`。实现 B-001..B-014，不涉及 GH-160。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue startup | `skills/specrail-implement-queue/SKILL.md:11-46` | 枚举 worktrees/branches，但没有 active runtime owner。 | acquire 必须在 queue/lane 前。 |
| checkpoint path | `skills/specrail-implement-queue/SKILL.md:545-573` | 所有运行使用 `.specrail/runtime/current.json`。 | checkpoint 必须绑定 run/token，但 lease 不能放在 worktree-local 路径。 |
| runtime schema | `schemas/runtime_checkpoint.schema.json:41-74` | 有 `goal_id`/repo/tranche，无 run ID/fencing token。 | 增加不可串线绑定。 |
| runtime gate | `checks/runtime_ledger_gate.py:473-523` | 校验 checkpoint 字段，不读取 active lease。 | 写/恢复前需显式 lease evidence。 |
| goal budget rules | `checks/runtime_gate_rules.py:510-530` | v3 只检查可选 goal_id。 | run/token 成为 v3+ 强制字段。 |

## 设计方案

### 1. 共享位置与身份

`checks/active_run_lease.py` 用参数数组调用 Git 获取 `--git-common-dir`，解析后要求位于
repo 控制范围内且无 symlink escape。lease 存放于：

```text
<git-common-dir>/specrail/active-run.lock/lease.json
```

目录的原子 `mkdir` 是 acquire primitive；所有 worktree 共享。repo identity 是
canonical git-common-dir identity 与规范化 default remote 的哈希，输出只显示短 digest，
不暴露 home path。非 Git repo 或不支持原子目录创建的 FS 返回 unsupported。

### 2. closed lease schema

`active_run_lease.schema.json` 禁止未知字段并要求：

```text
version, repo_id, run_id, fencing_token,
owner_marker, created_at, renewed_at, expires_at,
checkpoint_bound, checkpoint_digest, goal_id?, status
```

`fencing_token` 来自 common-dir 内 append-only counter，以原子 replace + fsync 更新。
acquire 必须同时成功创建 lock dir、写 temp、fsync、rename；异常留下的无效目录被 inspect
判为 corrupt，不自动删除。`checkpoint_bound` 是 required boolean；当它为 `false` 时
`checkpoint_digest` 必须为 `null`，为 `true` 时必须匹配
`^sha256:[0-9a-f]{64}$`；schema 用条件分支关闭其他组合。

### 3. 状态、转换与 compare-and-replace 串行化

纯函数 `inspect_lease()` 返回 `free | held | stale | corrupt | unsafe | unsupported`。
所有修改 API（包括 acquire）先对
`<git-common-dir>/specrail/active-run.mutex` 取得跨进程、repo-wide 的独占 advisory
lock，再在同一临界区内完成 read → digest compare → state/token compare → temp write
→ fsync → atomic replace/remove。mutex 获取采用一次 non-blocking 尝试：竞争时返回
`busy` 并 fail closed，不重试、不 polling；文件描述符关闭或进程退出时由内核释放。
mutex 必须是以 no-follow 方式打开的稳定 regular file，路径同样拒绝 symlink/escape；
平台或文件系统不支持该原语时返回 `unsupported`。单独的 atomic rename 只保证文件
完整，不得被描述为 compare-and-swap。`expected_digest` 是上一次 inspect 返回的当前
lease bytes SHA-256；修改 API 取得 mutex 后必须重新读取并比较它。

修改 API：

- `acquire(expected_free, run_id, owner_marker, ttl_seconds, checkpoint_digest=None)`；
  队列 startup 在写首个 checkpoint 之前取租，因此 `checkpoint_digest` 允许为显式
  `null`（sentinel `""` 非法）。首租写入 `checkpoint_digest: null` 与
  `checkpoint_bound: false`，schema 用 `["string","null"]` 表达；首次 checkpoint
  写入后必须立即 `renew(...)` 填入真实 digest 并置 `checkpoint_bound: true`。
  未绑定 lease 只允许执行首次 checkpoint bind，不得通过 resume、lane 或 remote-write
  gate，避免实现编造未经验证的占位值；
- `renew(expected_digest, run_id, token, checkpoint_digest, ttl_seconds)`；
  `ttl_seconds` 必须是正整数且不超过实现常量 `MAX_LEASE_TTL_SECONDS`。调用方在阻塞
  等待前以“声明 wait deadline + 固定 grace”计算 TTL；若所需期限超过硬上限，必须
  先 checkpoint/handoff 并停止，不能暗中截断或无限续租；
- `release(expected_digest, run_id, token)`；
- `takeover(expected_stale_digest, new_run_id, authorization, ttl_seconds)`。

takeover 写一条有界审计记录后生成更大 token；只接受本轮 conversation marker、actor 与
reason，且 acquire/takeover 的 `ttl_seconds` 服从同一硬上限。PID 只可作为诊断 hint，
不参与授权或真值。时间判断使用 UTC timestamp 加单调本进程 duration；检测回拨时 stale
判定 fail closed。renew/release/takeover 的竞争测试必须以 barrier 让两个操作携带同一
旧 digest 并发进入，证明 mutex 内重新读取后只有一个 compare 可以成功，旧 fencing
token 永远不能覆盖 takeover 后的新 lease。

### 4. checkpoint/gate binding

`checkpoint_version: 4` 是第一个 lease-aware 版本，新增 required、closed
`run_lease` object：

```text
repo_id, run_id, fencing_token
```

绑定只保留一个方向：checkpoint 携带不可变 lease identity；lease 的
`checkpoint_digest` 是对磁盘 checkpoint 完整 bytes 的 `sha256:<lowercase hex>`。
checkpoint 不保存
lease digest，因此 renew 改变 `renewed_at`、`expires_at` 或 `checkpoint_digest` 都不会
反向改变 checkpoint，绑定存在稳定点。`runtime_ledger_gate.py` 接受显式 `--lease`
路径，要求 lease 已绑定、identity 完全一致，并重算 checkpoint digest；它本身只读。
任一侧被替换或 lease 尚未完成首次绑定都必须 fail closed。

queue 在 Startup acquire；在 spawn lane、checkpoint replace、PR/comment/label/push 等
远端写前 renew/validate。checkpoint replace 成功但 lease bind 失败时不得宣称 checkpoint
可 resume，下一次 gate 会因 digest mismatch 阻断。

resume 的安全授权明确只有 checkpoint+lease 两方。checkpoint 可保留 `goal_id`，调用方
也可在恢复时独立调用 live Goal 查询来确认 Goal ID/status，以恢复目标和预算上下文；
但现有 Goal API 没有独立承载 repo/run/token 的合同，因此 Goal evidence 不参与 fencing
判断，也不得宣称 checkpoint+Goal+lease 三方安全绑定。没有 Goal 能力或 live Goal
evidence 时，只报告 Goal continuity 未验证，不得削弱 checkpoint+lease gate。

#### checkpoint 版本兼容

| Version | Schema/gate | Lease-aware 权限 |
| --- | --- | --- |
| 1–3 | 继续接受，保留现有 fixture 与离线历史校验；v3 budget/telemetry 语义不变 | 不得用于受 lease 保护的 resume、lane 或 remote write；必须开始新 run 并生成 v4 |
| 4 | 继承 v3 budget/telemetry 规则并强制 `run_lease` | 通过显式 `--lease` 的 identity + 单向 checkpoint digest 校验后允许 |
| 5+ | 拒绝 | 无 |

因此现有 `examples/fixtures/runtime-*.json`、`tests/fixtures/gh143-standard-auto.json`、
`tests/test_runtime_sensitive_routes.py` 与
`tests/test_spec_revision_route_end_to_end.py` 继续作为 v1–v3 compatibility evidence，
不要求批量补 `run_lease`。新增
`examples/fixtures/runtime-active-run-lease-v4.json`；同时更新
`tests/runtime_ledger_test_support.py` 的 v4 builder、
`tests/test_runtime_ledger_queue.py`（unknown-version case 改测 5）及
`tests/test_specrail_schema.py` 的 v1–v3 兼容/v4 required 断言。
`runtime_gate_rules.py`、`runtime_budget_dimensions.py` 与 `session_telemetry.py` 中写死
“v3 only”的判断/文案改成 v3+，确保 v4 不绕过现有硬预算。

普通 `check_workflow.py` 只校验 checker/schema 是 pack assets，不读取 common dir lease。

### 5. 无 polling 生命周期

不启动 heartbeat thread。owner 在已有关键状态转换前续租；长阻塞等待前用 required
`ttl_seconds` 将 expiry 覆盖已声明 deadline + grace，返回后立即 renew。等待超过
`MAX_LEASE_TTL_SECONDS` 时先 checkpoint/handoff，不允许扩大上限。held lease 或
mutation mutex busy 都不触发轮询；第二 run 立即报告并停止。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 | common-dir + atomic acquire/mutation mutex | `python3 -m pytest -q tests/test_active_run_lease.py -k "worktree or concurrent or mutex"` |
| B-003 B-004 B-010 | fencing、bounded TTL、serialized compare-and-replace | `python3 -m pytest -q tests/test_active_run_lease.py -k "fencing or ttl or replace_race"` |
| B-005 B-006 B-009 | stale/takeover | `python3 -m pytest -q tests/test_active_run_lease.py -k "stale or takeover or clock"` |
| B-007 | checkpoint+lease 单向 digest resume binding（含 Goal 非安全边界与首租阻断） | `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k "lease or goal or first_acquire or digest"` |
| B-008 B-011 B-014 | unsafe/corrupt/failure | `python3 -m pytest -q tests/test_active_run_lease.py -k "unsafe or corrupt or failure"` |
| B-012 B-013 | pure pack/inspect | `python3 -m pytest -q tests/test_check_workflow.py tests/test_active_run_lease.py -k "workflow or inspect"` |

## 数据流

```text
git common dir → mutation mutex → inspect/acquire → run_id + fencing token
      checkpoint identity → lease checkpoint_digest → runtime gate
      optional live Goal evidence → continuity/budget context only
      lane/checkpoint/remote write ← bounded renew/validate
```

仅 lease API 写 common-dir；gate、inspect 与 pack check 均只读。

## 备选方案

- worktree-local `.specrail/runtime`: 无法跨 worktree 排他，拒绝。
- PID lock: PID 可复用且跨 session 不稳定，拒绝。
- GitHub label: 有网络竞态和外部写副作用，拒绝。
- 自动 stale takeover: 会覆盖暂停中的合法 run，拒绝。

## 风险

- Security: 路径、owner 输出与原子文件操作 fail closed；不记录 session 正文。
- Compatibility: v1–v3 保留离线校验但不能授权 lease-aware resume；新 run 生成 v4。
- Performance: 每个关键写边界一次小文件验证，无轮询。
- Maintenance: lease 与 checkpoint 两方 binding 必须共享 validator；Goal 不进入安全边界。

## 测试计划

- [ ] Unit: 状态机、closed schema、TTL 上限、mutex、原子失败、时钟、路径和授权。
- [ ] Integration: 两 worktree 并发、serialized replace race、稳定的单向 digest binding、
      v1–v4 compatibility、queue boundary fixture。
- [ ] Regression: full pytest、all-specs、depth/diff/pack checks。
- [ ] Forward-use: 两个真实临时 worktree 竞争、resume、stale authorized takeover。

## 回滚方案

回滚 checker/schema/queue/wiring/tests/docs/lock 的同一实现提交。保留的 common-dir lease
可由原 owner 显式释放或人工归档；不得在回滚脚本中递归删除 `.git/specrail`。
