# Task Plan

## Linked Issue

GH-111

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP111-T001` 队列 skill description 加 ONLY-explicit 限定并排除描述性触发。 Covers: B-001, B-006, B-008, B-009 | Owner: skills | Done when: 两种触发方式与排除条款成文，原语义描述保留 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH111`
- [x] `SP111-T002` 12 个单件 specrail-* skills description 统一追加 explicit-invocation 限定。 Covers: B-002, B-009 | Owner: skills | Done when: 每个 description 含限定语且原语义不变 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH111`
- [x] `SP111-T003` workflow 路由改为点名才路由队列 skill。 Covers: B-003, B-006, B-007 | Owner: skills | Done when: 路由条件成文，未点名时的替代路径（单 issue implement 或提示 implx）成文 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH111`
- [x] `SP111-T004` implx SKILL.md 不动，验证其触发与行为条文零 diff。 Covers: B-004 | Owner: coordinator | Done when: `git diff skills/implx/` 为空 | Verify: `git diff --stat skills/implx/`
- [x] `SP111-T005` 刷新 skills-lock hash 并跑全量验证。 Covers: B-005 | Owner: coordinator | Done when: lock hash 一致、全部命令通过、无未声明写入 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`

## 并行拆分

串行实现：先队列 skill，再批量单件 skills，再 workflow 路由，最后 lock。
没有并行 writable ownership。

## 验证

- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH111`
- `python3 -m pytest -q`
- `git diff --check`

## Handoff Notes

合并后三台机器重装 skills。效果：不提 implx 的长期目标（如"做个 goal
一直优化"）不再被队列 skill 的 review 状态机接管；说 implx / implx auto
时行为与现在完全一致。消费仓库若在自家 AGENTS.md 里显式引导队列 skill，
那是显式委派，不受影响。
