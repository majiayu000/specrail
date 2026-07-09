# Product Spec

## Linked Issue

GH-86

## 用户问题

SpecRail 生成的 spec 系统性偏浅：14 篇 product.md 中 13 篇落在 45-84 行，长度与功能复杂度脱钩。根因是深度载体错位——模板是 38 行填空框架，write skill 只有 34-36 行且只说"填模板"，模型对每个标题做最小填充（slot completion），模板成为深度天花板。浅 spec 的直接代价已被盲测实验证实：GH59 的历史浅 spec 对"已授权 self_review 在无 lane 失败记录时仍通过 gate"这一真实缺陷只有 PARTIAL 覆盖，照字面实现正好产出该漏洞（PR #83 才修）；同一 issue 用深方法盲写的 spec 以 B-022 精确命中。

本变更把深度从模板搬回 skill prompt：worked example、边界穷尽清单、长度启发式、稳定 invariant ID 与全量映射纪律，写进两个 write skill 与两套 locale 模板。

## 目标

- spec 深度与功能复杂度重新挂钩：复杂 gate/合同类 issue 产出边界穷尽的 spec，trivial issue 不被逼着注水。
- 让"漏掉的边界"从静默遗漏变成显式论证：每个边界类别要么有 invariant，要么写明 N/A + 原因。
- 让 spec→测试可机械追溯：稳定 B-xxx ID 贯穿 product → tech mapping → tasks。

## 非目标

- 不新增任何门禁/检查逻辑（深度门禁是 Phase 2，另行立项）。
- 不回改已有 specs/GH*（历史 spec 保持原样，check_workflow 不校验 invariant ID 格式）。
- 不改 `checks/`、`workflow.yaml`、`states.yaml`、`labels.yaml` 的任何行为。
- 不引入英文 EARS 语法的强制要求（两种 locale 各自允许自然的"当/若…系统应…"或"When/If…the system shall…"措辞）。

## Behavior Invariants

以下"写作者"指按 skill 指引写 spec 的 agent；"skill"指 `specrail-write-product-spec` / `specrail-write-tech-spec` 的 SKILL.md。

1. B-001 product skill 必须内嵌一个完整 worked example：编号 invariant 不少于 10 条、展示边界组合枚举（失败模式 × 授权状态 × 证据字段状态这类交叉），并至少含一条显式 "N/A + 原因" 的边界声明，使写作者有可模仿的密度锚点。
2. B-002 product skill 必须包含显式密度指令：产出的 invariant 密度以 worked example 为基准，而不是以模板留白为基准；禁止"每个标题填 1-2 条即完成"的最小填充。
3. B-003 product skill 必须包含长度启发式：trivial（单文件小修）→ 最小 spec 并在头部声明 `complexity: trivial`；小功能 → 约 30-60 行；中等 → 约 80-150 行；大功能 → 更长。长度由复杂度驱动，禁止为凑行数注水。
4. B-004 product skill 必须给出边界穷尽清单（至少 10 类：空/缺失输入、错误与失败路径、授权/权限、并发/竞态、重试/重复、非法状态转换、兼容/迁移、降级/回退、证据与审计完整性、取消/中断），并要求写作者对每一类给出"已覆盖(列出 B-xxx)"或"N/A + 原因"，不允许静默跳过。
5. B-005 product spec 的 behavior invariant 必须使用稳定 ID（B-001 起连续编号）；后续修订只追加不重排，已发布的 B-xxx 含义不得复用给不同行为。
6. B-006 tech skill 必须要求 Codebase Context 中每个文件引用为写作时已核实的 `path:line` 锚点（用 Read/grep 验证后写入）；禁止凭记忆猜测路径或行号；无法核实的引用必须删除或降级为"待定位"。
7. B-007 tech skill 必须要求 Product-to-Test Mapping 覆盖 product spec 的全部 B-xxx（无孤儿 invariant），且每行 Verification 为可执行命令或可人工复核的具体步骤，不得为空或 TBD。
8. B-008 tasks 模板与 skill 指引必须让每个实现任务行标注 `Covers: B-xxx`（可多个）；与任何 invariant 无关的基建任务标注 `Covers: none` 并给一句原因。
9. B-009 两套 locale 模板（`templates/` 与 `templates/zh-CN/`）在本变更后保持标题结构一致；稳定 ID、路径、命令、JSON key、状态与路由名一律保持英文，不随 locale 翻译。
10. B-010 本变更落地后，`specs/GH86/` 自身的 spec packet 必须是用新方法写成的合格样本（含 B-xxx ID、边界清单表、全量映射），作为自举验证。
11. B-011 `skills-lock.json` 中两个 write skill 的 computedHash 必须与更新后的 SKILL.md 内容一致，`check_workflow.py` 校验通过；lock 中其余 12 个 skill 的条目不受影响。
12. B-012 修改后的 `templates/*/tasks.md` 生成的任务行仍满足 `validate_task_plan` 的既有约束（反引号稳定 ID + Owner/Done when/Verify），`Covers:` 是追加字段而非替代。

## 边界情况清单

| 类别 | 判定 |
| --- | --- |
| 空/缺失输入 | 已覆盖：B-003（trivial issue 的最小 spec 路径，避免"无内容硬写"） |
| 错误与失败路径 | 已覆盖：B-006（锚点无法核实时的处理：删除或显式待定位，禁止猜测） |
| 授权/权限 | N/A：本变更不触碰任何授权/gate 语义（见非目标） |
| 并发/竞态 | N/A：纯文档/模板变更，无运行时并发面 |
| 重试/重复 | 已覆盖：B-005（修订追加不重排，防 ID 复用歧义） |
| 非法状态转换 | N/A：不改 states.yaml/workflow.yaml 状态机 |
| 兼容/迁移 | 已覆盖：B-009（locale 结构对齐）、非目标（历史 spec 不回改，check_workflow 不校验 ID 格式故旧 spec 不受影响） |
| 降级/回退 | 已覆盖：B-003（trivial 声明即降级路径，避免规则绝对化） |
| 证据与审计完整性 | 已覆盖：B-011（lock 哈希与内容一致）、B-004（边界不允许静默跳过） |
| 取消/中断 | N/A：无长时任务或会话状态 |

## 验收标准

- [ ] `skills/specrail-write-product-spec/SKILL.md` 满足 B-001~B-005；`skills/specrail-write-tech-spec/SKILL.md` 满足 B-006~B-007。
- [ ] 六个模板文件（product/tech/tasks × 两套 locale）满足 B-008、B-009、B-012。
- [ ] `skills-lock.json` 满足 B-011，`python3 checks/check_workflow.py --repo . --all-specs` 通过。
- [ ] `uvx pytest -q` 通过（本变更不应引起任何测试变化）。
- [ ] `specs/GH86/` 自身满足 B-010。

## 发布说明

对已安装 `~/.codex/skills` / Claude 侧副本的用户：需要重跑 `python3 tools/install_codex_skills.py --repo . --apply` 才能拿到新版 write skill。历史 spec 无需迁移。
