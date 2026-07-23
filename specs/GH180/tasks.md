# Task Plan

## Linked Issue

GH-180

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP180-T1` 在 `checks/check_workflow.py` 增加纯 artifact-presence 的 `invalid | staged | complete` shape helper 和稳定 packet snapshot sha256，并让 validator 接受有效 product/tech-only packet；只要 `tasks.md` 存在就继续执行全部 task 内容校验，缺失、空白、不可读或错误 identity 的 product/tech 仍 fail closed。同步更新 `tests/test_evaluate.py` 与 `tests/test_check_workflow_paths.py`，覆盖 staged、complete、invalid、present-invalid tasks、symlink/identity、半写文件、重复运行与 snapshot 改变后摘要变化。Covers: B-001 B-002 B-004 B-005 B-011 B-014 B-015 B-019。Owner: validator lane。Depends on: none；开始前须确认本文件有效，禁止生产代码编辑先于有效 task plan。Done when: shape 与摘要只由当前 artifact snapshot 决定；有效 staged/complete packet 通过，坏 tasks 不降级，失败与中断均重新全量校验。Verify: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py`。
- [ ] `SP180-T2` 在 `tests/test_check_workflow.py` 增加显式 packet 与 `--all-specs` CLI 审计回归，驱动 `checks/check_workflow.py` 对成功和失败 packet 按稳定路径顺序输出 `shape=<staged|complete|invalid>; readiness=unproven; packet_snapshot_sha256=<digest>`，保留既有最终消息与退出码。Covers: B-001 B-002 B-003 B-004 B-005 B-010 B-014 B-015 B-018 B-019。Owner: CLI audit lane。Depends on: SP180-T1。Done when: CLI 报告 shape、artifact、snapshot 与失败原因，但不把 shape 表述为授权；相同 tree 重跑输出一致。Verify: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py`。
- [ ] `SP180-T3` 在 `checks/github_issue_evidence.py` 与 `schemas/issue_evidence.schema.json` 增加必填 UTC `collected_at`，并在 `checks/route_gate.py` 对 readiness route 强制 fresh trusted label evidence，拒绝 CLI self-report、缺失、未来或超窗 evidence；route 先验证 packet，再返回规范化 `issue_evidence_sha256`、逐 artifact sha256 与聚合 `packet_snapshot_sha256`，并提供 `--verify-result <saved-route.json>` consumer gate。更新四个 `examples/fixtures/issue-*.json` 的结构；把 `tests/test_github_issue_evidence.py` 中 route/fixture 回归迁到已有 `tests/test_github_issue_route_evidence.py`，同步 `tests/route_gate_test_support.py`、`tests/test_configured_spec_path_review_regressions.py`，新增 `tests/test_issue_evidence_freshness.py` 并更新 `tests/test_route_gate.py`。Covers: B-006 B-007 B-008 B-009 B-013 B-014 B-015 B-018 B-019。Owner: evidence gate lane。Depends on: SP180-T1。Done when: 只有 fresh trusted label evidence可通过；旧 CLI-state 允许断言改为拒绝，固定时间 fixture 只作 schema/陈旧样本；consumer gate 确定性拒绝旧摘要；迁移不丢测试，原 851 行文件与所有修改文件均 `<800`。Verify: `/usr/bin/python3 -m pytest -q tests/test_issue_evidence_freshness.py tests/test_route_gate.py tests/test_github_issue_evidence.py tests/test_github_issue_route_evidence.py tests/test_configured_spec_path_review_regressions.py tests/test_route_gate_sensitive.py`。
- [ ] `SP180-T4` 更新 `AGENT_USAGE.md` 和三个 workflow skill，统一 staged lifecycle 与 snapshot-bound gate：write_spec 只写 product/tech；fresh trusted implement route 才规划 tasks；staged=`needs_tasks`；tasks 有效后重跑 route，并以 `--verify-result` consumer gate 通过才可启动生产代码 lane。记录纠偏、漂移后重采、GH-180 tracked bootstrap 边界；删减重复文字确保当前 799 行的 queue skill 修改后仍 `<800`。Covers: B-003 B-006 B-007 B-008 B-009 B-010 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019。Owner: contract docs lane。Depends on: SP180-T1..SP180-T3。Done when: 四个文件术语一致，禁止 shape、自报、旧 evidence/snapshot 或 bootstrap 扩权。Verify: `rg -n "staged|needs_tasks|ready_to_implement|packet_snapshot_sha256|verify-result|task" AGENT_USAGE.md skills/specrail-workflow/SKILL.md skills/specrail-plan-tasks/SKILL.md skills/specrail-implement-queue/SKILL.md`，再运行 `test $(wc -l < skills/specrail-implement-queue/SKILL.md) -lt 800`。
- [ ] `SP180-T5` 仅更新 `skills-lock.json` 中 SP180-T4 三个已修改 skill 的 sha256，不改变 skill 集合、顺序、路径或其它 hash。Covers: none。Owner: skill-lock lane。Depends on: SP180-T4。Done when: 三个目标 hash 与内容一致，其他 lock diff 为空。Verify: `/usr/bin/python3 checks/check_workflow.py --repo .` 并复核 `git diff -- skills-lock.json`。
- [ ] `SP180-T6` 执行 focused、CLI、evidence/route、fixture migration、queue、full、all-spec、depth、diff 与 size 验证；核对 validator 与 route 使用同一 current packet 摘要，staged 始终为 `needs_tasks`，只有 fresh trusted evidence + valid complete packet + digest match 才进入生产代码候选。Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019。Owner: verification coordinator。Depends on: SP180-T1..SP180-T5。Done when: 所有 fresh 命令通过；二十二个 planned paths 外无实现 diff；tracked bootstrap evidence 绑定 issue #180 与两阶段 transition，task plan 有效前没有生产代码实现。Verify: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py tests/test_check_workflow.py tests/test_issue_evidence_freshness.py tests/test_route_gate.py tests/test_github_issue_evidence.py tests/test_github_issue_route_evidence.py tests/test_configured_spec_path_review_regressions.py tests/test_route_gate_sensitive.py && /usr/bin/python3 -m pytest -q && /usr/bin/python3 checks/check_workflow.py --repo . --all-specs && /usr/bin/python3 tools/spec_depth_audit.py --spec-dir specs/GH180 --gate && git diff --check`，并对二十二个 planned paths 执行 `<800` 行检查。

