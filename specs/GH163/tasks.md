# Task Plan

## Linked Issue

GH-163

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP163-T1` 更新 review route 与 Gate Availability 契约。Covers: B-001 B-002 B-003 B-004 B-005。Owner: implementation lane。Depends on: none。Done when: gate 存在/缺失/错误/人工 degraded 四条路径无歧义。Verify: `python3 checks/check_workflow.py --repo .`。
- [x] `SP163-T2` 在 JSON gate 中校验 degraded status、授权与披露。Covers: B-004 B-005 B-006。Owner: implementation lane。Depends on: T1。Done when: 所有缺失或越界组合返回 blocked。Verify: `uvx pytest tests/test_review_json_gate.py -q -k 'gate_status or authorization or disclosure'`。
- [x] `SP163-T3` 扩展 review result schema 并保持 legacy compatibility。Covers: B-007 B-008。Owner: implementation lane。Depends on: T2。Done when: 合规 degraded artifact 通过 manifest loader，旧 fixtures 全绿。Verify: `uvx pytest tests/test_review_json_gate.py -q`。
- [x] `SP163-T4` 补充完整回归并同步 skill lock。Covers: B-006 B-007 B-008 B-009。Owner: verification owner。Depends on: T1 T2 T3。Done when: focused/full tests、workflow check、diff check 全绿。Verify: `uvx pytest -q`; `python3 checks/check_workflow.py --repo .`; `git diff --check`。

## 并行拆分

实现文件共享同一 artifact contract，任务串行执行；独立 reviewer 在稳定 head 后只读审查。

## 验证

- Product invariant set: B-001..B-009。
- Task coverage union: B-001..B-009。
- Exact-head independent reviewer、CI、review threads、`pr_gate` 待 push 后执行。

## Handoff Notes

继续原 PR #164，不创建竞争 PR、不 force-push。实现 lane 只能回复 thread；thread resolve
由独立 reviewer 或 human maintainer 执行。
