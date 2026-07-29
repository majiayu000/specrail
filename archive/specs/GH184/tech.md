# Tech Spec

## Linked Issue

GH-184

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":184,"complete":true,"paths":["checks/checks_availability.py","checks/pr_evidence_items.py","checks/pr_gate.py","schemas/pr_review_gate.schema.json","skills-lock.json","skills/specrail-pr-gate/SKILL.md","skills/specrail-review-pr/SKILL.md","tests/test_pr_gate.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH184/product.md","specs/GH184/tech.md","specs/GH184/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Required change |
| --- | --- | --- | --- |
| checks 校验 | `checks/pr_gate.py:244`（变更前）→ `checks/pr_evidence_items.py:28` | 空 `checks` 直接 `missing: checks` | 空列表时委派给声明校验（`checks/pr_evidence_items.py:36`）；缺失/类型错误仍走原路径 |
| 并存冲突 | `checks/pr_evidence_items.py:41` | 不存在该字段，无冲突判定 | `checks` 非空却声明降级时追加 reason |
| 声明校验器 | `checks/checks_availability.py:36` | 不存在 | 新增封闭字段校验，枚举定义在 `checks/checks_availability.py:20`，降级文案在 `checks/checks_availability.py:118` |
| gate 入口体积 | `checks/pr_gate.py:45` | 856 行，超过仓库 800 行硬上限 | 三个证据字段校验器外移并改为导入，入口降至 718 行 |
| PR 证据 schema | `schemas/pr_review_gate.schema.json:516` | 顶层 `additionalProperties: false`，未知字段拒绝 | 声明封闭的 `checks_unavailable` 对象 |
| review 契约 | `skills/specrail-review-pr/SKILL.md:93` | 未区分「CI 未通过」与「CI 不可能运行」 | 增加结构性不可用判定与「不得为此重开 round」 |
| gate 使用说明 | `skills/specrail-pr-gate/SKILL.md:110` | 只描述 CI rollup 必须存在 | 说明降级声明的封闭字段与 `degraded:` 读法 |

## 设计方案

### 1. 模块拆分（前置，非行为变更）

`checks/pr_gate.py` 在 main 上已是 856 行，超过 `check_workflow.py` 的 800 行硬上限，任何新增都会加重违规。将同类的证据字段校验器 `_check_items`、`_issue_reference_items`、`_merge_record_items` 整体移入新模块 `checks/pr_evidence_items.py`，`pr_gate.py` 改为导入。移动后 `CHECK_PASS_CONCLUSIONS` 与 `MERGE_PATHS` 在入口不再被引用，一并删除（`closure_audit.py` 自带同名常量，不受影响）。

`pr_gate.py` 由 856 行降至 718 行，`pr_evidence_items.py` 166 行，行为逐字不变。

### 2. 声明校验器

新增 `checks/checks_availability.py`，导出 `evaluate_checks_unavailable(evidence)`，返回与其它校验器一致的 `(satisfied, missing, reasons)` 三元组。校验顺序：

1. 声明缺失 → 原始 `missing: checks` + `CI/check evidence is missing`（B-002）。
2. 声明非对象 → reason + `missing: checks`（B-004）。
3. 字段集合封闭校验（B-004）、`reason` 枚举（B-005）、两个 ref 的存在性/一致性/互异性（B-006）、`workflow_trigger_evidence` / `local_verification` / `verified`（B-007）。
4. 任一 missing 或 reason 非空 → 追加 `missing: checks` 并返回，不产出 satisfied（B-008）。
5. 全通过 → 单条 `degraded:` satisfied（B-009）。

gate 不读取 GitHub、不解析 workflow 文件：`workflow_trigger_evidence` 是采集方提供的可审计字符串，不是可执行断言。

### 3. 接入点

`pr_evidence_items._check_items` 中：`checks` 为空**列表**时委派给 `evaluate_checks_unavailable`；`checks` 缺失或类型错误保持原路径（B-003）。`checks` 非空且同时出现 `checks_unavailable` 时追加 reason（B-001）。

### 4. Schema

`schemas/pr_review_gate.schema.json` 增加封闭的 `checks_unavailable` 属性（`additionalProperties: false`，`reason` 为单值 enum，`verified` 为 `const: true`，`local_verification` 为 `minItems: 1`）。`checks` 仍是 required，空数组仍合法（B-011）。插入块采用紧凑格式，使文件保持 781 行、低于 800 行上限。

### 5. 决策语义

该路径只影响 `_check_items` 的输出。`decision` 仍由既有聚合逻辑决定：确定性 missing/reasons 为空且 `human_authorization` 缺失时仍是 `needs_human`（B-010）。降级不授予合并权。

## 风险

1. 采集方可能对「未触发」与「未完成」判断错误，把普通 CI 缺失声明为结构性。
   - 缓解：`reason` 单值枚举 + 要求 `base_ref != default_base_ref` + 要求引用触发条件原文；skill 明确禁止用于 pending/failed CI。
2. 降级被下游读成 CI 通过。
   - 缓解：satisfied 文本强制 `degraded:` 前缀并写明原因，两个 skill 均要求按降级报告。
3. 模块拆分与其它进行中的 `pr_gate.py` 改动冲突。
   - 缓解：拆分为纯移动，不改函数体；冲突时以移动后的模块为准重放对方改动。
