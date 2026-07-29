# Task Plan

## Linked Issue

GH-86

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP86-T1` 重写 `skills/specrail-write-product-spec/SKILL.md`：长度启发式、边界穷尽清单、worked example、密度规则、稳定 ID 纪律。Covers: B-001 B-002 B-003 B-004 B-005。Owner: agent. Done when: 四个新小节齐备且保留 route gate/locale 既有纪律. Verify: 按 tech.md 映射逐条人工复核
- [ ] `SP86-T2` 重写 `skills/specrail-write-tech-spec/SKILL.md`：锚点纪律、全量映射、worked mapping 示例。Covers: B-006 B-007。Owner: agent. Done when: 禁猜锚点与禁 TBD 措辞齐备. Verify: 按 tech.md 映射逐条人工复核
- [ ] `SP86-T3` 更新 `specrail-plan-tasks` 的全量 invariant 覆盖纪律，并同步改六个模板（product/tech/tasks × en/zh-CN）：B-xxx 格式、边界清单表、Covers 标注。Covers: B-008 B-009 B-012。Owner: agent. Done when: task skill 会阻止 Covers 遗漏，且两套 locale 逐文件节数节序一致. Verify: 人工复核 product ID 集与 task Covers 并集相等，并逐对复核六个模板的节结构与表格列
- [ ] `SP86-T4` 重算三个变更 skill 的 sha256 并写回 `skills-lock.json`；CHANGELOG Unreleased 加条目。Covers: B-011。Owner: agent. Done when: lock 哈希与文件一致. Verify: `python3 checks/check_workflow.py --repo .`

## 并行拆分

单人串行执行；T1/T2/T3 文件集互不重叠，T4 依赖 T1/T2/T3 完成后的最终字节。

## 验证

- [ ] `SP86-T5` 全量回归与自举确认。Covers: B-010。Owner: agent. Done when: 三条命令全绿. Verify: `python3 checks/check_workflow.py --repo . --all-specs && python3 checks/check_workflow.py --repo . --spec-dir specs/GH86 && uvx pytest -q`

## Handoff Notes

- 深度门禁（invariant 计数、锚点 grep 校验、边界覆盖率）显式排除在本 issue 外，Phase 2 另行立项时以 GH86 的产出分布做阈值标定。
- worked example 素材源自 GH59 盲测实验（深 spec 命中 PR #83 才修的 D2 漏洞），实验记录见 issue #86 正文。
