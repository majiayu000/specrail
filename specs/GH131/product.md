# Product Spec

## Linked Issue

GH-131

## 用户问题

PR #107 把 auto 模式的自审替代收窄为窄条件 standing authorization："同一 PR 上两条不同独立审查 lane 失败后，implx auto 调用本身构成 scoped 自审授权；单条 lane 失败仍必须走重试 lane"。但 `checks/runtime_gate_rules.py` 只校验 `lane_failures` 非空（>=1 条）。契约说"两条不同 lane"，gate 只查"至少一条"——历史会话记录中已发生过两次把合并授权误记为自审授权的语义滑坡。自然语言契约需要机器断言兜底，让 gate 而非文字承担这条边界。

## 目标

- checkpoint `auth_mode: auto` 下的 self_review 合并证据必须满足"两条不同 lane 失败"的契约条件，否则 ledger gate 阻断。

## 非目标

- 不改 `skills/` 契约文本（#107 已定稿）。
- 不对 `scope`/`conversation_marker` 自由文本做启发式内容判定。
- 不改 `auth_mode: review`（含缺省）路径的任何行为。
- 不改 `pr_review_contract.py` 的 PR 证据层校验。

## Behavior Invariants

1. B-001 当 checkpoint 缺少 `auth_mode` 或其值为 `review` 时，self_review 授权校验行为应与现状完全一致（lane_failures >=1 条 + scope/marker 非空）。
2. B-002 当 `auth_mode: auto` 且 merge-ready item 的 `review_source: self_review` 且 `lane_failures` 中不同 `lane_id` 数少于 2 时，gate 应输出指明"需要两条不同失败 lane"的错误并判定 blocked。
3. B-003 当 `auth_mode: auto` 且 self_review item 记录了至少 2 个不同 `lane_id` 的失败时，该断言应不新增错误，既有其余校验（scope/marker、human_final_review_required、terminal review）照常执行。
4. B-004 如果 `lane_failures` 含两条记录但 `lane_id` 相同，应计为 1 条不同 lane，不满足 auto 自审条件。
5. B-005 若失败记录的 `lane_id` 缺失或为空白字符串，该记录应不计入不同 lane 数（既有的 lane_id 必填错误照常报出）。
6. B-006 `auth_mode` 值比较应大小写与首尾空白不敏感（`"AUTO"`、`" auto "` 等同 `"auto"`）。
7. B-007 该断言应只在 merge-ready 证据路径（`merge_ready`/`ready_to_merge`/`merged`，或 `complete` 且带 pr）上触发；`planning`/`blocked`/`needs_human` 等状态不受影响。
8. B-008 阻断错误信息应包含实际观测到的不同 lane 数，便于修复方定位缺口。

## Acceptance Criteria

- [ ] auto + self_review + 单条 lane 失败 → blocked，错误指明需两条不同 lane
- [ ] auto + self_review + 两条不同 lane 失败 → gate 结论与现状一致（allowed/warn）
- [ ] auto + self_review + 同一 lane_id 两条记录 → blocked
- [ ] 无 auth_mode / review 模式：全部既有 self_review 用例行为不变

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 B-005（auth_mode 缺省与 lane_id 空白） |
| Error / failure paths | covered: B-002 B-008 |
| Authorization / permission | covered: B-002 B-003（自审授权即本 spec 主题） |
| Concurrency / race | N/A: 纯函数校验，无共享可变状态 |
| Retry / idempotency | covered: B-004（重复记录不虚增 lane 数；校验可重复执行） |
| Illegal state transitions | covered: B-007（断言与 item 状态的绑定关系） |
| Compatibility / migration | covered: B-001（存量 checkpoint 与 fixture 零影响） |
| Degradation / fallback | N/A: gate 只有 blocked/allowed，无降级路径 |
| Evidence / audit integrity | covered: B-002 B-005（失败 lane 证据的完整性判定） |
| Cancellation / interruption | N/A: 短生命周期校验函数，无长事务 |

## Rollout Notes

对存量 checkpoint 无影响（`auth_mode: auto` 是 #107 之后才出现的新字段）。auto 模式运行方如遇阻断，修复路径是补第二条独立 lane 的失败记录或改走重试 lane，与 `skills/specrail-implement-queue/SKILL.md` 契约一致。