## 并行拆分

- Validator lane 独占写入 `checks/check_workflow.py`、`tests/test_evaluate.py`、`tests/test_check_workflow_paths.py`。
- CLI audit lane 独占写入 `tests/test_check_workflow.py`；可在 SP180-T1 的 shape/output contract 稳定后并行补齐 CLI fixture，禁止修改 validator 文件。
- Evidence gate lane 在 SP180-T1 后独占写入 tech manifest 所列 evidence/route、四个 fixture、test support、issue evidence/route 与 configured-path 测试文件；拆分只移动 route/fixture 回归，不改断言意图。
- Contract docs lane 在 evidence contract 稳定后独占写入 `AGENT_USAGE.md` 与三个 workflow skill。
- Skill-lock lane 仅在 SP180-T4 完成后独占写入 `skills-lock.json`。
- Reviewer lane 全程只读，复核 invariant 覆盖、planned-path 白名单、shape/readiness 措辞与生产代码 gate；不得与任何 lane 共享可写文件。

## 验证

- Product invariant 集与 task Covers 并集均为 `B-001..B-019`，无缺项。
- Planned changes 恰好是 tech spec manifest 中的二十二条路径；新增 freshness 测试经 search-first 确认没有等价模块；已 851 行的 `tests/test_github_issue_evidence.py` 必须把 route/fixture 回归迁到已有 `tests/test_github_issue_route_evidence.py`，两者修改后均 `<800`。
- staged packet 通过 artifact 校验但在 queue 中归类为 `needs_tasks`；只有 valid tasks 使 packet 成为生产实现候选，shape 本身始终不授予 readiness。
- 按 SP180-T6 的顺序产出本次 session 的 focused、full、workflow、depth、diff 与 size gate 新鲜证据。

## Handoff Notes

- Bootstrap 前提已真实完成：live issue #180 已处于 `ready_to_implement`，旧 implement gate decision 为 allowed；历史证据持久化在 tracked `bootstrap-evidence.json`，只审计本次 bootstrap，不能充当修复后 route 的 current 授权。实现时若 fresh evidence 缺失、超窗、issue/packet 摘要不匹配或 decision 不再 allowed，必须停止并重新采集。
- 当前 task-planning 阶段必须把 GH-180 视为 `needs_tasks`；本文件通过 validator 与 coverage gate 前禁止生产代码实现。
- 实现阶段只能修改 tech manifest 中的二十二条路径；四个 spec refs 不属于实现路径。
- B-012 的在途纠偏应在 GH-180 validator 落地后于原 PR/原分支执行；GH-180 的一次性 bootstrap 不是其它 packet 提前创建 tasks 的先例。
