# Task Plan

## Linked Issue

GH-104

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP104-T001` 改写 Goal Use 小节为 auto drain / 其余两分支，含 objective 内容要求、token 预算规则与终态协议。 Covers: B-001, B-002, B-005, B-006, B-007 | Owner: skills | Done when: auto drain 分支条件、objective 必含要素、预算记录、complete/budget-exhausted/interrupt 终态与"禁止未排空标 complete"均成文，保留 goal 不替代 checkpoint/gates 原句 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH104`
- [x] `SP104-T002` 在 Bounded Tranche Hard Stop / Context Budget 加入 goal 激活期间的 compaction 豁免与压缩后重锚规则。 Covers: B-003, B-004, B-006 | Owner: skills | Done when: goal-active 时 compaction 不触发 handoff、压缩后必须重读 checkpoint + 刷新 remote truth、无 goal 时规则原样、tranche 记账与 ledger gate 不变均成文 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH104`
- [x] `SP104-T003` 更新 implx auto bullet：goal 默认开启条件、compaction 不中断、四类终止条件。 Covers: B-001, B-005 | Owner: skills | Done when: auto 条文引用 queue skill Goal Use auto drain 分支 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH104`
- [x] `SP104-T004` 在 checkpoint 模板 goal 对象上方加启用条件注释。 Covers: B-002 | Owner: templates | Done when: 注释说明 auto drain 默认建 goal 与预算记录要求，JSON 示例不变 | Verify: `python3 checks/check_workflow.py --repo .`
- [x] `SP104-T005` 刷新 skills-lock hash 并跑全量验证。 Covers: B-001, B-002, B-003, B-004, B-005, B-006, B-007 | Owner: coordinator | Done when: lock hash 与文件一致，全部命令通过且无未声明写入 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`

## 并行拆分

本次串行实现。两个 SKILL.md 与模板共享同一组行为不变量，先改 queue skill，
再改 implx 入口与模板，最后刷新 lock。没有并行 writable ownership。

## 验证

- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH104`
- `python3 -m pytest -q`
- `git diff --check`

## Handoff Notes

合并后在三台机器重装 skills（`python3 tools/install_codex_skills.py --repo .
--apply`），并同步 `~/.claude/skills/implx`。正在运行的 implx session 等自然
交接后再更新。首次 goal-wired auto run 建议给出显式 token 预算并观察 goal
终态与 checkpoint 一致性。
