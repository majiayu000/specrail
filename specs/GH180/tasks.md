# Task Plan

## Linked Issue

GH-180

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP180-T1` 在 `checks/check_workflow.py` 增加纯 artifact-presence 的 `invalid | staged | complete` shape helper，并让现有 packet validator 接受有效 product/tech-only packet；只要 `tasks.md` 存在就继续执行全部 task 内容校验，缺失/空白/不可读/错误 identity 的 product 或 tech 仍 fail closed。同步更新 `tests/test_evaluate.py` 与 `tests/test_check_workflow_paths.py`，覆盖 staged、complete、invalid、present-but-invalid tasks、symlink/identity、半写/空文件、重复运行与 snapshot 改变后重验。Covers: B-001 B-002 B-004 B-005 B-011 B-014 B-015 B-019。Owner: validator lane。Depends on: none；开始前须确认本文件有效，且当前 packet 必须分类为 `needs_tasks`，禁止任何生产代码编辑先于有效 task plan。Done when: shape 只由当前 artifact snapshot 决定；有效 product/tech-only 通过，三文件 packet 保持兼容，坏 tasks 不得降级为 staged，所有失败与中断路径均重新全量校验。Verify: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py`。
- [ ] `SP180-T2` 在 `tests/test_check_workflow.py` 增加显式 packet 与 `--all-specs` CLI 审计回归，驱动 `checks/check_workflow.py` 对成功和失败 packet 按稳定路径顺序输出 `shape=<staged|complete|invalid>; readiness=unproven`，并保留既有最终消息与退出码。Covers: B-001 B-002 B-003 B-004 B-005 B-010 B-014 B-015 B-018 B-019。Owner: CLI audit lane。Depends on: SP180-T1 的 shape/output contract；该 lane 只写 `tests/test_check_workflow.py`，若发现生产实现缺口则交还 validator lane。Done when: CLI 在无 GitHub evidence 时完整报告 shape、发现的 artifact 与校验失败，但绝不把 staged 或 complete 表述为 approval、readiness 或实现授权；相同 tree 重跑输出一致。Verify: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py`。
- [ ] `SP180-T3` 更新 `AGENT_USAGE.md`、`skills/specrail-workflow/SKILL.md`、`skills/specrail-plan-tasks/SKILL.md`、`skills/specrail-implement-queue/SKILL.md`，统一 staged lifecycle：`ready_to_spec + write_spec: allowed` 只写 product/tech；可信 `ready_to_implement + implement: allowed` 才规划 tasks；staged 在 queue 中必须归类为 `needs_tasks`；只有 tasks 创建且验证有效后才可归类 `complete` 并启动生产代码 lane。记录可信 evidence、纠偏删除提前 tasks、并发漂移后重采、GH-180 一次性 bootstrap 与不可复用边界。Covers: B-003 B-006 B-007 B-008 B-009 B-010 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019。Owner: contract docs lane。Depends on: SP180-T1 的术语与 SP180-T2 的 audit wording。Done when: 四个文件使用一致的 `staged | complete | invalid`、`needs_tasks | complete | needs_spec` 与 `readiness=unproven` 语义；明确禁止 shape、自报、body hint、旧证据或 bootstrap 例外扩权，并明确生产代码必须等待有效 tasks。Verify: `rg -n "staged|needs_tasks|ready_to_implement|task" AGENT_USAGE.md skills/specrail-workflow/SKILL.md skills/specrail-plan-tasks/SKILL.md skills/specrail-implement-queue/SKILL.md`，再按 `product.md` 的 B-003、B-006..B-019 人工逐项复核。
- [ ] `SP180-T4` 仅更新 `skills-lock.json` 中 SP180-T3 三个已修改 skill 的 sha256；不得改变 skill 集合、顺序、路径或其它 hash。Covers: none（分发完整性 housekeeping，不直接实现产品行为）。Owner: skill-lock lane。Depends on: SP180-T3。Done when: 三个目标 hash 与文件内容一致，除这三项外 lock diff 为空。Verify: `/usr/bin/python3 checks/check_workflow.py --repo .`，并人工复核 `git diff -- skills-lock.json` 仅含三条 hash。
- [ ] `SP180-T5` 执行 focused、CLI、queue/route regression、full suite、all-spec、GH180 depth、diff 与 touched-file size 验证；核对 validator shape audit 与 fresh route JSON 是两份独立证据，且 staged packet 始终为 `needs_tasks`、不进入生产代码候选。Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019。Owner: verification coordinator。Depends on: SP180-T1 SP180-T2 SP180-T3 SP180-T4。Done when: 所有 fresh 命令通过；九个 planned paths 之外无实现 diff；GH-180 bootstrap evidence 绑定 issue #180 与本次 auth_mode auto transition，且 task plan 有效之前没有任何生产代码实现。Verify: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py tests/test_check_workflow.py && /usr/bin/python3 -m pytest -q && /usr/bin/python3 checks/check_workflow.py --repo . --all-specs && /usr/bin/python3 tools/spec_depth_audit.py --spec-dir specs/GH180 --gate && git diff --check`，并对九个 planned paths 执行 `<800` 行检查。

