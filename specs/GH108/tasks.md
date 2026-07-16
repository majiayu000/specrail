# Task Plan

## Linked Issue

GH-108

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP108-T001` 提取唯一 runtime ledger 测试 helper，并按 core、full-queue/budget、review/lane-failure 边界拆分测试模块。 Covers: B-001, B-002, B-003, B-004 | Owner: implementation | Dependencies: none | Done when: helper 无重复定义、全部 66 个测试函数只出现一次、每个相关文件低于 800 行、生产与 fixture 文件未修改 | Verify: `wc -l tests/test_runtime_ledger*.py && rg --no-filename '^def test_' tests/test_runtime_ledger*.py | sort`
- [ ] `SP108-T002` 对比拆分前后的函数集合、参数化收集数与断言迁移。 Covers: B-001, B-004 | Owner: verification | Dependencies: SP108-T001 | Done when: 基线与工作树 `test_*` 名称集合无差异、pytest 收集 73 cases、没有新增 skip/xfail 或弱化断言 | Verify: `/usr/bin/python3 -m pytest --collect-only -q tests/test_runtime_ledger*.py && git diff --word-diff=plain f3251fe -- tests/test_runtime_ledger*.py`
- [ ] `SP108-T003` 运行 focused 与 repository 全量验证并记录 fresh 输出。 Covers: B-005 | Owner: verification | Dependencies: SP108-T001, SP108-T002 | Done when: focused tests、421+ 全量 tests、all-spec workflow check 与 whitespace check 全部通过 | Verify: `/usr/bin/python3 -m pytest -q tests/test_runtime_ledger*.py && /usr/bin/python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`
- [ ] `SP108-T004` 完成 scope 审计与 SpecRail implementation handoff。 Covers: B-002, B-003, B-004, B-005 | Owner: coordinator | Dependencies: SP108-T003 | Done when: implementation PR 只含批准的 test-only 范围、验证证据与风险说明完整、未越过 final review/merge gate | Verify: `git diff --name-only f3251fe...HEAD && python3 checks/check_workflow.py --repo . --spec-dir specs/GH108`

## 并行拆分

本项串行执行。所有测试模块共享同一 helper 与同一基线函数集合，并行写入会增加重复
定义或漏迁移风险；单一 implementation owner 完成 T001，verification owner 再执行
T002-T004。

## 验证

- `/usr/bin/python3 -m pytest --collect-only -q tests/test_runtime_ledger*.py`
- `/usr/bin/python3 -m pytest -q tests/test_runtime_ledger*.py`
- `/usr/bin/python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH108`
- `git diff --check`

## Handoff Notes

- Spec 编写基线：`origin/main@f3251fe`；原文件 1063 行、66 个 `test_*` 函数、
  pytest 收集 73 cases；全库基线为 421 passed。
- tasks 按用户要求与 product/tech 同一 spec PR 提交；当前 issue 仍为
  `ready_to_spec`，不得把 task plan 视为 `ready_to_implement` 或 spec approval。
- spec PR 合并并由维护者设置 `ready_to_implement` 后，implementation 必须重新
  fetch `origin/main` 并从该时刻最新提交创建独立分支。
- Product ID set: `{B-001, B-002, B-003, B-004, B-005}`；task coverage union:
  `{B-001, B-002, B-003, B-004, B-005}`。
