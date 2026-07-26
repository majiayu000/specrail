# Task Plan

## Linked Issue

GH-189

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP189-T1` Owner: lease-core | Depends on: approved spec | Done when: `repo_id` 只依赖 canonical common-dir 稳定 identity，跨 upstream/remote 配置变化不变；closed lease 不持久化 `status` 并含 nullable `remote_operation`；counter parent/file 均从 canonical common-dir fd 逐段 no-follow 打开并做 regular/lstat-fstat identity 检查，counter 小于 lease/audit witness、symlink/非普通文件/竞态替换均 fail closed；acquire/resume/takeover 先 durable allocation，takeover 再计算 new digest/写 prepared audit，后续失败只留下永不复用的 skipped token；repo-wide non-blocking mutex、bounded TTL、boot+monotonic expiry、所有 parent fsync、barrier compare race、audit dirfd/recovery/256 retention 与 begin/end remote guard core 全有测试 | Verify: `python3 -m pytest -q tests/test_active_run_lease.py -k "identity or upstream or remote_change or status or mutex or counter or rollback or skipped_token or allocate_before_audit or takeover or audit or symlink or recovery or retention or clock or remote_operation"` | Covers: B-001 B-002 B-004 B-006 B-008 B-009 B-010 B-011 B-014 B-015 B-017 | 新增 lease/counter/audit core 与三个对应 closed schemas，不接 queue。
- [ ] `SP189-T2` Owner: runtime-binding | Depends on: SP189-T1 | Done when: `checkpoint_version: 4` 是唯一强制 `run_lease` repo/run/token 的 lease-aware 版本，lease 单向保存完整 checkpoint bytes digest，稳定绑定与任一侧篡改均有测试；首租/resume/takeover 过渡 lease 都是新 owner/new token 的 unbound state，写入同 identity v4 checkpoint 并立即 bind 前不能通过 resume/lane/remote-write；gate 只从 `--repo` 推导 canonical lease；Goal 只作连续性/预算上下文；v1–v3 fixture 继续离线兼容，两个未修改通用 tranche template 明确保持实际 `checkpoint_version: 2`，5+ 拒绝；只有 startup acquire 成功后使用 queue-only v4 templates | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_gate_rules.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_queue.py tests/test_specrail_schema.py tests/test_active_run_lease.py -k "lease or canonical or resume or takeover or rebind or goal or first_acquire or digest or version or budget or template" && rg -n '\"checkpoint_version\": 2' templates/tranche_checkpoint.md templates/zh-CN/tranche_checkpoint.md && rg -n run_lease templates/implx_checkpoint_v4.md templates/zh-CN/implx_checkpoint_v4.md && ! rg -n run_lease templates/tranche_checkpoint.md templates/zh-CN/tranche_checkpoint.md` | Covers: B-003 B-004 B-006 B-007 B-008 B-011 B-019 | 更新 schema/rules/gate、v4 fixture/builder、版本接受测试和 queue-only v4 templates；通用模板与已声明 v1–v3 compatibility fixtures保持不变。
- [ ] `SP189-T3` Owner: queue-integration | Depends on: SP189-T1 SP189-T2 SP189-T6 | Done when: queue 只通过 `python3 checks/active_run_lease.py --repo <repo> --json <operation>` 调用 inspect/acquire/renew/release/resume/takeover/recover/begin-remote/end-remote；base envelope 七键始终出现，operation/repo_id/lease_digest 按 spec 使用 JSON null，free/unsupported/unsafe/argument/schema error 的 closed JSON/nullability/退出码 0/2/3/4/5/64/70 全有测试；takeover 只传 opaque authorization ref，caller 不能注入 authorization/role-map path；每次 provider write 必须 begin guard 后同步执行，只有确定响应才 end，timeout/ambiguous 保留 `remote_operation_unknown` 并永久阻断 takeover，不能声称 provider-side fencing；startup v4、bounded TTL、new-owner bind、owner-only release、无 polling 与 review/auto fail-closed 语义保持 | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_active_run_takeover_authorization.py tests/test_runtime_ledger_gate.py -k "cli or json or nullability or argument_error or exit_code or redaction or queue or boundary or begin_remote or end_remote or provider_timeout or release or ttl or unsupported or recovery or takeover"` | Covers: B-003 B-004 B-005 B-006 B-007 B-010 B-011 B-013 B-014 B-015 B-016 B-018 | 更新 queue；若 GH-174 已合并则放入其 canonical runtime phase。
- [ ] `SP189-T4` Owner: pack-docs | Depends on: SP189-T3 | Done when: checker/schema required assets（在 `checks/pack_asset_validation.py` 注册 counter/lease/takeover-audit/takeover-authorization 四个 active-run schemas，并更新 ownership 断言）、AGENT_USAGE/CHANGELOG 与 Skill hash 同步，普通 workflow 不读取活动 counter/lease/audit/auth/remote-operation 状态 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py tests/test_pack_asset_validation.py tests/test_specrail_schema.py -k "active_run or required or ownership"` | Covers: B-012 B-013 B-016 B-017 B-018 | 完成 pack wiring。
- [ ] `SP189-T6` Owner: takeover-authorization | Depends on: SP189-T1 | Done when: 新 adapter/schema 以 host-configured verifier 解析 opaque authorization ref，caller 不能选择 adapter 或注入 authorization/role-map 文件；adapter 只接受 current-conversation evidence + maintainer role map，exact 绑定 authorization ID/decision `takeover_once`/repo/old digest-run-token/new run-owner/reason digest/actor/source/conversation evidence/freshness；adapter unavailable、请求者自报 marker、错 role、错绑、过期、auto/merge auth 替代全部失败；core 在 canonical dirfd 下 create-only durable consumption tombstone，ID 重放失败，takeover 后续失败仍 consumed 且需新授权 | Verify: `python3 -m pytest -q tests/test_active_run_takeover_authorization.py tests/test_active_run_lease.py -k "authorization or maintainer or role_map or exact_binding or unavailable or expired or replay or consumption or takeover_once"` | Covers: B-005 B-006 B-016 | 新增 host-owned external authorization adapter/schema/tests；不得从 lease CLI 生成授权。

