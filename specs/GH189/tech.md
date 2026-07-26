# Tech Spec

## Linked Issue

GH-189

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":189,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/active_run_lease.py","checks/active_run_takeover_authorization.py","checks/check_workflow.py","checks/pack_asset_validation.py","checks/runtime_active_run_gate.py","checks/runtime_active_run_rules.py","checks/runtime_budget_dimensions.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/session_telemetry.py","examples/fixtures/runtime-active-run-lease-v4.json","schemas/active_run_fencing_allocation.schema.json","schemas/active_run_fencing_counter.schema.json","schemas/active_run_fencing_witness.schema.json","schemas/active_run_lease.schema.json","schemas/active_run_takeover_audit.schema.json","schemas/active_run_takeover_authorization.schema.json","schemas/active_run_takeover_consumption.schema.json","schemas/runtime_checkpoint.schema.json","schemas/runtime_checkpoint_v4.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement-queue/references/active-run-lease.md","templates/implx_checkpoint_v4.md","templates/zh-CN/implx_checkpoint_v4.md","tests/runtime_ledger_test_support.py","tests/test_active_run_lease.py","tests/test_active_run_schema.py","tests/test_active_run_takeover_authorization.py","tests/test_check_workflow.py","tests/test_pack_asset_validation.py","tests/test_review_runtime_schema.py","tests/test_runtime_gate_rules.py","tests/test_runtime_ledger_budget.py","tests/test_runtime_ledger_gate.py","tests/test_runtime_ledger_queue.py","tests/test_session_telemetry.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH189/product.md","specs/GH189/tech.md","specs/GH189/tasks.md"]}
-->

## Product Spec

见 `specs/GH189/product.md`。实现 B-001..B-019，不涉及 GH-160。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue startup | `skills/specrail-implement-queue/SKILL.md:11-46` | 枚举 worktrees/branches，但没有 active runtime owner。 | acquire 必须在 queue/lane 前。 |
| checkpoint path | `skills/specrail-implement-queue/SKILL.md:545-573` | 所有运行使用 `.specrail/runtime/current.json`。 | checkpoint 必须绑定 run/token，但 lease 不能放在 worktree-local 路径。 |
| runtime schema | `schemas/runtime_checkpoint.schema.json:41-74` | 有 `goal_id`/repo/tranche，无 run ID/fencing token。 | 增加不可串线绑定。 |
| runtime gate | `checks/runtime_ledger_gate.py:473-523` | 校验 checkpoint 字段，不读取 active lease。 | 写/恢复前需显式 lease evidence。 |
| goal budget rules | `checks/runtime_gate_rules.py:510-530` | v3 只检查可选 goal_id。 | run/token 只在第一个 lease-aware 版本 v4 成为强制字段；v1–v3 保持兼容。 |
| generic checkpoint templates | `templates/tranche_checkpoint.md:27`, `templates/zh-CN/tranche_checkpoint.md:16` | 两份模板实际都输出 `checkpoint_version: 2`。 | 必须按 v2 保持不变，不能在 manifest 排除模板时声称 v3。 |
| external role evidence precedent | `checks/github_review_evidence.py:236-272`, `checks/github_review_evidence.py:294-395` | maintainer role map 与一次性 round authorization 由 adapter 独立加载、规范化。 | takeover 必须复用“外部 role-mapped evidence，不信请求者自报 marker”的边界。 |
| U-16 split pressure | `tests/test_specrail_schema.py:1`, `skills/specrail-implement-queue/SKILL.md:1`, `checks/runtime_ledger_gate.py:1`, `checks/runtime_gate_rules.py:1`, `schemas/runtime_checkpoint.schema.json:1` | 写作时分别为 1092、799、788、785、778 行，均在 hard ceiling 之上或无安全增量空间。 | complete manifest 必须包含每个拆分目标，新增 active-run 合同不能继续堆入这些文件。 |

## 设计方案

### 1. 共享位置与身份

`checks/active_run_lease.py` 用参数数组调用 Git 获取 `--git-common-dir`，解析后要求位于
repo 控制范围内且无 symlink escape。lease 存放于：

```text
<git-common-dir>/specrail/active-run.lock/lease.json
```

目录的原子 `mkdir` 是 acquire primitive；所有 worktree 共享。repo identity 只从
canonical Git common dir 的稳定 `st_dev`/`st_ino` identity 计算 domain-separated SHA-256；
不得混入 worktree path、当前 branch/upstream、remote 名称或 URL。所有生产 gate 都从调用
repo 重新解析该 canonical path，以逐段 no-follow directory descriptor 打开并校验
lstat/fstat identity；同一 common dir 下不同 upstream 的 worktree 以及运行中 remote
增删改必须保持同一 `repo_id`，而无法保证稳定 device/inode identity 的平台返回
`unsupported`。输出只显示短 digest，不暴露 home path；CLI 不接受任意 lease 副本作为
安全证据。非 Git repo 或不支持原子目录创建的 FS 同样返回 `unsupported`。

### 2. closed lease schema

`active_run_lease.schema.json` 禁止未知字段并要求：

```text
version, repo_id, run_id, fencing_token,
owner_marker, created_at, renewed_at, expires_at,
clock_boot_id, monotonic_deadline_ns,
checkpoint_bound, checkpoint_digest,
takeover_audit_id, remote_operation, goal_id?
```

`remote_operation` 是 required nullable closed object；非 null 时包含
`operation_id, operation_kind, run_id, fencing_token, started_monotonic_ns,
deadline_monotonic_ns, remote_precondition_digest`，用于 §4 的同步远端调用 guard。

`fencing_token` 由三项 canonical 资产共同证明：

```text
<git-common-dir>/specrail/active-run-fencing-counter.json
<git-common-dir>/specrail/active-run-fencing-witness.json
<git-common-dir>/specrail/active-run-fencing-allocation.json
```

