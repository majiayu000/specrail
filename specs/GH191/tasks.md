# Task Plan

## Linked Issue

GH-191

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP191-T1` Owner: ledger-gate | Depends on: SP191-T7 | Done when: closed immutable-event ledger 分离 `attempt_started` 与唯一 terminal event，验证 scope/run/head 状态机、内部 hash chain、progress recompute；三阈值保持 GH-157 的 commit/commit/tranche 口径，覆盖 4↔5 commits、2↔3 same-fingerprint commits、2↔3 tranches，且含 2 attempts=3+2 commits 触发、5 attempts=4 commits 不触发、1 attempt=3 same commits 触发；公开 gate 必须消费受保护 challenge 对应的 provider current-state proof，旧 ledger+旧 attestation/proof、错/已消费 challenge、current generation 前移均 fail closed；decision 只用 allowed/warn/needs_human/blocked + 稳定 reason id | Verify: `python3 -m pytest -q tests/test_issue_progress_gate.py -k "ledger or event or threshold or freshness or challenge or replay"` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-011 B-012 B-016 B-017 B-019 | 新增 ledger schema/gate/template。
- [ ] `SP191-T2` Owner: collector | Depends on: SP191-T1 SP191-T7 | Done when: bounded read-only collector 只接受已验证的 trusted evidence envelope，绑定 issue/head/run/spec IDs、签名 `provider_as_of`、adapter-run provenance 与 snapshot digest，输出 start/terminal candidate，不信任 caller-authored evidence path、不读 session/raw logs、不读墙钟改变既有输入判断 | Verify: `python3 -m pytest -q tests/test_issue_attempt_collector.py tests/test_github_issue_attempt_evidence.py -k "candidate or deterministic or as_of or provenance"` | Covers: B-001 B-002 B-003 B-004 B-009 B-012 B-016 B-019 | 新增 collector。
- [ ] `SP191-T3` Owner: queue-integration | Depends on: SP191-T6, GH-172/PR #186 merged into target base, GH-174/PR #192 rebased on GH-172 then merged, GH-189/PR #193 rebased on GH-174 then merged, GH-191 rebased on all three | Done when: fresh GitHub preflight 证明上述顺序且不把 open PR 当 merged；pre-lane gate 要求 fresh current-state proof，queue 只经 writer 更新 ledger；blocked（trip、stale proof、pending anchor、untrusted evidence、scope authorization invalid、history loss 或其他 history 缺陷）无继续路径，remote park/draft 仅在已有授权时执行 | Verify: `python3 -m pytest -q tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py tests/test_check_workflow.py -k "queue or authorization or anchor or freshness or upstream or dependency"` | Covers: B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-013 B-014 B-015 B-017 B-018 B-019 B-020 | 只在 fresh truth 证明 upstream 按序合入后对齐最终 queue/run/fencing 合同。
- [ ] `SP191-T4` Owner: pack-docs | Depends on: SP191-T3 | Done when: assets/wiring/docs/hash 全部同步（ledger/anchor/current-proof/evidence/scope-authorization schemas 全部注册进 `checks/pack_asset_validation.py` 的 `SPEC_SCHEMA_FILES` 并同步 `tests/test_pack_asset_validation.py` 的 exact ownership 断言），普通 workflow 纯仓库通过 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py tests/test_pack_asset_validation.py` | Covers: B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 | pack 收口。
- [ ] `SP191-T6` Owner: writer-anchor | Depends on: SP191-T1 SP191-T2 SP191-T7 | Done when: 唯一 writer helper 实现 `init-baseline`/`migrate-baseline`/start/terminal/scope/recover；用 expected ledger digest + 外部 anchor generation 做 prepare/CAS、temp+fsync+atomic replace+dir fsync、commit attestation，拒绝 direct rewrite、并发丢写、重复 terminal、pending/mismatch；`open-scope` 验证 exact maintainer rescope/unpark 授权，并在 provider CAS 中 create-only 原子消费 authorization ID、写入 event/anchor transaction，错 scope/epoch/generation/tail、伪造/重放/竞态均失败；首次 baseline 绑定 repo/issue/trusted head/as_of/history digest/authorization，anchor 已存在但 ledger 缺失判 history loss | Verify: `python3 -m pytest -q tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py tests/test_github_issue_attempt_evidence.py -k "writer or anchor or baseline or migration or history_loss or recover or scope_authorization or unpark or replay"` | Covers: B-001 B-002 B-009 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 | 新增 writer、anchor schema/template 与测试。
- [ ] `SP191-T7` Owner: trusted-evidence-auth | Depends on: approved spec, fresh dependency status recorded | Done when: 新增 `github_issue_attempt_evidence.py` 与 closed evidence/scope-authorization schemas；allowlisted issuer/trust root/adapter executable 对完整 GitHub query/pagination、repo/issue/head、`provider_as_of` 与 payload digest 签名，unknown/self-declared/incomplete evidence fail closed；受保护 runtime challenge 从 provider 获取 nonce-bound current-state proof；maintainer role map 产出 exact `open_scope_once` rescope/unpark 授权，普通 writer/agent 不可伪造 | Verify: `python3 -m pytest -q tests/test_github_issue_attempt_evidence.py tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py -k "issuer or adapter or signature or pagination or freshness or challenge or scope_authorization"` | Covers: B-012 B-016 B-017 B-018 B-019 | 复用现有 trusted GitHub adapter/content-binding 与一次性 review authorization 模式，不复用其不同语义字段。

