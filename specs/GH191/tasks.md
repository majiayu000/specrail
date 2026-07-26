# Task Plan

## Linked Issue

GH-191

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP191-T1` Owner: ledger-gate | Depends on: approved spec | Done when: closed immutable-event ledger 分离 `attempt_started` 与唯一 terminal event，验证 scope/run/head 状态机、内部 hash chain、progress recompute；三阈值保持 GH-157 的 commit/commit/tranche 口径，覆盖 4↔5 commits、2↔3 same-fingerprint commits、2↔3 tranches，且含 2 attempts=3+2 commits 触发、5 attempts=4 commits 不触发、1 attempt=3 same commits 触发；decision 只用 allowed/warn/needs_human/blocked + 稳定 reason id | Verify: `python3 -m pytest -q tests/test_issue_progress_gate.py` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-011 B-012 B-016 | 新增 ledger schema/gate/template。
- [ ] `SP191-T2` Owner: collector | Depends on: SP191-T1 | Done when: bounded read-only collector 绑定 issue/head/run/spec IDs、可信 `as_of` 与 snapshot digest，输出 start/terminal candidate，不读 session/raw logs、不读墙钟改变既有输入判断 | Verify: `python3 -m pytest -q tests/test_issue_attempt_collector.py -k "candidate or deterministic or as_of"` | Covers: B-001 B-002 B-003 B-004 B-009 B-012 B-016 | 新增 collector。
- [ ] `SP191-T3` Owner: queue-integration | Depends on: SP191-T6, GH-172 merged | Done when: pre-lane gate 要求 committed anchor attestation，queue 只经 writer 更新 ledger；blocked（trip、pending anchor、history loss 或其他 history 缺陷）无继续路径，remote park/draft 仅在已有授权时执行 | Verify: `python3 -m pytest -q tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py -k "queue or authorization or anchor"` | Covers: B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-013 B-014 B-015 | 对齐已合并 GH-174/GH-189。
- [ ] `SP191-T4` Owner: pack-docs | Depends on: SP191-T3 | Done when: assets/wiring/docs/hash 全部同步（ledger/anchor schema 注册进 `checks/pack_asset_validation.py` 的 `SPEC_SCHEMA_FILES` 并同步 `tests/test_pack_asset_validation.py` 的 ownership 断言），普通 workflow 纯仓库通过 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py tests/test_pack_asset_validation.py` | Covers: B-012 B-013 B-014 B-015 B-016 | pack 收口。
- [ ] `SP191-T6` Owner: writer-anchor | Depends on: SP191-T1 SP191-T2 | Done when: 唯一 writer helper 实现 `init-baseline`/`migrate-baseline`/start/terminal/scope/recover；用 expected ledger digest + 外部 anchor generation 做 prepare/CAS、temp+fsync+atomic replace+dir fsync、commit attestation，拒绝 direct rewrite、并发丢写、重复 terminal、pending/mismatch；首次 baseline 绑定 repo/issue/trusted head/as_of/history digest/authorization，anchor 已存在但 ledger 缺失判 history loss | Verify: `python3 -m pytest -q tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py -k "writer or anchor or baseline or migration or history_loss or recover"` | Covers: B-001 B-002 B-009 B-012 B-013 B-014 B-015 B-016 | 新增 writer、anchor schema/template 与测试。

## 并行拆分

- 固定串行 `T1 → T2 → T6 → T3 → T4 → T5`，ledger/fingerprint/writer/anchor/gate 是共享合同；保留已发布的 T1..T5 ID，新增 writer 为 T6。
- reviewer 可只读检查阈值误报，不修改 manifest。

## 验证

- [ ] `SP191-T5` Owner: verification-owner | Depends on: SP191-T1 SP191-T2 SP191-T3 SP191-T4 SP191-T6 | Done when: focused/full/pack/depth/diff/hash 与三次 resume forward test 全绿；5-commit 与 3-same-commit 用例刻意令 attempts≠commits，start/terminal 不可变、墙钟跨越 `as_of` 不改结果、anchor 尾截断/整体重写/pending、首次 baseline 与 history loss、writer 中断恢复全部有 fresh evidence，多提交真进展不误报、message 改写不绕过、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_issue_attempt_collector.py tests/test_issue_attempt_writer.py tests/test_issue_progress_gate.py tests/test_check_workflow.py tests/test_pack_asset_validation.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH191 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；合并/readiness gate 前不得实现。
- gate 永不执行 park/draft/comment；外部动作沿用用户授权边界。
- trusted anchor provider 位于 ledger/checkout 外；工作树内复制品不构成 B-013 证据。
- queue/lock 等待 GH-172，并 rebase GH-174/GH-189。