新增三个 closed schema：

- `active_run_fencing_counter.schema.json` 只允许
  `version, repo_id, last_allocated_token`；
- 不随正常 release 或 audit retention prune 删除的
  `active_run_fencing_witness.schema.json` 只允许
  `version, repo_id, high_water_token, last_allocation_digest,
  last_allocation_kind, last_allocation_outcome, updated_at`，其中 kind 闭集为
  `acquire | resume | takeover`，outcome 闭集为 `reserved | issued | skipped`。
  `high_water_token: 0` 的 genesis witness 是唯一条件分支：此时不存在可引用的
  allocation，`last_allocation_digest`/`last_allocation_kind`/`last_allocation_outcome`
  必须同时为 `null`；`high_water_token >= 1` 时三者必须同时非 null。schema 用条件
  分支关闭其他组合，`tests/test_active_run_schema.py` 必须覆盖 genesis 与非 genesis
  两个分支的 valid/invalid case；
- 临时但 durable 的 `active_run_fencing_allocation.schema.json` 只允许
  `version, repo_id, state, operation, previous_token, allocated_token,
  previous_counter_digest, previous_witness_digest, run_id, created_at`；
  `state` 只能为 `prepared`，且 `allocated_token = previous_token + 1`。

三项 parent 都从已持有的 canonical common-dir descriptor 逐段
`openat(..., O_NOFOLLOW|O_DIRECTORY)` 打开；final component 使用
`O_RDONLY|O_NOFOLLOW|O_CLOEXEC` 并 immediate `fstat` regular file，读取前后及 pathname
lstat/fstat 的 device+inode/type/size/mtime identity 必须稳定。fresh repo 只允许在
counter/witness/journal 全部缺失且不存在 lease/audit 时，于 mutex 内初始化 token 0 的
counter+genesis witness pair（witness 三个 `last_allocation_*` 字段为 `null`）；只缺一项
即 `corrupt`。无 allocation journal 时 counter
`last_allocated_token` 必须精确等于 witness `high_water_token`，且不小于 canonical
lease/retained audit token；任一单独回滚、symlink、非普通文件、越界 mode、identity swap
或内容/schema 损坏均 `unsafe/corrupt`。lease 的单独回滚按是否跨 allocation 边界区分：
witness `last_allocation_outcome` 为 `issued` 时，存在的 canonical lease 必须携带
`fencing_token == high_water_token`；held lease token 小于 high-water 只在最近 outcome 为
`reserved`/`skipped` 时合法，否则 inspect 判 `corrupt`。该 invariant 检测跨 allocation
边界的 lease 单独回滚（如恢复 resume/takeover 之前的旧 token lease），
`tests/test_active_run_lease.py` 必须覆盖 rollback 检出与 skipped 合法两侧。未跨
allocation 边界的同 token 字节级回滚（如恢复同一 allocation 的旧 renewal bytes 或复活
已 release 的同 token lease）没有 durable allocation 证据可区分，只由 mutation API 的
`expected_digest` compare 拦截并发误用；同一 OS principal 的该类字节级回滚与协调回滚
counter+witness 及相关资产同属 product non-goal。

每次 acquire/resume/takeover 都在 mutex 内执行同一 allocation transaction：

1. no-follow 读取并验证 counter+witness exact high-water 相等；
2. create-only 写 `prepared` allocation journal，fsync file+parent；该 durable reservation
   已永久 burn `allocated_token`；
3. dirfd-relative atomic replace counter 到新 token，fsync parent，再 replace witness 到
   同一 high-water 与 journal digest，fsync parent；
4. no-follow 重开并确认 counter/witness exact equality 与 journal binding 后，unlink
   journal 并 fsync parent；此后 token 才可用于 lease/takeover mutation。

任一步失败均不得返回 allocation success。若崩溃留下 schema-valid journal，下一次 modifying
allocation 必须先逐项匹配 old digests 与允许的 `{old/old, new/old, new/new}` durable state，
将两项推进到 journal 的新 token、把 outcome 记为 `skipped`、删除 journal并 fsync，然后以
`conflict`/reason=`allocation_recovered_token_skipped` 返回并要求 fresh retry；其它组合
`corrupt`。正常 journal close 先把 outcome 记为 `reserved`，后续 lease mutation 成功可
durable 改为 `issued`、失败可改为 `skipped`；`reserved` 本身已经 burned，terminal outcome
更新失败也不得授权复用。因此 normal release 后 lease 已删除、resume 后旧 lease 已替换、takeover audit
已 prune 或步骤失败时，witness 仍覆盖所有 acquire/resume/takeover 及 skipped token，下一次
allocation 必须严格大于 high-water。acquire 必须同时成功创建 lock dir、fsync 其 parent、
写 temp、fsync、rename 并 fsync lease parent；异常留下的无效目录被 inspect 判为 corrupt，
不自动删除。`checkpoint_bound` 是 required boolean；
当它为 `false` 时 `checkpoint_digest` 必须为 `null`，为 `true` 时必须匹配
`^sha256:[0-9a-f]{64}$`；schema 用条件分支关闭其他组合。
`takeover_audit_id` 是 required nullable field：普通 acquire/resume 为 `null`，takeover
生成的 lease 必须引用对应 audit record。`clock_boot_id` 是不暴露原值的 boot identity
digest，`monotonic_deadline_ns` 是同一 boot 内跨进程共享 clock domain 的绝对 deadline。
lease 不持久化 `status`：`free | held | stale | corrupt | unsafe | unsupported |
clock_unsafe | takeover_recovery_required | remote_operation_unknown` 全部由
`inspect_lease()` 从 canonical bytes、
clock 与 audit 状态派生。closed schema 遇到历史/未知 `status` 等额外字段必须判
`corrupt`，避免磁盘字段与派生状态形成两套真值。

