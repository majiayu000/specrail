# Task Plan

## Linked Issue

GH-141

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP141-T1` 新建 `checks/rejection_items.py`：`make_item`（闭集 category、四字段非空、占位值拒绝）、`finalize_items`（按 item_id 去重排序）、`load_prior_rejection`（fail-closed 转 config_error item）、`repeat_rejection`（item_id+expected+found 全等比对）；配套 `tests/test_rejection_items.py`。Covers: B-002 B-003 B-004 B-005 B-006 B-009。Owner: agent. Done when: 单元测试覆盖全部构造/去重/比对/fail-closed 分支且全绿. Verify: `python3 -m pytest -q tests/test_rejection_items.py`
- [ ] `SP141-T2` `checks/route_gate.py` 接入：`evaluate_route()` 与 `blocked_result()` 输出 `rejection_items`（allowed 为空数组；早退路径含结构化单项），`main()` 增加 `--prior-rejection` 与 `repeat_rejection` 段；既有字段与退出码不动。Covers: B-001 B-007 B-008 B-010 B-011 B-012。Owner: agent. Done when: 新增用例通过且既有 route_gate 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_route_gate.py tests/test_route_gate_sensitive.py`
- [ ] `SP141-T3` `checks/review_json_gate.py` 接入：`evaluate_review_gate()` 产出 items，`main()` 增加 `--prior-rejection`，load 失败分支产出 config_error item。Covers: B-001 B-005 B-006 B-007 B-008。Owner: agent. Done when: 新增用例通过且既有 review_json_gate 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_review_json_gate.py`
- [ ] `SP141-T4` `checks/pr_review_contract.py` + `checks/sensitive_enforcement.py` + `checks/pr_gate.py` 全量驳回源接入：contract 汇总附带 items；`evaluate_sensitive_evidence`（`checks/sensitive_enforcement.py:501`）附带 items；pr_gate 其余全部自有来源同步 itemize——内联字段检查（`checks/pr_gate.py:213-249`）、`_check_items`（:46）、`_issue_reference_items`（:74）、`_merge_record_items`（:148）、`_authorization_item`（:187）、sensitive 分支（:273-312）、`main()` ValueError 早退分支（:393-404，产出单条 config_error item）；`main()` 增加 `--prior-rejection` 与 `repeat_rejection` 段。Covers: B-001 B-004 B-005 B-006 B-007 B-010。Owner: agent. Done when: 逐来源 fixture 断言每类来源至少产出一条 item（`test_pr_gate_all_sources_emit_items`），pr_gate 输出含去重后的 rejection_items，且既有用例零改动全绿. Verify: `python3 -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py`
- [ ] `SP141-T5` 端到端两轮验证：构造多缺失 fixture，第一轮拿全量清单、单轮补齐、第二轮通过；构造重复驳回 fixture 验证 `repeat_rejection` 段。Covers: B-001 B-005 B-012。Owner: agent. Done when: 两个 fixture 场景断言通过. Verify: `python3 -m pytest -q tests/test_rejection_items.py -k "two_round or repeat"`
- [ ] `SP141-T6` 编排消费面接线（U-26）：在含 gate 调用命令的 SKILL.md 中增补统一约定——gate 驳回时调用方把输出 JSON 持久化到 `.specrail/runtime/rejections/<gate>-<issue|pr>.json`，同一 issue/PR 的下一轮重试对同一 gate 传 `--prior-rejection <该文件>`，并说明 `repeat_rejection` 命中时按契约违规上报而非继续重试。修改文件：`skills/specrail-diagnose-ci/SKILL.md`、`skills/specrail-implement-queue/SKILL.md`、`skills/specrail-implement/SKILL.md`、`skills/specrail-plan-tasks/SKILL.md`、`skills/specrail-pr-gate/SKILL.md`、`skills/specrail-release-note/SKILL.md`、`skills/specrail-review-pr/SKILL.md`、`skills/specrail-triage-issue/SKILL.md`、`skills/specrail-write-product-spec/SKILL.md`、`skills/specrail-write-tech-spec/SKILL.md`。Covers: B-005 B-011（持久化由编排方执行，gate 本身仍只读）。Owner: agent. Done when: 上述 10 个 SKILL.md 均含 `--prior-rejection` 重试约定且 workflow 校验通过. Verify: `grep -l -- --prior-rejection skills/specrail-{diagnose-ci,implement-queue,implement,plan-tasks,pr-gate,release-note,review-pr,triage-issue,write-product-spec,write-tech-spec}/SKILL.md | wc -l | grep -qx 10 && python3 checks/check_workflow.py --repo .`

## 并行拆分

T1 先行；T2/T3/T4 文件不相交可并行（route_gate.py / review_json_gate.py / pr_review_contract.py+sensitive_enforcement.py+pr_gate.py）；T5 依赖 T1-T4；T6 只改 skills/*/SKILL.md，与 T2-T4 文件不相交，依赖 T1-T4 确定的 CLI 面后执行。

## Verification

- `python3 -m pytest -q tests/test_rejection_items.py tests/test_route_gate.py tests/test_review_json_gate.py tests/test_pr_gate.py`
- `python3 checks/check_workflow.py --repo .`

## Handoff Notes

- repeat_rejection 是信号不改判 decision；编排方（implement/review lane）消费后自行升级处理。
- `evaluate_review_contract` 返回形态扩展方式（第四返回位 vs 伴生函数）由实现者按 `checks/pr_gate.py:261` 消费面选择，两者均不得破坏既有三元组调用。
