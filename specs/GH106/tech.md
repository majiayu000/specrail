# Tech Spec

## Linked Issue

GH-106

## Product Spec

Link to `product.md`.

## Codebase Context

锚点按当前实现现场核实（2026-07-19，`origin/main` c0be38f）。

| Area | Anchor | Current behavior | Why relevant |
| --- | --- | --- | --- |
| standing authorizations 块 | `skills/implx/SKILL.md:77-84` | auto bullet 声明四条自动放行（readiness label、双 lane 失败后 scoped self-review、同 owner 跨仓库、弃用默认下一 minor），全部 scoped to this run | B-001 B-003 B-004 B-005 入口条文 |
| human_decisions 收窄 | `skills/implx/SKILL.md:85-90` | 仅破坏性/不可逆、maintainer waiver、probe/time-window、冲突反馈、架构级重写、跨 owner、证据不足的 spec 进 human_decisions | B-004 B-007 |
| 同 owner 边界 | `skills/implx/SKILL.md:105-111` | "never act outside the repository" 细化：auto 下同 owner + 队列 issue 显式引用在授权范围内，跨 owner 一律人工 | B-004 B-007 |
| auto 选择来源 | `skills/implx/SKILL.md:52-55`（queue skill 侧 `skills/specrail-implement-queue/SKILL.md:188-191`） | 持久化 `automation_policy.auth_mode` 是 review 安全基线；auto 仅由现时消息 `implx auto` 选择，不从配置提升 | B-008 |
| readiness 自动放行 | `skills/specrail-implement-queue/SKILL.md:79-85` | auto + complete/umbrella_covered → 补 label、记 `readiness_label_source: auto_drain`、报告列出；needs_spec/needs_tasks 永不放行 | B-001 B-002 |
| 弃用窗口默认值 | `skills/specrail-implement-queue/SKILL.md:141-146` | 用户未指定 → 下一 minor，`deprecation_default: true` 记入 checkpoint 与 PR 描述，移除仍受既有 gate | B-005 |
| 双 lane 失败例外 | `skills/specrail-implement-queue/SKILL.md:596-608` | auto + 两条不同独立 lane 失败 + `lane_failures[]` 完整 → implx auto 调用即 scoped 授权（actor: user、source: implx auto invocation）；单 lane 失败仍需重试 lane；review 模式不适用 | B-003 B-006 |
| lane 失败校验 | `checks/runtime_gate_rules.py:79`（`_validate_lane_failures`）、`checks/runtime_gate_rules.py:133`（`_has_self_review_authorization`） | 校验 `lane_failures[]` 字段完整性与 `self_review_authorization` 存在性，阻断未授权 self-review 与未上报失败 | B-009（零代码改动的校验面） |
| PR 证据 review_source | `checks/pr_gate.py:388` | 证据对象透传 `review_source`；缺失即被 gate 阻断 | B-009 |

## 设计方案

### 1. implx auto bullet（`skills/implx/SKILL.md:77-90`）

auto 模式列表中的 "auto-mode standing authorizations" 块声明四条自动放行
规则（B-001..B-005）及其边界（B-006/B-007/B-008），并把 `human_decisions`
的定义收窄为：破坏性/不可逆、发布、跨 owner、架构级重写、maintainer
waiver、probe/time-window gate、证据不足的 spec。

### 2. Readiness 自动放行（`specrail-implement-queue/SKILL.md:79-85`）

`auth_mode: auto` 且 `spec_status: complete|umbrella_covered` 时，缺失
readiness label 不再是 blocker——agent 添加 label、记录
`readiness_label_source: auto_drain`、继续路由（B-001/B-002）。review
模式下 readiness label 仍是人工 gate（B-006）。

### 3. Post-failure self-review（`specrail-implement-queue/SKILL.md:596-608`）

`auth_mode: auto` 下，同一 PR 两条不同独立 lane 失败且 `lane_failures[]`
完整后，implx auto 调用构成 scoped `self_review_authorization`
（actor: user、source: implx auto invocation、scope: 点名 PR 与失败
路径）。单 lane 失败仍走换 lane 重试；silent substitution 禁令原句保留
（B-003）。

### 4. 同 owner 跨仓库（`skills/implx/SKILL.md:105-111` 与 queue skill Boundaries）

"never act outside the repository without explicit instruction" 细化：
auto 模式下，队列 issue 显式引用的同 owner 仓库在授权范围内；跨 owner
或队列外仓库仍禁止（B-004）。

### 5. 弃用窗口默认值（`specrail-implement-queue/SKILL.md:141-146`）

auto 模式弃用类任务无用户指定版本时，默认下一个 minor 为窗口起点，
`deprecation_default: true` 记录进 checkpoint 与 PR 描述（B-005）。

### 6. 锁文件

刷新 `skills-lock.json` 两个 SKILL.md 的 hash。

## 风险与兼容

- gate 代码零改动：`checks/pr_gate.py:388` 只透传并要求 `review_source`，
  `checks/runtime_gate_rules.py:79`/`:133` 校验 `lane_failures[]` 与
  `self_review_authorization` 三字段非空；auto 填充的对象满足同一 schema
  （B-009）。
- review 模式路径不进入任何新分支（B-006）。
- 文本变更；验证以 pack 校验 + 全量 pytest + hash 一致性为准。