### 3. 状态、转换与 compare-and-replace 串行化

纯函数 `inspect_lease()` 返回
`free | held | stale | corrupt | unsafe | unsupported | clock_unsafe |
takeover_recovery_required | remote_operation_unknown`。
所有修改 API（包括 acquire）先对
`<git-common-dir>/specrail/active-run.mutex` 取得跨进程、repo-wide 的独占 advisory
lock，再在同一临界区内完成 read → digest compare → state/token compare → temp write
→ fsync → atomic replace/remove。mutex 获取采用一次 non-blocking 尝试：竞争时返回
`busy` 并 fail closed，不重试、不 polling；文件描述符关闭或进程退出时由内核释放。
mutex 必须是以 no-follow 方式打开的稳定 regular file，路径同样拒绝 symlink/escape；
平台或文件系统不支持该原语时返回 `unsupported`。单独的 atomic rename 只保证文件
完整，不得被描述为 compare-and-swap。`expected_digest` 是上一次 inspect 返回的当前
lease bytes SHA-256；修改 API 取得 mutex 后必须重新读取并比较它。

任何 durable mutation 必须在返回成功前 fsync 受影响目录项：counter replace 后 fsync
counter parent；lock-directory `mkdir`/`rmdir` 后 fsync `specrail/`；lease replace/unlink
后 fsync `active-run.lock/`；audit create/replace/prune 后 fsync audit directory。
directory fsync 不可用或失败属于 `unsupported`/operation failure，不能 warning 后继续。

修改 API：

- `acquire(expected_free, run_id, owner_marker, ttl_seconds, checkpoint_digest=None)`；
  队列 startup 在写首个 checkpoint 之前取租，因此 `checkpoint_digest` 允许为显式
  `null`（sentinel `""` 非法）。首租写入 `checkpoint_digest: null` 与
  `checkpoint_bound: false`，schema 用 `["string","null"]` 表达；首次 checkpoint
  写入后必须立即 `renew(...)` 填入真实 digest 并置 `checkpoint_bound: true`。
  未绑定 lease 只允许执行首次 checkpoint bind，不得通过 resume、lane 或 remote-write
  gate，避免实现编造未经验证的占位值；
- `renew(expected_digest, run_id, owner_marker, token, checkpoint_digest, ttl_seconds)`；
  `ttl_seconds` 必须是正整数且不超过实现常量 `MAX_LEASE_TTL_SECONDS`。调用方在阻塞
  等待前以“声明 wait deadline + 固定 grace”计算 TTL；若所需期限超过硬上限，必须
  先 checkpoint/handoff 并停止，不能暗中截断或无限续租；
- `resume(expected_digest, run_id, old_owner_marker, token, checkpoint_digest,
  new_owner_marker, ttl_seconds)`：先验证当前 bound checkpoint+canonical lease，随后在
  mutex 内从 counter 分配更大的 fencing token、替换 owner marker，并写入
  `checkpoint_bound: false`/`checkpoint_digest: null` 的过渡 lease。旧 token 从该
  replace 起失效；新 session 只能写入携带新 token 的 v4 checkpoint 并立即 renew bind，
  在 bind 完成前不得 lane/remote-write。resume 任一步失败都从 canonical lease 和
  checkpoint 重读，不能回用旧 session identity；
- `release(expected_digest, run_id, owner_marker, token)`；
- `takeover(expected_stale_digest, new_run_id, new_owner_marker,
  authorization_ref, ttl_seconds)`：先按下节独立验证并消费一次性
  authorization，再 durable 分配更大 token；只有此后才能计算 new lease bytes/digest、
  create prepared journal，随后 durable replace 为新 `run_id`/`new_owner_marker`、
  `checkpoint_bound: false`、`checkpoint_digest: null` 的 lease，再 durable commit audit。
  takeover 成功返回后，新 owner 只可写入携带新 repo/run/token 的 v4 checkpoint并立即
  调用 `renew(...)` bind；bind 前 resume、lane 与 remote-write gate 均失败。旧
  checkpoint/owner/token 从 lease replace 起失效，任一步失败必须从 canonical
  counter/lease/audit 重读；已分配 token 永久 skipped，不得为重试复用。

acquire/resume/takeover 的 `ttl_seconds` 服从同一硬上限。PID 只可作为诊断 hint，
不参与授权或真值。
renew/release/resume/takeover 的竞争测试必须以 barrier 让两个操作携带同一旧 digest
并发进入，证明 mutex 内重新读取后只有一个 compare 可以成功，旧 fencing token 永远
不能覆盖 resume/takeover 后的新 lease。

#### 独立、一次性 takeover authorization

新增 `checks/active_run_takeover_authorization.py` 与 closed
`schemas/active_run_takeover_authorization.schema.json`。queue 外层在收到当前 conversation
的显式 human decision 后，向 host-owned human-gate adapter 请求授权并只得到 opaque
`authorization_ref`。adapter 的配置/maintainer role source 由 host 建立，takeover
caller 不能通过 CLI 提供 adapter、authorization file 或 role-map path；受支持平台上 core
用 ref 重新调用 adapter，adapter 返回规范化 evidence + role map。不具备这种独立 verifier
时 takeover 返回 `unsupported`，不得退回自报 JSON。lease CLI 不提供 `authorize`
subcommand，也不接受 raw `actor_marker`/`authorization_marker`/`reason`。adapter 返回的
artifact 闭集为：

```text
version, authorization_id, decision, repo_id,
expected_stale_lease_digest, old_run_id, old_fencing_token,
new_run_id, new_owner_marker, reason_digest,
actor, source, conversation_evidence_id, authorized_at, expires_at
```

