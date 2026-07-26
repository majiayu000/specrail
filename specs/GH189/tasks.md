# Task Plan

## Linked Issue

GH-189

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP189-T1` Owner: lease-core | Depends on: approved spec | Done when: `repo_id` 只依赖 canonical common-dir 的稳定 device/inode identity，跨不同 branch upstream 与运行中 remote 配置变化不变；closed lease schema 不持久化 `status`，inspect 状态完全派生；required `checkpoint_bound`/clock/audit link、repo-wide non-blocking mutation mutex、inspect/acquire/renew/release/resume/takeover、required bounded TTL、跨进程 boot+monotonic expiry、所有 rename/mkdir/remove 后 parent fsync 与原子失败全部有测试；barrier race 证明 renew/release/resume/takeover 只有一个旧 digest compare 成功；takeover journal 按 prepared→new-owner unbound lease→committed durable ordering，audit 全程 canonical dirfd/no-follow/lstat-fstat identity，symlink/identity swap fail closed，prepared recovery 与最多 256 条 retention 可判定 | Verify: `python3 -m pytest -q tests/test_active_run_lease.py -k "identity or upstream or remote_change or status or mutex or takeover or audit or symlink or recovery or retention or clock"` | Covers: B-001 B-002 B-004 B-005 B-006 B-008 B-009 B-010 B-011 B-013 B-014 | 新增 lease 核心和 `schemas/active_run_takeover_audit.schema.json`，不接 queue。
- [ ] `SP189-T2` Owner: runtime-binding | Depends on: SP189-T1 | Done when: `checkpoint_version: 4` 是唯一强制 `run_lease` repo/run/token 的 lease-aware 版本，lease 单向保存完整 checkpoint bytes digest，稳定绑定与任一侧篡改均有测试；首租/跨 session resume/authorized takeover 过渡 lease 均为新 owner/new token、`checkpoint_bound: false` + null digest，新 owner 写入相同 identity 的 v4 checkpoint 并立即 bind 前不能通过 resume/lane/remote-write，旧 token 即使读取最新 digest 仍失败；gate 只从 `--repo` 推导并 no-follow 打开 canonical common-dir lease，保存副本/symlink/非 canonical path 全拒绝；Goal 明确只作连续性/预算上下文，不参与安全授权；v1–v3 fixture 与两个通用 tranche template 继续为非 lease compatibility shape，5+ 拒绝；只有 startup acquire 成功后使用新增 queue-only `templates/implx_checkpoint_v4.md`/`templates/zh-CN/implx_checkpoint_v4.md` | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_gate_rules.py tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_queue.py tests/test_specrail_schema.py tests/test_active_run_lease.py -k "lease or canonical or resume or takeover or rebind or goal or first_acquire or digest or version or budget or template" && rg -n run_lease templates/implx_checkpoint_v4.md templates/zh-CN/implx_checkpoint_v4.md && ! rg -n run_lease templates/tranche_checkpoint.md templates/zh-CN/tranche_checkpoint.md` | Covers: B-003 B-004 B-006 B-007 B-008 B-011 | 更新 schema/rules/gate、v4 fixture/builder、版本接受测试和 queue-only v4 templates；通用模板与已声明 v1–v3 compatibility fixtures 保持不变。
- [ ] `SP189-T3` Owner: queue-integration | Depends on: SP189-T1 SP189-T2 | Done when: queue 只通过 `python3 checks/active_run_lease.py --repo <repo> --json <operation>` 调用 inspect/acquire/renew/release/resume/takeover/recover，所有 operation 的参数、closed JSON、敏感字段裁剪及稳定退出码 0/2/3/4/5/64/70 有测试且 nonzero 不降级为 warning；startup acquire 后选择 queue-only v4 template，lane/checkpoint/所有 remote write 前以 required bounded TTL renew/validate，takeover success 后按新 owner v4 checkpoint→renew bind 顺序执行，等待超过硬上限先 checkpoint/handoff，正常完成/中断只在 mutation mutex 内释放自己的 lease，held/busy 状态无 polling；`unsupported`/`clock_unsafe`/`takeover_recovery_required` 在 plain review 与 auto 中都阻断，只有纯 inspect/pack check 可继续 | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_runtime_ledger_gate.py -k "cli or json or exit_code or redaction or queue or boundary or release or ttl or mutex or unsupported or recovery or takeover_rebind"` | Covers: B-003 B-004 B-006 B-007 B-010 B-011 B-013 B-014 | 更新 queue；若 GH-174 已合并则放入其 canonical runtime phase。
- [ ] `SP189-T4` Owner: pack-docs | Depends on: SP189-T3 | Done when: checker/schema required assets（含在 `checks/pack_asset_validation.py` 的 `SPEC_SCHEMA_FILES` 注册 `schemas/active_run_lease.schema.json` 与 `schemas/active_run_takeover_audit.schema.json`，并更新 `tests/test_pack_asset_validation.py` 的 ownership 断言）、AGENT_USAGE/CHANGELOG 与 Skill hash 同步，普通 workflow 不读取活动 lease/audit | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py tests/test_pack_asset_validation.py tests/test_specrail_schema.py -k "active_run or required or ownership"` | Covers: B-012 B-013 | 完成 pack wiring。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4`，lease/schema/queue 是共享状态机。
- 只读 reviewer 可并行，不得修改 manifest 文件。

## 验证

- [ ] `SP189-T5` Owner: verification-owner | Depends on: SP189-T1 SP189-T2 SP189-T3 SP189-T4 | Done when: focused/full/pack/depth/diff/hash 全绿；不同 upstream 的两个临时 worktree/独立进程及运行中 remote 变化证明唯一稳定 owner；canonical lease/audit no-follow identity、无 persisted status 的派生状态、resume/takeover token rotation + new-owner unbound checkpoint rebind、CLI closed JSON/exit/redaction、通用 v3 与 queue-only v4 template 选择、serialized replace race、parent fsync failure、prepared takeover recovery/256 retention、same-boot monotonic expiry/boot-change stale、review+auto unsupported 阻断、bounded TTL 与授权 takeover 全部有 exact-head evidence；无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_active_run_lease.py tests/test_runtime_ledger_gate.py tests/test_check_workflow.py tests/test_pack_asset_validation.py tests/test_specrail_schema.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH189 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 | exact-head 交付证据。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 ready_to_implement 前不得实现。
- 不得自动 takeover/kill/删除他人 lease，remote write 仍遵守当前会话授权。
- manifest 完整列出 v4 hard-coded consumers、builder/acceptance tests 与新增 v4 fixture；
  通用 tranche templates 与已有 v1–v3 fixtures 按兼容合同保持不变；queue-only v4
  templates 只有成功 acquire 后才能使用，不含 GH-160。
