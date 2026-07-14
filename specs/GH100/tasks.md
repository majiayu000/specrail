# Task Plan

## Linked Issue

GH-100

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP100-T001` 在 Bounded Tranche Hard Stop 小节加入 Same-Session Tranche Rollover 两分支规则与 item_cap 默认值。 Covers: B-001, B-002, B-003, B-004, B-007 | Owner: skills | Done when: rollover 条件、非 override 语义、交接首行 resume_prompt 与 item_cap 默认 3 均有明确条文，review 模式条文未被触碰 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH100`
- [x] `SP100-T002` 在 Reviewer Lane Failures 小节加入 lane 等待上限协议。 Covers: B-006 | Owner: skills | Done when: 等待上限（一次有界等待 + 一次 stop-and-return）与"禁止重复等待同一 lane"成文，恢复路径复用既有失败协议 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH100`
- [x] `SP100-T003` 在 implx auto 模式 bullet list 声明"无退化信号不暂停"并引用 queue skill 规则。 Covers: B-001, B-003 | Owner: skills | Done when: auto 条文引用 Same-Session Tranche Rollover 且列出四个交接条件 | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH100`
- [x] `SP100-T004` 更新 `templates/tranche_checkpoint.md` budget 注释（item_cap 默认与 item_cap_reason）。 Covers: B-004 | Owner: templates | Done when: 模板示例保留 compaction 默认，注明 auto 模式 item_cap 默认 3 与 `item_cap_reason` 要求 | Verify: `python3 checks/check_workflow.py --repo .`
- [x] `SP100-T005` 刷新 `skills-lock.json` 两个改动技能的 hash 并跑全量验证。 Covers: B-001, B-002, B-003, B-004, B-005, B-006, B-007 | Owner: coordinator | Done when: lock hash 与文件一致，全部命令通过且无未声明写入 | Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`

## 并行拆分

本次串行实现。两个 SKILL.md 与模板共享同一组行为不变量，先改 queue skill 主体，
再改 implx 入口与模板，最后刷新 lock。没有并行 writable ownership。

## 验证

- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH100`
- `python3 -m pytest -q`
- `git diff --check`

## Handoff Notes

合并后需在使用 implx 的机器上重装本地 skills
（`python3 tools/install_codex_skills.py --repo . --apply`），并同步
`~/.claude/skills/implx` 副本；正在运行的 implx session 不应中途换 skill
（W-20 运行面钉扎），等其自然交接后再更新。