`decision` 只能是 `takeover_once`；`reason_digest` 绑定未输出的原始理由，时间必须是
timezone-aware 且有效期不超过实现常量。freshness 不得只依赖 core 用本地 wall clock 比较
artifact 内 `authorized_at`/`expires_at`：有效期以 adapter 在 core 每次以 ref 重新调用时
基于自身可信时间源的即时裁决为准，adapter 必须拒绝解析已过期的 ref 而不是返回旧
artifact；core 的 timestamp 比较只是防御性二次检查，两者任一判过期都 fail closed。因此
本地 wall-clock 回拨不能复活已过期授权，artifact 不引入 boot/monotonic 字段，
`tests/test_active_run_takeover_authorization.py` 必须覆盖 adapter 端过期拒绝与
core 端二次检查两条路径。host-owned role map 必须把同一 actor 显式映射为
maintainer 并绑定可信 `source`/`conversation_evidence_id`；请求 takeover 的 new owner 不得
充当 authorizer。core 在 mutex 内重新调用 adapter，并逐字段匹配当前 canonical stale
lease 与请求的新 identity。caller 自带 artifact/role map、artifact 内自报 marker、
`implx auto` standing authorization、merge authorization 或 adapter 无法证明 role 时均
不能替代。

验证成功后，core 从已验证的 canonical common-dir fd 逐段
`openat("specrail", O_NOFOLLOW|O_DIRECTORY)` 与
`openat("active-run-authorizations", O_NOFOLLOW|O_DIRECTORY)`，持有最终 parent dirfd，并在
lookup/create 前后比较 pathname lstat 与 fd fstat 的 device+inode/type identity。预置或竞态
替换的 parent symlink、非 directory、identity swap 或 common-dir escape 均
`unsafe/corrupt`，不得读取或创建外部 target。

final basename 只能是 `<sha256(authorization_id)>.json`，并仅以该 parent dirfd 执行
`openat(O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600)`；immediate `fstat` 必须证明 regular
file、exact mode 与 single link。新增 closed
`schemas/active_run_takeover_consumption.schema.json`，只允许：

```text
version, authorization_id, authorization_id_sha256, authorization_digest,
repo_id, expected_stale_lease_digest, old_run_id, old_fencing_token,
new_run_id, new_owner_marker, reason_digest, actor, source,
conversation_evidence_id, consumed_at
```

schema 必须复核 basename hash、authorization artifact digest 与所有 old/new exact binding。
写入后 fsync file+parent；若 final 已存在，只能通过同一 no-follow parent dirfd 安全打开、
fstat regular file 并按该 closed schema 读取：exact match 仍返回 replay，malformed/错绑返回
conflict/corrupt，任何情况都不得覆盖。tombstone 不随 256 条 takeover audit retention prune；
消费后任一后续失败仍保持 consumed，重试必须取得新的 exact-bound authorization。测试必须
预置 parent/file symlink、在 lookup/create barrier 交换 parent identity，并用 common-dir 外
sentinel 证明没有外部读写。

#### durable takeover audit

审计目录固定为 `<git-common-dir>/specrail/active-run-audit/`；每次 inspect、create、
replace、prune 与 recovery 都必须从已验证的 canonical common-dir fd 逐段
`openat(..., O_NOFOLLOW|O_DIRECTORY)` 打开并持有 audit directory fd，校验路径
lstat/fstat device+inode identity。audit file 仅允许 20 位 token basename，以该 dirfd
执行 create-only open/rename/unlink；final component 使用 `O_NOFOLLOW` 并在读写前立即
`fstat` 确认为 regular file。预置或竞态置换的 directory/file symlink、identity mismatch、
escape 或非 regular file 一律 `unsafe/corrupt`，不得写入、替换或删除 common dir 外内容。
每个 takeover 使用按
20 位零填充新 fencing token 命名的 immutable identity，例如
`00000000000000000042.json`。新增 closed
`schemas/active_run_takeover_audit.schema.json`，record 要求：

```text
version, audit_id, state, repo_id,
old_run_id, new_run_id, old_fencing_token, new_fencing_token,
old_lease_digest, new_lease_digest,
authorization_id, authorization_digest, authorization_actor, reason_digest,
created_at, completed_at
```

`state` 只允许 `prepared | committed | aborted`；prepared 的 `completed_at` 为 null，
terminal state 必须有 timestamp。takeover 在同一 mutex 内按固定顺序执行：

1. 独立复核 exact-bound authorization 并 durable create consumption tombstone。
2. 通过 counter+witness+prepared allocation journal transaction durable 分配新 token；
   journal close 且 pair exact high-water 一致前不得计算或使用 token，从此即使后续失败也
   永久 burn。基于该 token 构造 new lease bytes，计算 `new_lease_digest`，此后 prepared
   takeover audit 才有完整输入。
3. 若 terminal record 已达 256，先按 fencing token 删除最旧 committed/aborted record
   并 fsync audit dir；任何 non-terminal record 先进入 recovery，不能被 prune。
4. 以新 token 命名，create-only 写 prepared record，fsync file、rename、fsync audit dir。
5. durable replace canonical lease，使其引用 `takeover_audit_id`，fsync lease parent。
6. replace audit 为 committed，fsync audit dir；只有此后才返回 takeover success。

若步骤 2 后、步骤 4 前失败，counter+witness high-water 中的新 token 是没有对应
audit/lease 的 `skipped_token`；normal release、resume replacement 与 audit prune 都不得删除
该 witness，下一次 allocation 必须从更大 token 开始。若 prepared takeover audit 已存在，
recovery 必须使用 record 的 exact new token/digest，不得再分配或回收 token。

崩溃留下 prepared record 时，inspect/gate 返回 `takeover_recovery_required` 并阻断所有
lease-protected 操作。显式 recovery 仍在 mutex 内：若 canonical lease digest/identity
等于 record 的 new side，则 durable commit；若仍等于 old side，则 durable abort；
其他组合判 corrupt 并等待人工处理。任何 audit 写入、prune、recovery 或 fsync 失败均
fail closed，不能以终端消息代替 durable record。