## 并行拆分

- Validator lane 独占写入 `checks/check_workflow.py`、`tests/test_evaluate.py`、`tests/test_check_workflow_paths.py`。
- CLI audit lane 独占写入 `tests/test_check_workflow.py`；可在 SP180-T1 的 shape/output contract 稳定后并行补齐 CLI fixture，禁止修改 validator 文件。
- Contract docs lane 独占写入 `AGENT_USAGE.md`、`skills/specrail-workflow/SKILL.md`、`skills/specrail-plan-tasks/SKILL.md`、`skills/specrail-implement-queue/SKILL.md`。
- Skill-lock lane 仅在 SP180-T3 完成后独占写入 `skills-lock.json`。
- Reviewer lane 全程只读，复核 invariant 覆盖、planned-path 白名单、shape/readiness 措辞与生产代码 gate；不得与任何 lane 共享可写文件。

## 验证

- Product invariant 集与 task Covers 并集均为 `B-001..B-019`，无缺项。
- Planned changes 恰好是以下九条路径：`AGENT_USAGE.md`、`checks/check_workflow.py`、`skills-lock.json`、`skills/specrail-implement-queue/SKILL.md`、`skills/specrail-plan-tasks/SKILL.md`、`skills/specrail-workflow/SKILL.md`、`tests/test_check_workflow.py`、`tests/test_check_workflow_paths.py`、`tests/test_evaluate.py`。
- staged packet 通过 artifact 校验但在 queue 中归类为 `needs_tasks`；只有 valid tasks 使 packet 成为生产实现候选，shape 本身始终不授予 readiness。
- 按 SP180-T5 的顺序产出本次 session 的 focused、full、workflow、depth、diff 与 size gate 新鲜证据。

## Handoff Notes

- Bootstrap 前提已由 coordinator 真实完成：live issue #180 已处于 `ready_to_implement`，fresh implement route gate decision 为 allowed；证据引用 `.specrail/runtime/artifacts/20260723-t10/gh180-implement-route-gate.json`。若该证据缺失、过期、issue/packet 不匹配或 decision 不再 allowed，停止后续实现并重新采集，不得复制、补写或推断授权。
- 当前 task-planning 阶段必须把 GH-180 视为 `needs_tasks`；本文件通过 validator 与 coverage gate 之前，禁止修改上述九个 planned paths 中的生产/合同实现，也禁止启动任何生产代码 lane。
- 实现阶段只能修改 tech spec manifest 中列出的九条路径；`specs/GH180/product.md`、`specs/GH180/tech.md` 与本文件是 spec refs，不属于实现路径。
- B-012 的在途纠偏应在 GH-180 validator 落地后于原 PR/原分支执行；GH-180 的一次性 bootstrap 不是其它 packet 提前创建 tasks 的先例。
