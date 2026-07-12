# Tech Spec

## Linked Issue

GH-86

## Product Spec

`specs/GH86/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| product write skill | `skills/specrail-write-product-spec/SKILL.md:10-28` | 7 步流程，第 5-6 步只要求"编号、可测、无实现细节"，无范例、无密度/长度指引 | 深度载体，本变更主体 |
| tech write skill | `skills/specrail-write-tech-spec/SKILL.md:10-27` | 8 步流程，第 5 步要求 codebase context 但未要求核实 `path:line`，第 6 步映射未要求全量覆盖 | 锚点纪律与全量映射写入点 |
| task planning skill | `skills/specrail-plan-tasks/SKILL.md:10-27` | 要求稳定 task ID、Owner/Done when/Verify，但未要求 task 覆盖全部 product invariant | B-008 的 product→task 覆盖纪律写入点 |
| product 模板 | `templates/product_spec.md:19-26`、`templates/zh-CN/product_spec.md:19-25` | Behavior Invariants 段仅一句状态类别提示 + `1.` 占位 | 加 B-xxx ID 约定与边界清单表 |
| tech 模板 | `templates/tech_spec.md:21-25`、`templates/zh-CN/tech_spec.md:21-25` | Product-to-Test Mapping 表头用 `P1` 占位 | 改为 `B-001` 并要求全量覆盖 |
| tasks 模板 | `templates/tasks.md:14-19`、`templates/zh-CN/tasks.md:14-18` | 任务行无 Covers 标注 | 加 `Covers: B-xxx` 追加字段（B-008） |
| lock 校验 | `checks/specrail_lib.py:599-601` | computedHash 与 SKILL.md 字节 sha256 严格比对，不符即 error | B-011 的确定性验证依据 |
| lock 条目 | `skills-lock.json:36-38`、`skills-lock.json:66-73` | 两个 write skill 与 plan-tasks skill 各有一条 `computedHash` | skill 更新后必须再生 |
| task plan 校验 | `checks/check_workflow.py:288-314` | 每个 `- [` 行需反引号 `SP<issue>-T<n>` ID + Owner/Done when/Verify | B-012：Covers 必须是追加而非替代 |
| 安装器 | `tools/install_codex_skills.py:95` | 安装后按 `sha256:` + hexdigest 复核 | 发布说明中重装路径的依据 |

## 设计方案

深度全部写进 skill prompt，模板只承担结构（与根因诊断一致：模板 = 结构，skill = 深度）：

1. `specrail-write-product-spec/SKILL.md` 重写为约 150 行：保留现有 Steps 与 Boundaries 骨架（route gate 命令、locale 规则、linked issue 纪律不变），新增四个小节——Length heuristic（表格，含 `complexity: trivial` 声明式降级）、Boundary checklist（10 类，逐类"covered(B-xxx) 或 N/A + reason"）、Worked example（从 GH59 盲测深 spec 提炼约 35 行：≥10 条编号 invariant，含组合边界与一条 N/A 声明）、Density rule（"match the example's density, not the template's emptiness"）。
2. `specrail-write-tech-spec/SKILL.md` 重写为约 100 行：新增 Anchor discipline（所有 `path:line` 写入前用 Read/grep 核实，禁猜，未核实即删或标"待定位"）、Full-coverage mapping（映射表必须枚举 product spec 全部 B-xxx，Verification 禁空/禁 TBD）、一段 worked mapping 示例行。
3. `specrail-plan-tasks/SKILL.md` 增加全量 invariant→task 覆盖纪律；六个模板同步小改：product 模板的 invariant 段改为 `1. B-001 …` 格式示意 + 边界清单表骨架；tech 模板映射列头 `P1` → `B-001`；tasks 模板任务行示例加 `Covers: B-xxx`。两套 locale 改动逐标题对齐。
4. 重算三个变更 skill 的 sha256 写回 `skills-lock.json`；CHANGELOG Unreleased 加条目。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 worked example | product SKILL.md | 人工复核：范例含 ≥10 条编号 invariant、≥1 条 N/A 声明、含组合边界 |
| B-002 密度指令 | product SKILL.md | 人工复核：存在显式 density rule 措辞 |
| B-003 长度启发式 | product SKILL.md | 人工复核：四档长度表 + `complexity: trivial` 降级路径 |
| B-004 边界穷尽清单 | product SKILL.md | 人工复核：≥10 类清单 + "covered 或 N/A+reason" 强制措辞 |
| B-005 稳定 ID 纪律 | product SKILL.md + product 模板 | 人工复核：追加不重排、不复用的措辞存在 |
| B-006 锚点纪律 | tech SKILL.md | 人工复核：核实后写入/禁猜/无法核实即删的措辞存在 |
| B-007 全量映射 | tech SKILL.md + tech 模板 | 人工复核：无孤儿 B-xxx、Verification 禁 TBD 措辞存在 |
| B-008 Covers 标注 | `specrail-plan-tasks` + tasks 模板 ×2 | 人工复核全量覆盖纪律与模板示例行；`specs/GH86/tasks.md` 自身即样本 |
| B-009 locale 对齐 | 六个模板 | 人工复核：两套 locale 逐文件节数、节序、表格结构一致（标题文字随 locale 语言，不做字面 diff） |
| B-010 自举样本 | `specs/GH86/` | `python3 checks/check_workflow.py --repo . --spec-dir specs/GH86` 通过 + 本 packet 含 B-xxx/边界表/全量映射 |
| B-011 lock 哈希 | `skills-lock.json` | `python3 checks/check_workflow.py --repo .` 通过（三个变更 skill 均由 specrail_lib.py 严格比对） |
| B-012 task plan 兼容 | tasks 模板 ×2 | `python3 checks/check_workflow.py --repo . --all-specs` 通过（含用新模板写的 GH86 tasks） |

## 数据流

无运行时数据流变化。写作期数据流：issue 文本 + 代码库（Read/grep 核实锚点）→ write skill 指引 → product/tech → plan-tasks 全量 Covers 映射 → spec packet 三文件；安装期：SKILL.md → sha256 → skills-lock.json → `install_codex_skills.py` 分发校验。

## 备选方案

- 把 worked example 放进模板而非 skill：否决——模板会被逐字复制进每个 spec packet，范例会污染产出物；skill 只在写作时加载。
- 强制 EARS 英文语法：否决——中英混排仓库会造成 zh-CN spec 误判，且 Warp 证明自然语言编号 invariant 足够（见非目标）。
- 同时加深度门禁（invariant 计数、锚点 grep 校验）：否决——先验证新 prompt 的真实产出分布再定阈值，Phase 2 立项。

## 风险

- Security: 无——纯文档/模板/哈希更新，不触碰 gate 语义。
- Compatibility: 历史 spec 用 `P1` 映射 ID，check_workflow 不校验 ID 格式，不受影响；已安装的旧版 skill 需重装才生效（发布说明覆盖）。
- Performance: 写一份深 spec 的 agent 成本上升（实验实测约 14 万 token）；由 B-003 的 trivial 降级路径控制，只有复杂 issue 付这个成本。
- Maintenance: worked example 引用的是抽象化的 gate 场景而非真实文件行号，不随代码演进腐烂。

## 测试计划

- [ ] Unit tests: 无新增（不改任何 Python 逻辑）；`uvx pytest -q` 全量回归确认零影响。
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`（覆盖 B-010/B-011/B-012）。
- [ ] Manual verification: 按 Product-to-Test Mapping 逐条复核两个 SKILL.md 与六个模板；locale 标题对齐用 B-009 的 diff 命令。

## 回滚方案

`git revert` 单个 PR 即可整体回滚（skill、模板、lock、CHANGELOG 在同一提交序列）；已安装副本重跑 `python3 tools/install_codex_skills.py --repo . --apply` 恢复旧版。无数据迁移。
