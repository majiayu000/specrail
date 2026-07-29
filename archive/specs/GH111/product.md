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

1. B-001 当用户输入只包含描述性语言（如"优化这个库""做完这些 issue"
   "drain 队列式的工作描述"）而未点名 implx 或该 skill 时，
   `specrail-implement-queue` 不得激活；其 description 声明仅两种触发：
   implx 显式委派、用户明确点名该 skill。
2. B-002 全部其余 specrail-* skills 的 description 含 explicit-invocation
   限定语（"Explicit invocation only: … do not self-activate from
   descriptive language."）；SpecRail skill 之间的显式委派链（如 implx →
   queue → implement）不受影响。
3. B-003 当多个 approved specs 就绪但用户未点名 implx / 队列 skill 时，
   `specrail-workflow` 路由不得指向队列编排：逐 issue 走
   `specrail-implement`，或仅提示用户 implx 可用；只有点名才路由到
   `specrail-implement-queue`。
4. B-004 implx 自身触发条件与被调用后的全部行为逐字不变：说 implx /
   implx auto 时进入的状态机、授权规则与现状完全一致。
5. B-005 skills-lock 哈希与改动文件一致；任何 SKILL.md description 变更
   后必须刷新对应 sha256。
6. B-006 当工作不经 implx 进行时，agent 仍遵守仓库 AGENTS.md /
   workflow.yaml 既有约定（spec 先行、gate 脚本、合并纪律），但不启动
   队列编排、不进入 auth_mode 状态机、不发出逐 PR 授权询问。
7. B-007 当消费仓库的 AGENTS.md 显式引导使用队列 skill 时，该引导构成
   显式委派，仍然生效——invocation-scoped 限定只排除描述性语言的隐式
   命中，不排除任何显式委派来源。
8. B-008 隐式触发被排除后不得出现中间态：要么普通 agent 行为（B-006），
   要么显式调用后的完整队列状态机（B-004）；不存在"部分接管"（如只做
   checkpoint 不做授权询问，或只发授权询问不做记账）的降级形态。
9. B-009 explicit-invocation 限定只追加限定语，不改写各 skill 原有语义
   描述内容（人类可读性与既有触发说明保留）。

## Acceptance Criteria

- [ ] `specrail-implement-queue` description 含 ONLY-explicit 限定与
      描述性语言排除条款
- [ ] 其余 12 个 specrail-* skills description 均含 explicit-invocation
      限定语
- [ ] `specrail-workflow` 路由：点名才路由队列 skill；未点名时逐 issue
      implement 或提示 implx
- [ ] `git diff skills/implx/` 为空（implx 行为零改动）
- [ ] skills-lock hash 与全部改动文件一致

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 B-006（用户输入缺少 implx / skill 点名时不激活队列编排，回落为普通 agent 行为，不猜测意图） |
| Error / failure paths | covered: B-006（不经 implx 的路径失去编排保护层后由 CI gate 脚本与仓库约定兜底，失败仍被 gate 显式拦截而非静默通过） |
| Authorization / permission | covered: B-004 B-006（auth_mode 授权状态机仅在显式调用后进场；未点名时不得发出逐 PR 授权询问，也不得替用户批准任何合并） |
| Concurrency / race | N/A: 触发判定是单次路由决策，无共享可变状态；并行 lane 规则归队列 skill 被显式调用后的既有条文 |
| Retry / idempotency | covered: B-001 B-003（同一描述性输入重复出现时判定结果稳定一致：始终不触发队列 skill；点名判定不受会话历史影响） |
| Illegal state transitions | covered: B-008（描述性语言 → 队列状态机是被禁止的转移；"部分接管"中间态不存在，只有普通行为或完整状态机两态） |
| Compatibility / migration | covered: B-004 B-007 B-009（implx 显式路径零回归；消费仓库 AGENTS.md 显式委派继续生效；原语义描述保留，无需消费方迁移） |
| Degradation / fallback | covered: B-006（不经 implx 是用户知情选择的显式降级：失去 checkpoint 记账 / reviewer-lane 强制 / mix gate，由 CI 与仓库约定兜底，trade-off 成文） |
| Evidence / audit integrity | covered: B-005（skills-lock sha256 与 SKILL.md 内容一致是变更完整性的机械证据；hash 不一致即安装校验失败） |
| Cancellation / interruption | N/A: 触发判定为瞬时决策，无长事务可取消；被显式调用后的中断语义归 implx / 队列 skill 既有条文 |

## Rollout Notes

先改队列 skill description，再批量单件 skills，再 workflow 路由，最后刷新
skills-lock。合并后三台机器重装 skills。效果：不提 implx 的长期目标不再被
队列 skill 的 review 状态机接管；说 implx / implx auto 时行为与现在完全
一致。
