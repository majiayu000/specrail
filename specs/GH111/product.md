# Product Spec

## Linked Issue

GH-111

## 用户问题

用户对 SpecRail 治理仓库说"做一个 goal 一直优化这个库……每次改动做 issues、
spec PRs 和 impl PRs"，没有提到 implx。但 `specrail-implement-queue` 的
description（"implementing or draining a GitHub issue/PR queue in a
SpecRail-governed repository"）被这句描述性语言隐式命中，skill 带着
`auth_mode` 默认 review 的状态机进场，goal 长跑被逐 PR 授权反复打断
（2026-07-16 apple/remem 实测，2h22m 内多次停等确认）。

用户预期：implx 是"提到才调用"的 skill；不提 implx 时，不应被 implx 或
队列 skill 的授权状态机接管。

## 目标

- SpecRail skill 家族改为 invocation-scoped：
  - `specrail-implement-queue` 仅当被 implx 显式委派、或用户明确点名该
    skill 时使用；不再被描述性语言隐式触发。
  - 其余 specrail-* 单件 skills 的 description 加同等 explicit-invocation
    限定（被 workflow 路由或其他 SpecRail skill 显式委派也算显式）。
  - `specrail-workflow` 路由条目同步：向队列 skill 的路由仅在用户点名
    implx / 队列 skill 时发生。
- 不经 implx 的工作路径：agent 遵守仓库 AGENTS.md / workflow.yaml 既有
  约定（spec 先行、gate 脚本、合并纪律），但不启动队列编排、不进入
  auth_mode 状态机、不发出逐 PR 授权询问。
- implx 显式路径行为不变。

## 非目标

- 不修改 `checks/` gate 代码与 CI 行为。
- 不改变 implx 被调用后的任何规则（auth_mode、rollover、goal 接线、
  standing authorizations）。
- 不修改消费仓库的 AGENTS.md。

## 记录的 Trade-off

不经 implx 的自由跑失去队列编排保护层（checkpoint 记账、reviewer-lane
强制、spec/impl mix gate）；CI gate 脚本与仓库约定仍兜底。用户知情并接受
（见 issue #111）。

## Behavior Invariants

1. B-001 `specrail-implement-queue` 的 description 声明仅两种触发：implx
   显式委派、用户明确点名该 skill；并明确排除"优化这个库/做完这些
   issue"类描述性语言。
2. B-002 全部其余 specrail-* skills 的 description 含 explicit-invocation
   限定语；SpecRail skill 之间的显式委派链（如 implx → queue → implement）
   不受影响。
3. B-003 `specrail-workflow` 的路由条目改为：只有用户点名 implx 或队列
   skill 时才路由到队列编排；其余 SpecRail 仓库工作走单件 skill 或普通
   agent 行为。
4. B-004 implx 自身触发条件与被调用后的全部行为逐字不变。
5. B-005 skills-lock 哈希与改动文件一致。
