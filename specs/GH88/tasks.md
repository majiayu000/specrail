# Task Plan

## Linked Issue

GH-88

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP88-T001` 在聚焦的 `checks/github_issue_reference.py` 中添加 strict visible-Markdown partial matcher，并为 collector 添加显式 `--issue` 与 live issue 查询。 Covers: B-002, B-003, B-004, B-012 | Owner: adapter | Done when: partial 只能由非代码块/非注释的精确正文引用和 live OPEN issue 产生，collector 保持低于 800 行 | Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py -k 'partial or expected_issue'`
- [x] `SP88-T002` 扩展 evidence assembly 与 query snapshot 稳定性检查。 Covers: B-001, B-005, B-008, B-009 | Owner: adapter | Done when: closing/partial 均输出自洽 relation，mixed relation 保留全部 closing 编号且显式目标不被重定向，query 漂移 fail closed | Verify: `python3 -m pytest -q tests/test_github_pr_evidence.py`
- [x] `SP88-T003` 扩展 schema 与 offline PR gate relation consistency checker。 Covers: B-006, B-007, B-010, B-011 | Owner: gate | Done when: verified partial allowed，矛盾 relation blocked，legacy evidence 兼容 | Verify: `python3 -m pytest -q tests/test_pr_gate.py tests/test_specrail_schema.py`
- [x] `SP88-T004` 更新 agent usage、queue/PR-gate skills 与 `skills-lock.json`。 Covers: B-002, B-010 | Owner: docs | Done when: partial 采集命令可执行且 closure boundary 明确 | Verify: `python3 checks/check_workflow.py --repo .`
- [x] `SP88-T005` 完成 focused、full suite、spec packet 与 live read-only gate 验证。 Covers: B-001, B-003, B-004, B-005, B-006, B-008, B-009, B-010, B-011, B-012 | Owner: coordinator | Done when: 全部 deterministic checks 通过；Remem #801 evidence 将 GH671 识别为 verified partial、保留 closing #806，gate relation satisfied 且 GH671 仍 OPEN、无 closure/final-completion 字段或动作 | Verify: 执行 `tech.md` 测试计划中的完整 Remem #801 adapter→gate 命令，再执行 `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 checks/check_workflow.py --repo . --spec-dir specs/GH88`

## 并行拆分

本次不并行写代码：adapter、schema 与 gate 共享 evidence contract，必须串行稳定字段
后再更新 docs/lockfile。独立 reviewer 仅只读，不拥有 writable files。

## 验证

- `python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_pr_gate.py tests/test_specrail_schema.py`
- `python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH88`
- `python3 -m compileall checks`
- `git diff --check`
- `tech.md` 中完整的 Remem #801 live read-only adapter→gate 命令与 jq assertions

## Handoff Notes

用户在当前会话明确授权完成 issue、spec、implementation、PR 与 merge 闭环。实现仍需
保持 collector 只读、gate 离线、partial 不关闭 umbrella issue；任何新远端漂移均
要求刷新 exact-head evidence。
