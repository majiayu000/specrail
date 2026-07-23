# Tech Spec

## Linked Issue

GH-189

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":189,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/active_run_lease.py","checks/check_workflow.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","schemas/active_run_lease.schema.json","schemas/runtime_checkpoint.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","templates/tranche_checkpoint.md","tests/test_active_run_lease.py","tests/test_check_workflow.py","tests/test_runtime_ledger_gate.py"],"spec_refs":["specs/GH189/product.md","specs/GH189/tech.md","specs/GH189/tasks.md"]}
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
checkpoint_digest, goal_id?, status
```

`fencing_token` 来自 common-dir 内 append-only counter，以原子 replace + fsync 更新。
acquire 必须同时成功创建 lock dir、写 temp、fsync、rename；异常留下的无效目录被 inspect
判为 corrupt，不自动删除。

### 3. 状态与转换

纯函数 `inspect_lease()` 返回 `free | held | stale | corrupt | unsafe | unsupported`。
修改 API：

- `acquire(expected_free, run_id, owner_marker, ttl)`；
- `renew(expected_digest, run_id, token, checkpoint_digest)`；
- `release(expected_digest, run_id, token)`；
- `takeover(expected_stale_digest, new_run_id, authorization)`。

takeover 写一条有界审计记录后生成更大 token；只接受本轮 conversation marker、actor 与
reason。PID 只可作为诊断 hint，不参与授权或真值。时间判断使用 UTC timestamp 加单调
本进程 duration；检测回拨时 stale 判定 fail closed。

### 4. checkpoint/gate binding

runtime checkpoint 新增 required `run_lease`：

```text
repo_id, run_id, fencing_token, lease_digest
```

queue 在 Startup acquire；在 spawn lane、checkpoint replace、PR/comment/label/push 等
远端写前 renew/validate。`runtime_ledger_gate.py` 接受显式 `--lease` 路径，交叉检查
checkpoint binding；它本身只读。resume 需要 checkpoint+Goal+lease 三者 run/token 相同。

普通 `check_workflow.py` 只校验 checker/schema 是 pack assets，不读取 common dir lease。

### 5. 无 polling 生命周期

不启动 heartbeat thread。owner 在已有关键状态转换前续租；长阻塞等待前将 expiry
覆盖允许的最长 wait，返回后立即 renew。held lease 不触发轮询；第二 run 立即报告并停止。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 | common-dir + atomic acquire | `python3 -m pytest -q tests/test_active_run_lease.py -k "worktree or concurrent"` |
| B-003 B-004 B-010 | fencing operations | `python3 -m pytest -q tests/test_active_run_lease.py -k fencing` |
| B-005 B-006 B-009 | stale/takeover | `python3 -m pytest -q tests/test_active_run_lease.py -k "stale or takeover or clock"` |
| B-007 | checkpoint/Goal resume binding | `python3 -m pytest -q tests/test_runtime_ledger_gate.py -k lease` |
| B-008 B-011 B-014 | unsafe/corrupt/failure | `python3 -m pytest -q tests/test_active_run_lease.py -k "unsafe or corrupt or failure"` |
| B-012 B-013 | pure pack/inspect | `python3 -m pytest -q tests/test_check_workflow.py tests/test_active_run_lease.py -k "workflow or inspect"` |

## 数据流

```text
git common dir → inspect/acquire → run_id + fencing token
      checkpoint/Goal ← binding → runtime gate
      lane/checkpoint/remote write ← renew/validate
```

仅 lease API 写 common-dir；gate、inspect 与 pack check 均只读。

## 备选方案

- worktree-local `.specrail/runtime`: 无法跨 worktree 排他，拒绝。
- PID lock: PID 可复用且跨 session 不稳定，拒绝。
- GitHub label: 有网络竞态和外部写副作用，拒绝。
- 自动 stale takeover: 会覆盖暂停中的合法 run，拒绝。

## 风险

- Security: 路径、owner 输出与原子文件操作 fail closed；不记录 session 正文。
- Compatibility: checkpoint schema 升版，旧 checkpoint 只能显式迁移/新 run 生成。
- Performance: 每个关键写边界一次小文件验证，无轮询。
- Maintenance: lease 与 checkpoint/Goal 三方 binding 必须共享 validator。

## 测试计划

- [ ] Unit: 状态机、schema、原子失败、时钟、路径和授权。
- [ ] Integration: 两 worktree 并发、runtime gate binding、queue boundary fixture。
- [ ] Regression: full pytest、all-specs、depth/diff/pack checks。
- [ ] Forward-use: 两个真实临时 worktree 竞争、resume、stale authorized takeover。

## 回滚方案

回滚 checker/schema/queue/wiring/tests/docs/lock 的同一实现提交。保留的 common-dir lease
可由原 owner 显式释放或人工归档；不得在回滚脚本中递归删除 `.git/specrail`。
