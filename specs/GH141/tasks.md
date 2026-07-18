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
- [ ] `SP141-T4` `checks/pr_review_contract.py` + `checks/pr_gate.py` 接入：contract 汇总附带 items 并入 pr gate 输出。Covers: B-001 B-004 B-007。Owner: agent. Done when: pr_gate 输出含去重后的 rejection_items 且既有用例零改动全绿. Verify: `python3 -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py`
- [ ] `SP141-T5` 端到端两轮验证：构造多缺失 fixture，第一轮拿全量清单、单轮补齐、第二轮通过；构造重复驳回 fixture 验证 `repeat_rejection` 段。Covers: B-001 B-005 B-012。Owner: agent. Done when: 两个 fixture 场景断言通过. Verify: `python3 -m pytest -q tests/test_rejection_items.py -k "two_round or repeat"`

## 并行拆分

T1 先行；T2/T3/T4 文件不相交可并行（route_gate.py / review_json_gate.py / pr_review_contract.py+pr_gate.py）；T5 依赖 T1-T4。

## Verification

- [ ] `python3 -m pytest -q tests/test_rejection_items.py tests/test_route_gate.py tests/test_review_json_gate.py tests/test_pr_gate.py`
- [ ] `python3 checks/check_workflow.py --repo .`

## Handoff Notes

- repeat_rejection 是信号不改判 decision；编排方（implement/review lane）消费后自行升级处理。
- `evaluate_review_contract` 返回形态扩展方式（第四返回位 vs 伴生函数）由实现者按 `checks/pr_gate.py:261` 消费面选择，两者均不得破坏既有三元组调用。