#### queue-facing CLI

`checks/active_run_lease.py` 同时提供 queue 唯一允许调用的机器接口：

```text
python3 checks/active_run_lease.py --repo <repo> --json inspect
python3 checks/active_run_lease.py --repo <repo> --json acquire --expected-free --run-id <id> --owner-marker <digest> --ttl-seconds <n>
python3 checks/active_run_lease.py --repo <repo> --json renew --expected-digest <sha256> --run-id <id> --owner-marker <digest> --token <n> --checkpoint-digest <sha256> --ttl-seconds <n>
python3 checks/active_run_lease.py --repo <repo> --json release --expected-digest <sha256> --run-id <id> --owner-marker <digest> --token <n>
python3 checks/active_run_lease.py --repo <repo> --json resume --expected-digest <sha256> --run-id <id> --old-owner-marker <digest> --new-owner-marker <digest> --token <n> --checkpoint-digest <sha256> --ttl-seconds <n>
python3 checks/active_run_lease.py --repo <repo> --json takeover --expected-stale-digest <sha256> --new-run-id <id> --new-owner-marker <digest> --authorization-ref <opaque-id> --ttl-seconds <n>
python3 checks/active_run_lease.py --repo <repo> --json recover --audit-id <20-digit-token>
python3 checks/active_run_lease.py --repo <repo> --json begin-remote --expected-digest <sha256> --run-id <id> --owner-marker <digest> --token <n> --operation-id <id> --operation-kind <push|comment|label|pr_write|issue_write> --remote-precondition-digest <sha256> --ttl-seconds <n>
python3 checks/active_run_lease.py --repo <repo> --json end-remote --expected-digest <sha256> --run-id <id> --owner-marker <digest> --token <n> --operation-id <id> --provider-result <succeeded|definitive_failure>
```

当调用包含 `--json` 时，包括 argparse/closed-schema failure 在内都必须向 stdout 恰好输出
一个 `additionalProperties: false` envelope（stderr 不承载机器字段）。base keys 始终为
`version, operation, ok, state, reason_code, repo_id, lease_digest`：

- `operation` 是上述 subcommand enum；只有 subcommand 缺失/未知、无法解析时为 JSON null。
- `repo_id` 成功解析 canonical common-dir identity 后为 digest；参数错误发生在解析前，
  非 Git repo 或平台无法形成 identity 的 `unsupported` 时为 null。
- `lease_digest` 只有在 no-follow 安全读取 exact canonical lease bytes 后为 digest；
  `free`、路径 unsafe/无法读取、参数/schema error 或 identity 未形成时为 null。禁止
  `""`、`"unknown"`、全零 digest 等 sentinel。
- `ok` 仅在 exit 0 时为 true。仅在适用时增加 closed 集合内的
  `run_id, fencing_token, owner_marker, expires_at, checkpoint_bound,
  takeover_audit_id, remote_operation_id, remote_operation_kind,
  remote_operation_deadline_monotonic_ns`。三个 `remote_operation_*` 摘要字段
  只能同时出现且同时非 null：当且仅当安全读取的 canonical lease 携带非 null
  `remote_operation`（含 `remote_operation_unknown` 状态）时输出，其余情况整体缺省，
  不允许 null 占位。

成功（exit 0）的 mutation 必须输出以下固定 state/reason 映射，不允许实现自造字符串：

| Operation (exit 0) | `state` | `reason_code` |
| --- | --- | --- |
| acquire | `held` | `acquired` |
| renew | `held` | `renewed` |
| release | `free` | `released` |
| resume | `held` | `resumed` |
| takeover | `held` | `taken_over` |
| recover (commit) | `held` | `recovery_committed` |
| recover (abort) | `stale` | `recovery_aborted` |
| begin-remote | `held` | `remote_operation_begun` |
| end-remote | `held` | `remote_operation_cleared` |

inspect `free` 输出 `state:"free"`/`reason_code:"free"`。退出码表中 "0=mutation 成功或
inspect `free`" 优先于 state→exit 映射：recover abort 成功时 exit 0、state `stale`，
后续 inspect 才按 `stale`/3 报告。T3 的 closed-schema 测试必须对每个成功 operation
断言上表映射。同一 state/reason 必须产生唯一 nullability 组合；例如 inspect `free` 为
`operation:"inspect", repo_id:<digest>, lease_digest:null`，identity `unsupported` 与
argument error 都是两项 identity null，但各有不同 state/reason/exit。未知 base/conditional
字段一律 schema error。输出不含绝对 common-dir/home path、PID、environment、session
正文、authorization/role-map 内容或 reason 原文。所有 subcommand 禁止 human-output
parsing 与 ad hoc inline import。

稳定退出码为：`0`=mutation 成功或 inspect `free`；`2`=`held | busy | conflict`；
`3`=`stale | takeover_recovery_required | remote_operation_unknown`；
`4`=`corrupt | unsafe | clock_unsafe`；
`5`=`unsupported`；`64`=CLI 参数/schema 错误；`70`=未分类 I/O/内部失败。mutation
precondition mismatch 必须返回 `conflict`/2；不得把 nonzero 状态降级为 warning。

非成功路径的 `reason_code` 同样是闭集，实现不得自造字符串；每个 nonzero 结果只允许
下表 state/exit/reason 组合（`argument_error`/`internal_error` 是 envelope 专用 state，
不属于 `inspect_lease()` 派生集合）：

