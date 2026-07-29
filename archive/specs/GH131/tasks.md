# Task Plan

## Linked Issue

GH-131

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP131-T1` 在 `checks/runtime_gate_rules.py` 的 `_validate_self_review_authorization` 增加 auto 模式双 lane 断言（去重、非空白、大小写不敏感、错误含实际计数），`checks/runtime_ledger_gate.py` 调用点传入 `auth_mode`；`tests/test_runtime_ledger_review.py` 新增 B-002…B-007 回归。Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008。Owner: agent. Done when: Product-to-Test Mapping 全部验证通过. Verify: `python3 -m pytest -q tests/test_runtime_ledger_review.py tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_queue.py`

## 并行拆分

单任务无并行。
