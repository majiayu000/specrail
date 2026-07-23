# Task Plan

## Linked Issue

GH-188

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP188-T1` Owner: bundle-core | Depends on: approved spec, GH-165/GH-172 merged | Done when: closed manifest、路径/hash/稳定快照与 doctor 状态全覆盖 | Verify: `python3 -m pytest -q tests/test_runtime_bundle.py -k "manifest or doctor"` | Covers: B-001 B-002 B-003 B-004 B-005 B-008 B-011 B-012 | 新增 lock/library/check CLI。
- [ ] `SP188-T2` Owner: installer | Depends on: SP188-T1 | Done when: 默认 dry-run、显式 apply、staging/atomic write/post-doctor 与取消失败全覆盖 | Verify: `python3 -m pytest -q tests/test_runtime_bundle.py -k install` | Covers: B-006 B-007 B-008 B-011 | 新增 install CLI。
- [ ] `SP188-T3` Owner: queue-install-integration | Depends on: SP188-T1 SP188-T2 | Done when: queue require-adopted preflight 在所有写动作前，install Skill 提供 doctor/adopt route 且不自动 apply | Verify: `python3 -m pytest -q tests/test_runtime_bundle.py -k "queue or skill"` | Covers: B-006 B-009 B-010 | 更新 Skills/hash/docs。
- [ ] `SP188-T4` Owner: pack-wiring | Depends on: SP188-T3 | Done when: bundle assets required，普通 workflow 只验证源 repo | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py -k runtime_bundle` | Covers: B-001 B-010 B-012 | pack 收口。

## 并行拆分

- 固定串行 T1→T2→T3→T4，共享 manifest 与 installer。

## 验证

- [ ] `SP188-T5` Owner: verification-owner | Depends on: SP188-T1 SP188-T2 SP188-T3 SP188-T4 | Done when: focused/full/pack/depth/diff/hash 与两个 consumer forward test 全绿，无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_runtime_bundle.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH188 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 | exact-head 证据。

## Handoff Notes

- 当前只允许 write_spec；实现等待 GH-165/GH-172。
- installer 不自动 apply；manifest 12 个路径，不含 GH-160。