| `state` | exit | 允许的 `reason_code` 闭集 |
| --- | --- | --- |
| `held` | 2 | `held` |
| `busy` | 2 | `mutex_busy` |
| `conflict` | 2 | `precondition_mismatch` \| `allocation_recovered_token_skipped` |
| `stale` | 3 | `expired` \| `boot_epoch_changed` |
| `takeover_recovery_required` | 3 | `takeover_recovery_required` |
| `remote_operation_unknown` | 3 | `remote_operation_unknown` |
| `corrupt` | 4 | `corrupt_asset` |
| `unsafe` | 4 | `unsafe_path` |
| `clock_unsafe` | 4 | `clock_unsafe` |
| `unsupported` | 5 | `unsupported_platform` |
| `argument_error` | 64 | `argument_error` \| `schema_error` |
| `internal_error` | 70 | `io_error` \| `internal_error` |

CLI tests 对每个 operation、free/unsupported/unsafe 与 parser/schema error 同时断言
closed JSON、nullability 与退出码，并对上表逐组合断言 nonzero state/reason/exit 闭集，
任何表外 reason_code 都是 schema error；queue 只消费该接口。

#### cross-process expiry evidence

acquire/renew/resume/takeover 都从受支持的平台 adapter 读取稳定 boot identity 与同一
boot 内跨进程可比较的 monotonic clock，写入 boot digest 和绝对 deadline。inspect 在
boot digest 相同时只用 monotonic deadline 判断 held/stale；UTC timestamps 仅用于有界
诊断，wall-clock 前跳/回拨不能单独改变状态。boot digest 变化证明旧 owner 不可能仍在
原 boot 运行，因此返回 reason=`boot_epoch_changed` 的 `stale`，但仍要求显式授权
takeover。boot identity、跨进程 monotonic clock 或其一致性无法建立时返回
`unsupported/clock_unsafe` 并阻断，不得回退到 wall clock、PID 或进程存在性。

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
反向改变 checkpoint，绑定存在稳定点。`runtime_ledger_gate.py` 从 `--repo` 对应 Git
common dir 自行推导 canonical active lease，逐段 no-follow 打开并要求 path/lstat/fstat
identity、已绑定 lease、checkpoint identity 与 digest 全部一致；它本身只读，不提供
可将保存副本当成生产安全证据的任意 `--lease` override。任一侧被替换、路径非 canonical、
audit 未 committed 或 lease 尚未完成首次绑定都必须 fail closed。

queue 在 Startup acquire；在 spawn lane 与 checkpoint replace 前 renew/validate。
checkpoint replace 成功但 lease bind 失败时不得宣称 checkpoint 可 resume，下一次 gate
会因 digest mismatch 阻断。该 renew/validate 是 admission 判定，本 issue 不声称它与随后
的 checkpoint replace 或 lane spawn 构成单一 serialized transaction：若 admission 之后
owner 因合法 resume/takeover 失效，旧 owner 的 checkpoint 覆盖只会造成 canonical lease
`checkpoint_digest` mismatch 并对所有后续 gate fail closed，新 owner 仍持有效 lease，可
重写自己的 v4 checkpoint 并 renew 重新 bind 恢复；携带已失效 token 的 lane 则在其每个
checkpoint/lane/remote-write 边界被 fencing 阻断，不能产生 durable 或远端效果。跨这些
本地边界的原子事务超出文件型 lease 的诚实能力，属于后续设计。

PR/issue/comment/label/push 等 provider mutation 采用持久 remote-operation guard，而不是把一次
preflight 描述为 provider-side fencing。`operation_kind` 闭集为
`push | comment | label | pr_write | issue_write`；auto queue 合并后 closure audit 的
issue close/update 属于 `issue_write`，不得标记为 `pr_write` 或绕过该 guard：

1. 调用 `begin-remote`，在 mutex 内 renew/validate 当前 bound lease，并 durable replace
   为含 exact repo/run/owner/token、唯一 operation ID、operation kind、provider
   precondition digest 与 bounded deadline 的 `remote_operation`；返回新 lease digest。
2. 只有 begin 成功后才以同步、带 client timeout 的 provider API/CLI 发起一次写入；同一
   run 也不得并发第二个 remote operation。
3. 只有 provider 返回确定的 success 或 definitive failure 后，原 owner 才用 begin 返回的
   digest 与 identity 调用 `end-remote` compare-and-clear。timeout、transport interruption、
   cancellation、进程消失或响应语义不确定时不得 clear。
4. 任一 non-null guard 都阻断 takeover/resume/release；TTL 过期不改变该规则。
   inspect 返回 `remote_operation_unknown`/3 并保留有界 operation ID/kind/deadline 摘要。
   本 issue 不提供 force-clear；需要 provider-specific reconciliation/remote fencing adapter
   的后续设计。因而本合同只保证本地调用 admission 与 takeover exclusion，不声称已发出的
   GitHub 请求会理解或执行本地 fencing token。

resume 的安全授权明确只有 checkpoint+canonical lease 两方。验证旧 binding 后必须调用
上述 `resume(...)` 轮换 token/owner，再写入新 token 的 checkpoint 并重新 bind；继续使用
旧 token 的 gate/renew 即使拿到最新 digest 也必须失败。该 fencing 边界的诚实范围是
cooperative stale session：rotation 后的新 token/owner marker 存放在同一 OS principal
可读的 canonical lease 中，而 `renew` 验证的是 caller 提交的 identity 副本，因此一个
主动重新 inspect 并整套复制新 marker/token/digest 的对抗性本地进程无法被文件型 lease
区分——同一 principal 本就可以直接改写 lease bytes。B-007 的保证据此限定为：只持有
rotation 前 identity 的旧 session（跨 compaction/session 恢复的正常情形）必然在 renew
与所有 boundary gate 失败；防御同 principal 的主动 identity 复制需要 uncopyable
host/process capability，超出本 issue 的威胁模型，留待后续设计。checkpoint 可保留 `goal_id`，调用方
也可在恢复时独立调用 live Goal 查询来确认 Goal ID/status，以恢复目标和预算上下文；
但现有 Goal API 没有独立承载 repo/run/token 的合同，因此 Goal evidence 不参与 fencing
判断，也不得宣称 checkpoint+Goal+lease 三方安全绑定。没有 Goal 能力或 live Goal
evidence 时，只报告 Goal continuity 未验证，不得削弱 checkpoint+lease gate。