## 并行拆分

- `T1 → (T2 ∥ T6) → T3 → T4`：T2 独占 runtime checkpoint/gate/template 文件，T6
  独占 takeover authorization adapter/schema/tests；两者均不得修改 T1 的 dirty core，
  T3 在两条接口固定后串行接 queue。
- 只读 reviewer 可并行，不得修改 manifest 文件。

## 验证

- [ ] `SP189-T5` Owner: verification-owner | Depends on: SP189-T1 SP189-T2 SP189-T3 SP189-T4 SP189-T6 | Done when: focused/full/pack/depth/diff/hash 全绿；不同 upstream 的 worktrees/进程及 remote 变化证明唯一 owner；counter/lease/audit/auth canonical no-follow identity、counter rollback 与 token-before-audit/skipped gap、resume/takeover rotation+unbound rebind、external exact one-time authorization、CLI closed JSON/nullability/exit/redaction、通用实际 v2 与 queue-only v4 template 选择、remote begin/end 与 ambiguous-call takeover exclusion、replace race、fsync failure、prepared recovery/retention、monotonic expiry、review+auto unsupported、bounded TTL 全有 exact-head evidence；无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_active_run_takeover_authorization.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py tests/test_pack_asset_validation.py tests/test_specrail_schema.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH189 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 | exact-head 交付证据。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 ready_to_implement 前不得实现。
- 不得自动 takeover/kill/删除他人 lease，remote write 仍遵守当前会话授权；任何
  `remote_operation_unknown` 都没有 force-clear/takeover escape hatch。
- manifest 完整列出 v4 hard-coded consumers、builder/acceptance tests 与新增 v4 fixture；
  通用 tranche templates 保持实际 v2，已有 v1–v3 fixtures 按兼容合同保持不变；queue-only v4
  templates 只有成功 acquire 后才能使用，不含 GH-160。
