# Task Plan

## Linked Issue

GH-127

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP127-T001` 从最新 `origin/main` 创建 implementation 分支，在编辑前固定 Python 3.13.11 / pytest 9.1.1，记录 69 focused nodes、553 full count 与 focused outcomes；提取唯一 support 并按 general/terminal 主题拆分。 Covers: B-001, B-002, B-005 | Owner: implementation | Done when: 三文件均 `<800`，collection/outcomes 不变 | Verify: tech 步骤 1-3、6
- [ ] `SP127-T002` 证明基线同名定义位于 396/617，仅删除较早遮蔽定义，并对保留 54 个函数执行完整 AST parity。 Covers: B-003, B-004 | Owner: verification | Done when: 51 tests + 3 helpers 名称唯一、AST 相等、0 skip/xfail、无 pytestmark | Verify: tech 步骤 4
- [ ] `SP127-T003` 验证 production identity、full pytest 与 workflow。 Covers: B-004, B-005 | Owner: verification | Done when: 真实 objects identity、553 full、single/all-spec 全绿 | Verify: tech 步骤 5-6
- [ ] `SP127-T004` 完成 scope 与 handoff。 Covers: B-002, B-005 | Owner: coordinator | Done when: committed paths 精确为 manifest 三路径，protected paths 无 diff，PR 写明原因/计划/风险/验证 | Verify: tech 步骤 6

## 并行拆分

implementation 串行执行；三个文件共享同一 baseline/函数集合。独立 reviewer 只读验证。

## Handoff Notes

- Spec 基线：`origin/main@bf86866`，887 行、55 FunctionDef statements、54 unique names、
  52 test definitions、51 unique test names、3 helpers、69 collected、0 skip/xfail、553 full。
- 唯一允许删除的是第 396 行、被第 617 行同名定义遮蔽且从未收集的函数。
- implementation allowlist 仅为 tech manifest 的三个路径。
- Product ID set 与 task coverage union 均为 `{B-001, B-002, B-003, B-004, B-005}`。
