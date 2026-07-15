# Task Plan

## Linked Issue

GH-106

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP106-T001` implx auto bullet 增加 standing authorizations 块并收窄 human_decisions 定义。 Covers: B-001, B-003, B-004, B-005, B-007 | Owner: skills | Done when: 四条自动放行与保留边界成文 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH106`
- [x] `SP106-T002` Spec Coverage Gate 增加 auto readiness 自动放行与 `readiness_label_source` 记录。 Covers: B-001, B-002, B-006 | Owner: skills | Done when: complete/umbrella 才放行、needs_spec 不放行、审计字段成文 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH106`
- [x] `SP106-T003` Reviewer-Lane Failure Protocol 增加双 lane 失败后的 auto scoped self-review 授权。 Covers: B-003, B-006 | Owner: skills | Done when: 两条不同 lane + lane_failures 完整为前置、授权对象字段与 scope 要求成文、silent substitution 禁令保留 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH106`
- [x] `SP106-T004` Boundaries 细化同 owner 跨仓库授权；Queue Planning 增加弃用窗口默认值。 Covers: B-004, B-005, B-007 | Owner: skills | Done when: 同 owner + 队列引用才放行、跨 owner 仍禁、deprecation_default 记录成文 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH106`
- [x] `SP106-T005` 刷新 skills-lock hash 并跑全量验证。 Covers: B-001, B-002, B-003, B-004, B-005, B-006, B-007 | Owner: coordinator | Done when: lock hash 一致、全部命令通过、无未声明写入 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`

## 并行拆分

串行实现：先 queue skill 三处，再 implx 入口，最后刷新 lock。没有并行
writable ownership。

## 验证

- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH106`
- `python3 -m pytest -q`
- `git diff --check`

## Handoff Notes

合并后三台机器重装 skills 并同步 `~/.claude/skills/implx`。本次用户已在
对话中直接批准 remem #817-#820 readiness、#837 self-review、#720 跨仓库
与 #684 弃用窗口——正在运行的旧 session 可凭该显式授权继续，无需等
skill 更新。
