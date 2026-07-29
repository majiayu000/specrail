# Task Plan

## Linked Issue

GH-117

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP117-T001` 从最新 `origin/main` 创建 implementation 分支，在编辑前记录 `impl_base_sha`、唯一 Python、79-case normalized node multiset 与全库 collection count；随后提取唯一 support 并按 approval/snapshot、core relation/review、CLI/query 拆分。 Covers: B-001, B-002, B-003 | Owner: implementation | Done when: 实际基线仍为 42 test functions / 79 cases（否则先更新 spec），四文件均 `<800`，helper 无重复 | Verify: `tech.md` Deterministic Parity Procedure 步骤 1-3、6
- [ ] `SP117-T002` 对比全部顶层函数 AST、production symbol identity，并阻断 skip/xfail。 Covers: B-004 | Owner: verification | Done when: 50-function mapping 完全相等，列出的 production objects 均 identity 相同，support 无测试 | Verify: `tech.md` 步骤 4-5
- [ ] `SP117-T003` 运行 focused 与 repository 全量验证。 Covers: B-001, B-005 | Owner: verification | Done when: 79 focused cases 无 skip/xfail/xpass，全库 count 与实际 base 相等，全量 pytest、workflow 与 whitespace 全绿 | Verify: `tech.md` 步骤 7
- [ ] `SP117-T004` 完成 committed scope 审计与 implementation handoff。 Covers: B-002, B-003, B-004, B-005 | Owner: coordinator | Done when: changed paths 精确属于四文件 allowlist，protected paths 无 diff，PR 记录 base、原因、计划、验证与风险，且未越过 review/merge 人工门禁 | Verify: `tech.md` 步骤 6及 `python3 checks/check_workflow.py --repo . --spec-dir specs/GH117`

## 并行拆分

implementation 串行执行。四个文件共享同一 helper 集合和同一 parity baseline，并行写入
会增加重复定义或漏迁移风险；单一 implementation owner 完成 T001，独立 reviewer
只读验证 T002-T004。

## 验证

- 编辑前后 normalized node multiset 与全库 collected count diff 为空
- 50-function AST mapping 与 production symbol identity 通过
- `python_bin=$(cat /tmp/gh117-python-bin.txt) && "$python_bin" -m pytest -q -r a tests/test_github_pr_evidence*.py`
- `python_bin=$(cat /tmp/gh117-python-bin.txt) && "$python_bin" -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH117`
- `impl_base_sha=$(cat /tmp/gh117-impl-base-sha.txt) && git diff --check "$impl_base_sha"...HEAD`

## Handoff Notes

- Spec 基线为 `origin/main@3547af8`：1281 行、42 个 tests、8 个 helpers、79 focused
  cases、553 full collected；implementation 以当时实际 `impl_base_sha` fresh evidence
  为权威。
- 精确 implementation allowlist 仅为 tech manifest 的四个测试/support 路径。
- Spec PR 合并并由维护者确认 `ready_to_implement` 后，才能从当时最新 `origin/main`
  创建独立 implementation 分支。
- Product ID set 与 task coverage union 均为 `{B-001, B-002, B-003, B-004, B-005}`。
