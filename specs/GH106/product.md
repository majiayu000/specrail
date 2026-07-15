# Product Spec

## Linked Issue

GH-106

## 用户问题

GH104 之后的 `implx auto` run 仍把四类事项当成 `human_decisions` 上报并等待
批准（2026-07-15 remem drain 实测），用户明确表示这些在 auto 模式下不应
需要批准：

1. spec 覆盖已 complete 的 issue 仍等人工打 `ready_to_implement` readiness
   label（#817-#820）。
2. 两条独立 reviewer lane 均失败后，coordinator self-review 仍要求逐次显式
   授权（#837）。
3. 同 owner 的跨仓库工作被当作未授权边界（#720 涉及 refine 仓库）。
4. 弃用窗口的起始版本要求用户指定（#684）。

每类都让整条队列停摆等一句"批准"，与 auto 模式"一句话跑到底"的目标矛盾。

## 目标

以下规则全部仅在 `auth_mode: auto` 生效：

- readiness gate：spec coverage 为 `complete` 的 issue，agent 自行添加
  readiness label 并继续实现；label 事件即审计记录。
- self-review：两条不同的独立 reviewer lane 失败且已按协议记录
  `lane_failures[]` 后，implx auto 调用本身构成 scoped self-review
  authorization；照常记录 `review_source: self_review` 与
  `self_review_authorization`（actor: user、source: implx auto invocation、
  scope: 该 PR 与双 lane 失败路径）。
- 跨仓库：目标 issue 队列显式引用、且与主仓库同一 GitHub owner 的仓库，
  视为在授权范围内；跨 owner 仍需人工。
- 弃用版本：用户未指定时，默认以当前最新 release 的下一个 minor 版本为
  移除窗口起点，记录进 checkpoint 与 PR 描述；用户可事后否决。

## 非目标

- review 模式行为完全不变：以上四类仍需人工。
- 不放宽：破坏性或不可逆操作、发布、跨 owner 仓库、架构级重写、
  maintainer waiver、probe/time-window gate。
- 不修改 `checks/` 代码：`self_review_authorization` 与
  `human_authorization` 的 evidence 结构不变，auto 模式只是改变授权来源。

## Behavior Invariants

1. B-001 readiness 自动放行仅当：`auth_mode: auto` 且该 issue 的
   `spec_status` 为 `complete`（或 `umbrella_covered`）。`needs_spec` /
   `needs_tasks` 的 issue 不得自动打 readiness label。
2. B-002 自动打 label 后必须在 checkpoint 该 issue 项记录
   `readiness_label_source: auto_drain`，报告中列出所有自动打的 label。
3. B-003 self-review 自动授权仅当：`auth_mode: auto`、同一 PR 已有至少两条
   **不同**独立 reviewer lane 失败、每条失败均已记录 `lane_failures[]`。
   授权对象照常写入 `self_review_authorization`，scope 必须点名 PR 与
   失败路径；单条 lane 失败后直接 self-review 仍被禁止。
4. B-004 跨仓库自动授权仅当：目标仓库与主仓库同 GitHub owner，且该工作由
   队列内 issue 显式引用。跨 owner、或队列外的仓库工作仍进
   `human_decisions`。
5. B-005 弃用窗口默认值仅当用户未指定：取当前最新 release 的下一个 minor
   版本，写入 checkpoint 与 PR 描述并标注 `deprecation_default: true`；
   执行移除本身仍受既有 gate 约束。
6. B-006 review 模式下四类行为与现状完全一致。
7. B-007 不变式：破坏性/不可逆操作、发布、force-push、删除未合并分支、
   替换 maintainer PR 的既有边界逐字保留。
