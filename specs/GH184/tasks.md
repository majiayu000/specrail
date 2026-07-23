# Task Plan

## Linked Issue

GH-184

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [x] `SP184-T1` 将 `_check_items`、`_issue_reference_items`、`_merge_record_items` 移入新模块 `checks/pr_evidence_items.py`，`checks/pr_gate.py` 改为导入并删除随之失效的 `CHECK_PASS_CONCLUSIONS` / `MERGE_PATHS`。纯移动，不改函数体。Covers: 前置约束（800 行硬上限）。Owner: implementation lane。Depends on: none。Done when: `pr_gate.py` ≤ 800 行且既有测试全绿。Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo .`。
- [x] `SP184-T2` 新增 `checks/checks_availability.py`：实现封闭字段校验与 fail-closed 返回。Covers: B-004 B-005 B-006 B-007 B-008 B-009。Owner: implementation lane。Depends on: none。Done when: 非法声明的每一类都有负例。Verify: `python3 -m pytest -q tests/test_pr_gate.py -k checks_unavailable`。
- [x] `SP184-T3` 在 `checks/pr_evidence_items.py::_check_items` 接入委派，并对「checks 非空却声明 checks_unavailable」追加 reason。Covers: B-001 B-002 B-003。Owner: implementation lane。Depends on: T1 T2。Done when: 空列表委派、缺失/类型错误走原路径、并存即拒绝三种情形均有测试。Verify: `python3 -m pytest -q tests/test_pr_gate.py`。
- [x] `SP184-T4` 扩展 `schemas/pr_review_gate.schema.json` 并补 schema 测试，保持文件 ≤ 800 行。Covers: B-011。Owner: schema lane。Depends on: T2 字段契约。Done when: schema 接受合法声明、拒绝四类非法变体。Verify: `python3 -m pytest -q tests/test_specrail_schema.py && python3 checks/check_workflow.py --repo .`。
- [x] `SP184-T5` 更新 `skills/specrail-review-pr/SKILL.md` 与 `skills/specrail-pr-gate/SKILL.md`，并重算 `skills-lock.json`。Covers: 产品目标第 4 条。Owner: contract lane。Depends on: T2。Done when: review skill 写明结构性 CI 缺失不得重开 round，pr-gate skill 写明封闭字段与 `degraded:` 读法，lock hash 与文件一致。Verify: `python3 checks/check_workflow.py --repo .`。
- [x] `SP184-T6` 端到端验证：全量测试、workflow check、spec depth、whitespace。Covers: B-001..B-011。Owner: coordinator。Depends on: T1–T5。Done when: 全绿且未弱化任何既有断言。Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH184 --gate && git diff --check`。

## 并行拆分

T1 是纯移动，必须先落地；T2 与 T4 可并行（共享字段契约）；T3 依赖 T1/T2；T5 只动 skills 与 lock；T6 收口。lane 之间无共享可写文件。

## Verification

- `python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH184 --gate`
- `git diff --check`

## Handoff Notes

- 该降级路径只覆盖 `hosted_ci_not_triggered_for_base` 一种原因；新增原因需要新的 spec 与 schema 变更。
- 首选动作始终是修复消费仓库的 workflow 触发条件（参考 majiayu000/rnk#81），声明是次选。
- 降级不改变 human merge authorization；`degraded:` 条目必须在报告中如实呈现。
