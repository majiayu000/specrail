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

以下规则全部仅在 `auth_mode: auto` 生效（auto-mode standing
authorizations，全部 scoped to this run）：

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
- 不改变 PR tier lanes（GH143 fastlane/standard/heavy）的 gate 强度：tier
  只决定流程重量，四条自动放行规则不因 tier 增减证据要求。

## Behavior Invariants

1. B-001 readiness 自动放行仅当：`auth_mode: auto` 且该 issue 的
   `spec_status` 为 `complete`（或 `umbrella_covered`）。`needs_spec` /
   `needs_tasks` 的 issue 不得自动打 readiness label。
2. B-002 当自动打 label 后，必须在 checkpoint 该 issue 项记录
   `readiness_label_source: auto_drain`，报告中列出所有自动打的 label。
3. B-003 self-review 自动授权仅当：`auth_mode: auto`、同一 PR 已有至少两条
   **不同**独立 reviewer lane 失败、每条失败均已记录 `lane_failures[]`。
   授权对象照常写入 `self_review_authorization`，scope 必须点名 PR 与
   失败路径；单条 lane 失败后直接 self-review 仍被禁止（先换一条独立
   lane 重试一次），silent self-review substitution 禁令逐字保留。
4. B-004 跨仓库自动授权仅当：目标仓库与主仓库同 GitHub owner，且该工作由
   队列内 issue 显式引用。跨 owner、或队列外的仓库工作仍进
   `human_decisions`。
5. B-005 弃用窗口默认值仅当用户未指定：取当前最新 release 的下一个 minor
   版本，写入 checkpoint 与 PR 描述并标注 `deprecation_default: true`；
   执行移除本身仍受既有 gate 约束，用户可事后否决默认值。
6. B-006 当 `auth_mode: review` 时，四类行为与现状完全一致：readiness
   label 仍是人工 gate、失败后 self-review 仍需失败上报后新取得的显式
   授权、仓库外工作一律需人工指示、弃用版本需用户指定。
7. B-007 不变式：破坏性/不可逆操作、发布、force-push、删除未合并分支、
   替换 maintainer PR 的既有边界逐字保留；跨 owner 仓库任何时候都需要
   显式人工指示。
8. B-008 auto 只能由当前用户消息显式说 `implx auto` / `implx 自动` 选择；
   仓库持久化的 `automation_policy.auth_mode` 是 review 安全基线，永不
   选择或授权 auto；四条 standing authorizations 全部只覆盖本次 run。
9. B-009 evidence 结构零改动：`self_review_authorization{actor,source,
   scope}` 与 `lane_failures[]` schema 不变；`pr_gate.py` 阻断缺
   `review_source` 的证据，`runtime_ledger_gate.py` 阻断未授权 self-review
   合并与未上报的 lane 失败——自动授权路径必须通过同一套校验。

## Acceptance Criteria

- [ ] auto + complete/umbrella_covered → 自动打 readiness label 并记录
      `readiness_label_source: auto_drain`；needs_spec/needs_tasks 不放行
- [ ] auto + 双独立 lane 失败 + `lane_failures[]` 完整 → implx auto 调用即
      scoped self-review 授权；单 lane 失败不适用
- [ ] auto + 同 owner + 队列 issue 显式引用 → 跨仓库放行；跨 owner 仍人工
- [ ] auto + 用户未指定 → 弃用窗口默认下一 minor，`deprecation_default:
      true` 记录在案
- [ ] review 模式四类行为零回归
- [ ] skills-lock hash 与改动文件一致

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 B-005（缺 readiness label 在 auto 下不再是 blocker 但仅限 complete/umbrella 覆盖；用户缺省版本时用显式记录的默认值，不留空猜测） |
| Error / failure paths | covered: B-003 B-009（lane 失败必须记 `lane_failures[]` 才进入自动授权前置；未上报失败被 ledger gate 阻断） |
| Authorization / permission | covered: B-003 B-004 B-008（自动授权来源仅现时 `implx auto` 消息；持久化配置永不授权 auto；跨 owner 永远人工） |
| Concurrency / race | N/A: 四条规则均为 coordinator 单点决策，不引入新的并行写入面；lane 并行归 queue skill 既有 ownership 规则 |
| Retry / idempotency | covered: B-003（单 lane 失败先换独立 lane 重试一次；重复打同一 readiness label 幂等且审计记录不重复计数） |
| Illegal state transitions | covered: B-001 B-003（needs_spec/needs_tasks → readiness 是被禁止的转移；单 lane 失败 → self-review 是被禁止的捷径） |
| Compatibility / migration | covered: B-006 B-009（review 模式零回归；evidence schema 不变，既有 gate 代码无需迁移） |
| Degradation / fallback | covered: B-003 B-005（self-review 是双 lane 失败后的显式降级路径，必须带授权记录；弃用默认值显式标注 `deprecation_default: true` 而非静默选择） |
| Evidence / audit integrity | covered: B-002 B-009（`readiness_label_source: auto_drain` 与报告清单留痕；`pr_gate.py`/`runtime_ledger_gate.py` 校验授权与失败记录完整性） |
| Cancellation / interruption | covered: B-005 B-008（用户可事后否决弃用默认值；standing authorizations 随 run 结束失效，不跨 run 存续） |

## Rollout Notes

先合 queue skill 三处条文（Spec Coverage Gate、Reviewer-Lane Failure
Protocol、Queue Planning），再改 implx 入口 standing authorizations 块与
Boundaries，最后刷新 skills-lock。合并后三台机器重装 skills。