## 并行拆分

- 外部固定串行 `GH-172/PR #186 merge → rebase+merge GH-174/PR #192 → rebase+merge GH-189/PR #193 → rebase GH-191`；截至 2026-07-26 fresh truth 三个 PR 均 OPEN，故当前不得开始实现。
- 内部固定串行 `T7 → T1 → T2 → T6 → T3 → T4 → T5`，evidence/provenance、ledger/fingerprint/writer/anchor/gate 是共享合同；保留已发布 T1..T6 ID，新增可信证据任务为 T7。
- reviewer 可只读检查阈值误报，不修改 manifest。

## 验证

- [ ] `SP191-T5` Owner: verification-owner | Depends on: SP191-T1 SP191-T2 SP191-T3 SP191-T4 SP191-T6 SP191-T7 | Done when: focused/full/pack/depth/diff/hash 与三次 resume forward test 全绿；5-commit 与 3-same-commit 用例刻意令 attempts≠commits，start/terminal 不可变、墙钟跨越 `as_of` 不改结果、anchor 尾截断/整体重写/pending、旧 ledger+旧 attestation/proof replay、provider generation 前移、未知 adapter/issuer、分页不全、伪造 `as_of`、scope 授权伪造/错绑/重放、首次 baseline 与 history loss、writer 中断恢复全部有 fresh evidence；依赖 gate 覆盖 #186/#192/#193 open/closed-unmerged/跳序/rebase 漂移与按序 merged 正例，多提交真进展不误报、message 改写不绕过、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_github_issue_attempt_evidence.py tests/test_issue_attempt_collector.py tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py tests/test_check_workflow.py tests/test_pack_asset_validation.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH191 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；合并/readiness gate 前不得实现。
- gate 永不执行 park/draft/comment；外部动作沿用用户授权边界。
- trusted anchor provider 位于 ledger/checkout 外；工作树内复制品不构成 B-013 证据。
- 截至 2026-07-26，PR #186/#192/#193 均 OPEN、`mergedAt=null`；状态只能由 implementation
  preflight 的 fresh GitHub evidence 更新，spec/PR body 不得宣称已合并。
- queue/lock 必须等待并按 `GH-172 → GH-174 → GH-189 → GH-191` 逐项 merge/rebase；
  任一步未完成都不能用复制未合并合同或直接改最终共享文件绕过。
