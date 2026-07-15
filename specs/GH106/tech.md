# Tech Spec

## Linked Issue

GH-106

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| auto human-decision 列表 | `skills/implx/SKILL.md` | 四类事项进 `human_decisions` 等人 | 需缩小该列表并声明四条自动放行规则 |
| Reviewer-Lane Failure Protocol | `skills/specrail-implement-queue/SKILL.md` | self-review 需失败后新取得的显式授权 | 双 lane 失败 + auto 调用即构成 scoped 授权 |
| Spec Coverage Gate / route gate | `skills/specrail-implement-queue/SKILL.md` | readiness label 缺失 → needs_human | complete spec 在 auto 下可自打 label |
| Boundaries | 两个 SKILL.md | "act outside the repository" 一律禁止 | 同 owner 跨仓库需划出授权子集 |
| Evidence 结构 | `checks/pr_gate.py`、`checks/runtime_ledger_gate.py` | `self_review_authorization{actor,source,scope}` 必填 | 结构不变，auto 模式填充来源即可，无代码改动 |
| Skill hash lock | `skills-lock.json` | 记录 SKILL.md sha256 | 变更后刷新 |

## 设计方案

### 1. implx auto bullet（`skills/implx/SKILL.md`）

在 auto 模式列表中新增"auto-mode standing authorizations"块，声明四条
自动放行规则（B-001..B-005）及其边界（B-006/B-007），并把
`human_decisions` 的定义收窄为：破坏性/不可逆、发布、跨 owner、架构级
重写、maintainer waiver、probe/time-window gate、证据不足的 spec。

### 2. Readiness 自动放行（`specrail-implement-queue/SKILL.md` Spec Coverage Gate）

补充：`auth_mode: auto` 且 `spec_status: complete|umbrella_covered` 时，
缺失 readiness label 不再是 blocker——agent 添加 label、记录
`readiness_label_source: auto_drain`、继续路由（B-001/B-002）。

### 3. Post-failure self-review（同文件 Reviewer-Lane Failure Protocol）

补充：`auth_mode: auto` 下，同一 PR 两条不同独立 lane 失败且
`lane_failures[]` 完整后，implx auto 调用构成 scoped
`self_review_authorization`（actor: user、source: implx auto invocation、
scope: 点名 PR 与失败路径）。单 lane 失败仍走换 lane 重试；silent
substitution 禁令原句保留（B-003）。

### 4. 同 owner 跨仓库（两个 SKILL.md Boundaries）

把"never act outside the repository without explicit instruction"细化：
auto 模式下，队列 issue 显式引用的同 owner 仓库在授权范围内；跨 owner
或队列外仓库仍禁止（B-004）。

### 5. 弃用窗口默认值（`specrail-implement-queue/SKILL.md` Queue Planning）

新增一句：auto 模式弃用类任务无用户指定版本时，默认下一个 minor 为窗口
起点，`deprecation_default: true` 记录进 checkpoint 与 PR 描述（B-005）。

### 6. 锁文件

刷新 `skills-lock.json` 两个 SKILL.md 的 hash。

## 风险与兼容

- gate 代码零改动：`pr_gate.py` 只校验 `self_review_authorization` 三字段
  非空，`runtime_ledger_gate.py` 校验 lane_failures 与授权存在性；auto
  填充的对象满足同一 schema。
- review 模式路径不进入任何新分支（B-006）。
- 文本变更；验证以 pack 校验 + 全量 pytest + hash 一致性为准。
