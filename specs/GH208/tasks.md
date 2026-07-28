# Task Plan

## Linked Issue

GH-208

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP208-T1` 建立 breaking workflow 基线：加入 `fastlane | standard | heavy` profiles，将 Issue 收敛为八状态并同步 route gate。 Covers: B-001, B-002, B-003, B-005, B-006, B-007, B-018, B-019 | Owner: primary | Dependencies: none | Done when: profile 选择确定性，`parked + ready_to_*` 与多 readiness labels 一次拒绝，sensitive registry 自动选择 `heavy` | Verify: `/usr/bin/python3 -m pytest -q tests/test_specrail_yaml.py tests/test_route_gate.py tests/test_route_gate_sensitive.py tests/test_workflow_profiles.py`
- [x] `SP208-T2` 把 full/diff-only 两轮、P0/P1 阻断、P2/P3 follow-up 与 outdated hosted thread 收敛到单一 review gate；先让直接 review 路径脱离旧 helper，物理删除延后到 PR gate 消费方迁移完成。 Covers: B-008, B-009, B-010, B-017, B-018 | Owner: primary | Dependencies: SP208-T1 | Done when: round 1/2 正反例通过，round >2 返回 `needs_human`，旧字段一次报告，P2/P3 不阻断 | Verify: `/usr/bin/python3 -m pytest -q tests/test_review_json_gate.py tests/test_review_policy.py`
- [x] `SP208-T3` 重写当前证据 PR gate，迁移并删除旧 review/content/round helper，保留 current head、CI、merge state、linked Issue、当前 P0/P1、profile、sensitive classification 和人工 heavy merge authorization。 Covers: B-003, B-010, B-011, B-017, B-018, B-019 | Owner: primary | Dependencies: SP208-T1, SP208-T2 | Done when: 三 profile 由同一 gate 判断，security 缺证据 fail closed，旧 runtime/tier 字段统一 unsupported | Verify: `/usr/bin/python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_github_pr_evidence_cli.py tests/test_pr_gate.py tests/test_pr_gate_sensitive_routes.py tests/test_pr_gate_terminal.py`
- [x] `SP208-T4` 删除 Goal、budget、telemetry、checkpoint gate、tier authorization、thread-dispatch schema 及全部 runtime fixtures/tests。 Covers: B-012, B-013, B-014, B-017 | Owner: primary | Dependencies: SP208-T3 | Done when: 生产合同不再引用已删除 runtime checker/schema，legacy negative test 返回重建提示 | Verify: `/usr/bin/python3 -m pytest -q tests/test_legacy_runtime_removal.py tests/test_check_workflow.py tests/test_pack_asset_validation.py`
- [x] `SP208-T5` 将 checker/schema 收敛到 18/8，并将 duplicate 与 closure 降为 advisory。 Covers: B-004, B-011, B-014, B-016, B-018 | Owner: primary | Dependencies: SP208-T3, SP208-T4 | Done when: 文件计数硬检查通过，无 wrapper/搬家规避，adopted missing 与 not-adopted 路径有相反测试 | Verify: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py tests/test_pack_asset_validation.py tests/test_duplicate_work_gate.py tests/test_closure_audit.py tests/test_skill_size_gate.py`
- [x] `SP208-T6` 缩减 skills/docs：queue ≤200 行、implx ≤60 行、fastlane read set ≤3 文件/12 KiB，只对 heavy 默认独立 spec。 Covers: B-001, B-002, B-007, B-012, B-013, B-015, B-016, B-019 | Owner: primary | Dependencies: SP208-T1, SP208-T4, SP208-T5 | Done when: docs/token/hash/size tests 通过，技能不再引用删除的 runtime/tier/review-round artifact | Verify: `/usr/bin/python3 -m pytest -q tests/test_review_contract_docs.py tests/test_skill_size_gate.py tests/test_install_codex_skills.py`
- [ ] `SP208-T7` 在现有 installer 内实现只读 installed-skill hash doctor，不新增 gate 或迁移状态机。 Covers: B-004, B-017, B-018 | Owner: primary | Dependencies: SP208-T5 | Done when: `--check-installed` 一次报告全部 missing/drift，匹配返回 0，dry-run/apply 边界不变 | Verify: `/usr/bin/python3 -m pytest -q tests/test_install_codex_skills.py`
- [ ] `SP208-T8` 完成三 profile E2E、全量回归、tree/manifest 对账和 release handoff。 Covers: B-001, B-002, B-003, B-005, B-008, B-010, B-014, B-015, B-020 | Owner: primary | Dependencies: SP208-T1, SP208-T2, SP208-T3, SP208-T4, SP208-T5, SP208-T6, SP208-T7 | Done when: E2E、pack/all-specs、全 pytest、size gate、diff-check 全绿且修改路径位于 manifest 闭集 | Verify: `python3 checks/check_workflow.py --repo . --all-specs && /usr/bin/python3 -m pytest -q && python3 checks/skill_size_gate.py --repo . --json && git diff --check origin/main...HEAD`

## 并行拆分

本计划由单一 primary agent 顺序执行，不启动并行 writable lanes。T1-T7 共享
`workflow.yaml`、pack validator、skills 和测试契约；并行编辑会违反显式文件
所有权和 W-14。只读 review 可在实现完成后独立进行，但不得修改工作树。

## 验证

Product invariant 集为 B-001 至 B-020，任务 Covers 并集必须完整覆盖。每个任务在
进入下一任务前运行 focused tests 并按 fixflow `per_step` commit。最终运行：

- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `/usr/bin/python3 -m pytest -q`
- `python3 checks/skill_size_gate.py --repo . --json`
- `git diff --check origin/main...HEAD`

## Handoff Notes

- 用户已批准 GH208 缩减设计并授权进入实现；GitHub merge、关闭 Issue、关闭
  PR #198 仍在最终外部动作前回显精确清单。
- commit policy 为 `per_step`；每个 `SP208-T<n>` focused tests 通过后单独提交。
- 旧 runtime/checkpoint/tier artifact 是明确 breaking removal，不实现兼容层。
- 安全敏感路径、人工 merge gate、force-push/权限/安全披露禁令必须保留。
