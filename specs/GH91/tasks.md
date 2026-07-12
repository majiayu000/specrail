# Task Plan

## Linked Issue

GH-91

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP91-T001` 增加共享 path validator 并连接 configured discovery。 Covers: B-001, B-002, B-005, B-006, B-008 | Owner: workflow | Done when: parent 恒定，POSIX/Windows/`..`/symlink 逃逸、identity 重定向和 resolve loop 均明确失败 | Verify: `python3 -m pytest -q tests/test_check_workflow.py tests/test_evaluate.py`
- [x] `SP91-T002` 让 issue evidence CLI 从 `--repo` 验证并渲染三类 spec artifacts。 Covers: B-003, B-005, B-007, B-008 | Owner: evidence | Done when: fake gh 输出 custom paths，artifact 错位或 issue mismatch 非零退出 | Verify: `python3 -m pytest -q tests/test_github_issue_evidence.py`
- [x] `SP91-T003` 让 route gate 安全生成 configured packet 验证命令。 Covers: B-004, B-005, B-006 | Owner: route_gate | Done when: custom `--spec-dir` 经 shell quote，artifact resolve 不能逃逸 repo | Verify: `python3 -m pytest -q tests/test_route_gate.py`
- [x] `SP91-T004` 更新 README、AGENT_USAGE 和 CHANGELOG。 Covers: B-001, B-003, B-004 | Owner: docs | Done when: 文档说明唯一配置源且命令仍可复制执行 | Verify: `python3 checks/check_workflow.py --repo .`
- [x] `SP91-T005` 执行 focused/full/pack 验证并复核 diff。 Covers: B-001, B-002, B-003, B-004, B-005, B-006, B-007, B-008 | Owner: coordinator | Done when: 全部命令通过且无未声明写入 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 checks/check_workflow.py --repo . --spec-dir specs/GH91 && git diff --check`

## 并行拆分

本次串行实现。template helper、collector 与 route 输出共享 artifact contract，先稳定
helper 与 tests，再修改下游。没有并行 writable ownership。

## 验证

- `python3 -m pytest -q tests/test_check_workflow.py tests/test_evaluate.py tests/test_github_issue_evidence.py tests/test_route_gate.py`
- `python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH91`
- `python3 -m compileall checks`
- `git diff --check`

## Handoff Notes

VibeGuard adoption 应在包含本修复的精确 SpecRail commit 上取 pack，并将
`artifacts.*` 配置为 `docs/specs/GH{issue_number}`。上游 PR 合并前不得把该 commit
描述为正式 release。