#### checkpoint 版本兼容

| Version | Schema/gate | Lease-aware 权限 |
| --- | --- | --- |
| 1–3 | 继续接受，保留现有 fixture 与离线历史校验；v3 budget/telemetry 语义不变 | 不得用于受 lease 保护的 resume、lane 或 remote write；必须开始新 run 并生成 v4 |
| 4 | 继承 v3 budget/telemetry 规则并强制 `run_lease` | 通过 canonical common-dir lease 的 identity + 单向 checkpoint digest 校验后允许；跨 session resume 先轮换 token |
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

通用 `templates/tranche_checkpoint.md` 与 `templates/zh-CN/tranche_checkpoint.md`
继续使用当前实际的非 lease-aware v2 shape，服务不会 acquire canonical lease 的可选长运行，不在
本 issue 修改。新增 queue-only `templates/implx_checkpoint_v4.md` 与
`templates/zh-CN/implx_checkpoint_v4.md`，只有 startup acquire 成功并取得 repo/run/token
后才可选择；其 JSON 示例强制 v4 `run_lease`，不能作为普通运行的默认模板。

普通 `check_workflow.py` 只校验 checker 与 fencing-counter/fencing-witness/
fencing-allocation/lease/takeover-audit/takeover-authorization/takeover-consumption 七个
active-run closed schema 及 `runtime_checkpoint_v4.schema.json` 是 pack assets，不读取
common dir counter/witness/journal/lease/audit/authorization consumption/remote-operation
状态。`implx_checkpoint_v4.md` 必须同时注册进 `checks/pack_asset_validation.py` 的
`SPEC_TEMPLATE_FILES` deterministic ownership，使 base 与 `templates/zh-CN` localized
parity、缺失/不可读检测覆盖两个 queue-only checkpoint templates；缺任一份或 parity
失败时 `check_workflow.py` 必须失败。`tests/test_active_run_schema.py` 独占七个 active-run schema 的 valid/malformed/
unknown-field/conditional binding 测试；`tests/test_pack_asset_validation.py` 对每个 schema/template
路径和 owner 建立 exact 集合断言（含 `SPEC_TEMPLATE_FILES` 中的
`implx_checkpoint_v4.md`），任何漏注册或错误 owner 均失败。

### 5. 无 polling 生命周期

不启动 heartbeat thread。owner 在已有关键状态转换前续租；长阻塞等待前用 required
`ttl_seconds` 将 expiry 覆盖已声明 deadline + grace，返回后立即 renew。等待超过
`MAX_LEASE_TTL_SECONDS` 时先 checkpoint/handoff，不允许扩大上限。held lease 或
mutation mutex busy 都不触发轮询；第二 run 立即报告并停止。
`unsupported`、`clock_unsafe` 与 `takeover_recovery_required` 在 plain `implx` review
和 `implx auto` 中都阻断 startup/lane/checkpoint/remote write；只有不产生这些副作用的
inspect 与 pack check 可继续。`remote_operation_unknown` 还必须阻断 takeover/resume/
release 与新的 remote write，且没有 TTL 驱动的本地 force-clear。

### 6. U-16 hard-ceiling 拆分计划

实现不得把 active-run 内容继续堆入已到 hard ceiling 的文件。以下拆分路径已 search-first
确认不存在，并纳入 complete manifest；每项由对应 owner 在写新增行为前完成：

| 当前文件与写作时行数 | 拆分目标 | 强制边界 |
| --- | --- | --- |
| `tests/test_specrail_schema.py` (1092) | `tests/test_review_runtime_schema.py` | 迁出现有 review-result/runtime-checkpoint/content-binding schema 区段，使原文件与新文件都 `<800`；active-run 七 schema 新断言只能写入 `tests/test_active_run_schema.py`。 |
| `skills/specrail-implement-queue/SKILL.md` (799) | `skills/specrail-implement-queue/references/active-run-lease.md` | SKILL 只保留 startup/stop-boundary 摘要与“lease-protected queue 必须先读取该 reference”的路由；CLI、renew、resume、takeover、remote guard 过程写入 reference，二者都 `<800`。 |
| `checks/runtime_ledger_gate.py` (788) | `checks/runtime_active_run_gate.py` | v4 canonical lease/checkpoint binding、no-follow load 与 boundary validation 进入新模块；原 gate 只保留稳定 facade/import 与组合 decision。 |
| `checks/runtime_gate_rules.py` (785) | `checks/runtime_active_run_rules.py` | active-run state/reason、v4 `run_lease` 与 fencing rule table/normalizer 进入新模块；原 rules 不复制第二份常量。 |
| `schemas/runtime_checkpoint.schema.json` (778) | `schemas/runtime_checkpoint_v4.schema.json` | v4-only `run_lease` closed conditional 与字段定义进入新 schema；主 schema 以同目录 local `$ref` 组合并保留 v1–v3，不内联复制。 |

