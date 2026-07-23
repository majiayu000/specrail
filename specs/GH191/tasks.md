# Task Plan

## Linked Issue

GH-191

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP191-T1` Owner: ledger-gate | Depends on: approved spec | Done when: closed append-only ledger、progress recompute、三阈值、scope epoch 与稳定错误全部有测试 | Verify: `python3 -m pytest -q tests/test_issue_progress_gate.py` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-011 B-012 | 新增 schema/gate/template。
- [ ] `SP191-T2` Owner: collector | Depends on: SP191-T1 | Done when: bounded read-only collector 绑定 issue/head/run/spec IDs，输出可 append candidate，不读 session/raw logs | Verify: `python3 -m pytest -q tests/test_issue_attempt_collector.py` | Covers: B-001 B-002 B-003 B-004 B-009 B-012 | 新增 collector。
- [ ] `SP191-T3` Owner: queue-integration | Depends on: SP191-T1 SP191-T2, GH-172 merged | Done when: pre-lane 调 gate，trip/invalid 无继续路径，remote park/draft 仅在已有授权时执行 | Verify: `python3 -m pytest -q tests/test_issue_progress_gate.py -k "queue or authorization"` | Covers: B-005 B-006 B-007 B-008 B-009 B-010 B-011 | 对齐已合并 GH-174/GH-189。
- [ ] `SP191-T4` Owner: pack-docs | Depends on: SP191-T3 | Done when: assets/wiring/docs/hash 全部同步，普通 workflow 纯仓库通过 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-012 | pack 收口。

## 并行拆分

- 固定串行 `T1 → T2 → T3 → T4`，ledger/fingerprint/gate 是共享合同。
- reviewer 可只读检查阈值误报，不修改 manifest。

## 验证

- [ ] `SP191-T5` Owner: verification-owner | Depends on: SP191-T1 SP191-T2 SP191-T3 SP191-T4 | Done when: focused/full/pack/depth/diff/hash 与三次 resume forward test 全绿，多提交真进展不误报、message 改写不绕过、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_issue_attempt_collector.py tests/test_issue_progress_gate.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH191 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；合并/readiness gate 前不得实现。
- gate 永不执行 park/draft/comment；外部动作沿用用户授权边界。
- queue/lock 等待 GH-172，并 rebase GH-174/GH-189。
