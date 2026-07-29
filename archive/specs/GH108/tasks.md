# Task Plan

## Linked Issue

GH-108

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP108-T001` 从最新 `origin/main` 创建 implementation 分支，记录 `impl_base_sha` 与唯一 Python interpreter，并在任何编辑前保存 runtime normalized node multiset 与全库 collection count；随后提取唯一 helper，按 core、full-queue/budget、review/lane-failure 拆分。 Covers: B-001, B-002, B-003 | Owner: implementation | Dependencies: spec PR merged, issue `ready_to_implement` | Done when: pre-edit guard 证明实际 runtime 基线仍为 66 functions / 73 cases（否则停止更新 spec）、helper 无重复定义、每个相关测试文件与 `tests/runtime_ledger_test_support.py` 均低于 800 行 | Verify: 按 `tech.md` Deterministic Parity Procedure 步骤 1-2 生成 pre-edit evidence，并在拆分完成后执行步骤 6 的逐文件 `< 800` 行 gate
- [ ] `SP108-T002` 对比拆分前后的完整 runtime collection、全部顶层函数 AST 与 production symbol identity，并阻断 skip/xfail。 Covers: B-001, B-004 | Owner: verification | Dependencies: SP108-T001 | Done when: normalized node multiset 无差异；70-function AST mapping 完全相等；`evaluate_checkpoint`、gate/specrail_lib symbols 仍绑定生产对象；无 module/function skip/xfail | Verify: 执行 `tech.md` Deterministic Parity Procedure 步骤 3-5、7，两个 `diff -u` 为空、AST parity 输出 70 functions、production identity 通过、focused summary 无 skipped/xfailed/xpassed
- [ ] `SP108-T003` 运行 focused 与 repository 全量验证并记录 fresh 输出。 Covers: B-005 | Owner: verification | Dependencies: SP108-T001, SP108-T002 | Done when: 使用 `/tmp/gh108-python-bin.txt` 中同一解释器；focused tests 全通过、全库 collected count 与 `impl_base_sha` 基线相等、全量 pytest、all-spec workflow check 与 whitespace check 全部通过 | Verify: `python_bin=$(cat /tmp/gh108-python-bin.txt) && "$python_bin" -m pytest -q tests/test_runtime_ledger*.py && "$python_bin" -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`
- [ ] `SP108-T004` 完成 committed scope 审计与 SpecRail implementation handoff。 Covers: B-002, B-003, B-004, B-005 | Owner: coordinator | Dependencies: SP108-T003 | Done when: changed paths 全部属于四文件 allowlist、protected paths 相对 `impl_base_sha` 无 committed diff、验证证据与风险说明完整、未越过 final review/merge gate | Verify: 执行 `tech.md` Deterministic Parity Procedure 步骤 6，确认 `/tmp/gh108-unexpected-paths.txt` 为空，再运行 `python3 checks/check_workflow.py --repo . --spec-dir specs/GH108`

## 并行拆分

本项串行执行。所有测试模块共享同一 helper 与同一基线函数集合，并行写入会增加重复
定义或漏迁移风险；单一 implementation owner 完成 T001，verification owner 再执行
T002-T004。

## 验证

- 编辑前后 normalized runtime node multiset diff（预期为空）
- `impl_base_sha` 与工作树的逐测试函数 AST mapping equality check
- 编辑前后全库 collected test count equality check
- `python_bin=$(cat /tmp/gh108-python-bin.txt) && "$python_bin" -m pytest -q tests/test_runtime_ledger*.py`
- `python_bin=$(cat /tmp/gh108-python-bin.txt) && "$python_bin" -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH108`
- `git diff --check`

## Handoff Notes

- Spec 编写基线：`origin/main@f3251fe`；原文件 1063 行、66 个 `test_*` 函数、
  pytest 收集 73 cases；全库初始基线为 421 passed。implementation 以其实际
  `impl_base_sha` fresh collection 为权威，固定 421 不能作为未来下限。
- tasks 按用户要求与 product/tech 同一 spec PR 提交；当前 issue 仍为
  `ready_to_spec`，不得把 task plan 视为 `ready_to_implement` 或 spec approval。
- spec PR 合并并由维护者设置 `ready_to_implement` 后，implementation 必须重新
  fetch `origin/main` 并从该时刻最新提交创建独立分支。
- Product ID set: `{B-001, B-002, B-003, B-004, B-005}`；task coverage union:
  `{B-001, B-002, B-003, B-004, B-005}`。