`SP189-T5` 必须从 manifest 动态枚举所有 planned text assets，在 exact implementation head 对每个
现存路径执行 `wc -l` 并断言结果 `<800`；同时明确断言上述五个 split target 存在。缺文件、任一 source 或
split target 达到 800 行、SKILL 未路由读取 reference、schema `$ref`/pack ownership 不可解析
均阻断，不允许 grandfather 既有 1092 行文件或把新增测试留在原文件。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 | remote-independent common-dir identity + atomic acquire/mutation mutex | `python3 -m pytest -q tests/test_active_run_lease.py -k "worktree or upstream or remote_change or concurrent or mutex"` |
| B-003 B-004 B-010 B-015 | fencing、bounded TTL、serialized compare-and-replace、remote-operation begin/end guard | `python3 -m pytest -q tests/test_active_run_lease.py -k "fencing or ttl or replace_race or fsync or remote_operation or provider_timeout"` |
| B-005 B-006 B-009 B-016 | stale/takeover unbound rebind、external exact authorization、no-follow consumption/audit、boot/monotonic evidence | `python3 -m pytest -q tests/test_active_run_lease.py tests/test_active_run_takeover_authorization.py tests/test_active_run_schema.py -k "stale or takeover or authorization or replay or role_map or consumption or parent_swap or audit or clock or boot"` |
| B-007 | canonical lease + 单向 digest resume binding、token rotation（含 Goal 非安全边界与首租阻断） | `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_active_run_lease.py -k "lease or canonical or resume or goal or first_acquire or digest"` |
| B-008 B-011 B-014 B-017 | unsafe/corrupt/failure/unsupported、counter+witness+journal dirfd identity/rollback、allocation recovery、allocate-before-audit/skipped token | `python3 -m pytest -q tests/test_active_run_lease.py tests/test_active_run_schema.py tests/test_runtime_ledger_gate.py -k "unsafe or corrupt or failure or unsupported or recovery or counter or witness or allocation_journal or normal_release or audit_prune or skipped_token or allocate_before_audit"` |
| B-012 B-013 B-018 | pure pack/inspect + queue-facing closed JSON/nullability/exit contract | `python3 -m pytest -q tests/test_check_workflow.py tests/test_active_run_lease.py -k "workflow or inspect or cli or exit_code or nullability or argument_error or redaction"` |
| B-019 | generic v2 compatibility + queue-only v4 template selection | `python3 -m pytest -q tests/test_specrail_schema.py tests/test_review_runtime_schema.py tests/test_runtime_ledger_queue.py -k "tranche_template_v2 or implx_template_v4 or version"` |

## 数据流

```text
git common dir → canonical no-follow lease → mutation mutex → inspect/acquire
      allocation journal → counter + non-prunable high-water witness → token
      resume → rotated fencing token → checkpoint rebind
      takeover authorization → no-follow closed one-time consumption
               → durable counter+witness allocation
               → prepared audit → new unbound lease → committed audit
               → new-owner v4 checkpoint → renew bind
      checkpoint identity → lease checkpoint_digest → runtime gate
      optional live Goal evidence → continuity/budget context only
      lane/checkpoint ← bounded renew/validate
      remote write ← begin-remote guard → synchronous provider call
                   → definitive result → end-remote
                   → ambiguous result → remote_operation_unknown (no takeover)
```

仅 lease API 写 common-dir；gate、inspect 与 pack check 均只读。

## 备选方案

- worktree-local `.specrail/runtime`: 无法跨 worktree 排他，拒绝。
- PID lock: PID 可复用且跨 session 不稳定，拒绝。
- GitHub label: 有网络竞态和外部写副作用，拒绝。
- 自动 stale takeover: 会覆盖暂停中的合法 run，拒绝。
- 只在远端写前做 lease preflight：请求卡住后 lease 可过期并被 takeover，而旧请求仍可能
  在 GitHub 完成，拒绝；本 issue 选择持久 guard 阻断 takeover，不伪造 provider fencing。
- 由 takeover 请求者传 raw actor/marker/reason：无法证明人工授权且可重放，拒绝；只消费
  独立 adapter + maintainer role map 的 exact `takeover_once` evidence。

## 风险

- Security: canonical no-follow 路径、remote-independent repo identity、owner 输出、
  clock evidence、counter/witness/allocation/audit/consumption dirfd identity、一次性外部
  授权与原子文件操作
  fail closed；不记录 session 正文。
- Compatibility: v1–v3 保留离线校验但不能授权 lease-aware resume；通用模板保持实际 v2，
  成功 acquire 的 implx 新 run 使用 queue-only v4 模板。
- Performance: 每个关键写边界一次小文件验证，无轮询。
- Maintenance: lease 与 checkpoint 两方 binding 必须共享 validator；Goal 不进入安全边界。
  U-16 拆分后原 facade、split module/schema/reference 只能有一份规则真值，pack/hash/line-count
  gate 防止重新内联漂移。
  remote operation timeout 可能留下无法自动清除的 guard，这是不具备 provider-side fencing
  时保守换取安全的明确 liveness 成本。

## 测试计划

- [ ] Unit: 派生状态（lease schema 不持久化 `status`）、counter/witness/allocation/
      lease/audit/authorization/consumption 七个 active-run closed schema、TTL 上限、
      mutex、directory fsync、原子失败、boot/monotonic clock、canonical no-follow 路径、
      remote-independent repo identity、resume/takeover rotation+rebind、counter/witness/journal
      symlink/identity/single-file rollback、normal-release/audit-prune high-water retention、
      prepared allocation recovery、token-before-audit/skipped token、audit
      symlink/identity/recovery/retention、authorization consumption parent/file symlink 与
      identity swap、closed tombstone/replay、exact one-time authorization、CLI
      JSON/nullability/exit/redaction、remote-operation guard/ambiguous response。
- [ ] Integration: 不同 upstream 的两 worktree 并发、运行中 remote 变化、serialized
      replace race、稳定的单向 digest binding、v1–v4 compatibility、通用 v2 与 queue-only
      v4 template 选择、queue boundary fixture。
- [ ] Regression: full pytest、all-specs、depth/diff/pack checks，以及 manifest 动态 `<800`
      行 gate；1092 与 778–799 行五个源文件全部完成指定拆分。
- [ ] Forward-use: 两个真实临时 worktree 竞争、resume、stale authorized takeover。

## 回滚方案

回滚 checker/schema/queue/wiring/tests/docs/lock 的同一实现提交。保留的 common-dir lease
可由原 owner 显式释放或人工归档；不得在回滚脚本中递归删除 `.git/specrail`。
