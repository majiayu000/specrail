# Task Plan

## Linked Issue

GH-120

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP120-T001` 从最新 `origin/main` 创建 implementation 分支，在编辑前记录 `impl_base_sha`、唯一 `uvx pytest` 入口、37-case normalized node multiset 与全库 553-case count；随后提取唯一 support，并按 sensitive 与 general 两个主题拆分。 Covers: B-001, B-002, B-003 | Owner: implementation | Done when: 实际基线仍为 31 test functions / 37 cases / 5 helpers / 36 functions（否则先更新 spec），三文件均 `<800`，helper 无重复 | Verify: `tech.md` Deterministic Parity Procedure 步骤 1-3、6
- [ ] `SP120-T002` 对比全部顶层函数 AST、production symbol identity，并阻断 skip/xfail。 Covers: B-004 | Owner: verification | Done when: 36-function mapping 完全相等，关键 production objects identity 相同，support 无测试 | Verify: `tech.md` 步骤 4-5
- [ ] `SP120-T003` 运行 focused 与 repository 全量验证。 Covers: B-001, B-005 | Owner: verification | Done when: 37 focused cases 无 skip/xfail/xpass，全库保持 553 passed，workflow 与 whitespace 全绿 | Verify: `tech.md` 步骤 7
- [ ] `SP120-T004` 完成 committed scope 审计与 implementation handoff。 Covers: B-002, B-003, B-004, B-005 | Owner: coordinator | Done when: changed paths 精确属于三文件 allowlist，protected paths 无 diff，PR 记录 base、原因、计划、风险与验证 | Verify: `tech.md` 步骤 6及 `python3 checks/check_workflow.py --repo . --spec-dir specs/GH120`

## 并行拆分

implementation 串行执行。三个文件共享同一 helper 集合和 parity baseline，并行写入会增加
重复定义或漏迁移风险；单一 implementation owner 完成 T001，独立 reviewer 只读验证
T002-T004。

## 验证

- 编辑前后 normalized node multiset 与全库 collected count diff 为空
- 36-function AST mapping 与 production symbol identity 通过
- `uvx pytest -q -r a tests/test_route_gate*.py`
- `uvx pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH120`
- `impl_base_sha=$(cat /tmp/gh120-impl-base-sha.txt) && git diff --check "$impl_base_sha"...HEAD`

## Handoff Notes

- Spec 基线为 `origin/main@a899c558`：1023 行、31 个 test functions、37 focused cases、
  5 个 helpers、36 个顶层函数、553 full passed；implementation 以实际 base fresh evidence 为权威。
- 精确 implementation allowlist 仅为 tech manifest 的三个测试/support 路径。
- Spec PR 合并且 Issue #120 进入 `ready_to_implement` 后，才能从当时最新 `origin/main`
  创建独立 implementation 分支。
- Product ID set 与 task coverage union 均为 `{B-001, B-002, B-003, B-004, B-005}`。
