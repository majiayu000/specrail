# Product Spec

## Linked Issue

GH-141

## 用户问题

07-16 会话记录中出现 reviewer 反复驳回同一 preflight 缺失、agent 多轮试错的 W-02 循环。根因推断：preflight/review 类 gate 驳回时只返回"不通过"结论与零散字符串原因，未一次性枚举全部缺失项，也没有稳定的条目标识，agent 只能逐轮猜、逐轮补。现状中 `checks/route_gate.py` 与 `checks/review_json_gate.py` 虽然内部收集了 `missing` / `reasons` 列表，但条目是自由文本、无类别、无 expected/found 对照，且无法跨轮比对"这一项是不是上一轮已经驳回过的同一项"。

## 目标

- 驳回类 gate（route_gate、review_json_gate、pr gate 的 review contract 汇总）驳回时一次性输出机器可读的结构化缺失清单：稳定 item id、类别、expected 与 found 对照。
- agent 单轮补齐后复检；对"同一项被逐字重复驳回"给出可检测的契约违规信号，暴露并终止 W-02 重试循环。

## 非目标

- 不改变任何 gate 的放行/阻断判定逻辑与退出码语义；结构化清单是纯新增输出。
- 不删除或改写既有 `reasons` / `missing` / `satisfied` 字符串列表（下游消费方兼容）。
- 不接管 reviewer 人类判断；repeat_rejection 是信号输出，不自动改判 decision。
- 不覆盖 GitHub 远端 evidence 采集脚本（`checks/github_*.py`）；本期只做本地 gate 输出面。

## Behavior Invariants

1. B-001 当驳回类 gate 的 decision 非 `allowed` 时，输出 JSON 应包含 `rejection_items` 数组，一次性枚举全部可独立判定的缺失/失败项；gate 应不因发现第一项失败而停止收集其余项。
2. B-002 `rejection_items` 每项应包含非空的 `item_id`、`category`、`expected`、`found` 四个字段；`category` 取值为闭集 {missing_artifact, invalid_state, missing_evidence_field, invalid_evidence_value, contract_violation, config_error}，越界取值或字段缺失视为 gate 自身缺陷，gate 应非零退出并说明。
3. B-003 当以相同仓库状态与相同输入重复运行 gate 时，`rejection_items` 的条目集合、`item_id` 取值与排序应逐字节一致（确定性排序 + 去重）。
4. B-004 如果同一缺陷被多个 checker 重复发现，`rejection_items` 应按 `item_id` 去重后只保留一项，不得出现同 id 多条。
5. B-005 当调用方通过 `--prior-rejection` 提供上一轮驳回 payload、且本轮存在与上一轮 `item_id` + `expected` + `found` 完全一致的条目时，gate 应输出 `repeat_rejection` 段并列出全部重复的 `item_id`——重复驳回同一项即契约违规信号。
6. B-006 若 `--prior-rejection` 指向的文件缺失、JSON 非法或缺少 `rejection_items` 字段，gate 应将该错误作为一条 `config_error` 类别的 rejection item 列入本轮清单并阻断，不得静默忽略或降级为仅告警。
7. B-007 当未传 `--prior-rejection` 且不消费新字段时，既有 `reasons` / `missing` / `satisfied` 的内容与排序应保持与现状一致，退出码语义不变；`rejection_items` 为纯新增字段。
8. B-008 当 decision 为 `allowed` 时，`rejection_items` 应为空数组（字段存在但为空），且不输出 `repeat_rejection` 段。
9. B-009 每个 rejection item 的 `expected` 与 `found` 应为具体值描述（如 expected 为配置路径存在、found 为 absent），空串、"N/A"、"unknown" 占位均视为违规，gate 自检应拒绝生成此类条目。
10. B-010 当 route_gate 走早退路径（配置校验失败、GitHub state 非 OPEN、terminal state）时，输出同样应包含 `rejection_items`；环境级单项错误允许清单只有一项，但字段完整性要求（B-002/B-009）不变。
11. B-011 gate 输出结构化清单期间应保持只读，不写入或修改任何仓库文件；`--prior-rejection` 仅读取。
12. B-012 若 gate 进程被中断后重跑，输出应与一次完整运行一致；结构化清单不依赖任何跨进程状态，天然幂等。

## Acceptance Criteria

- [ ] 三个驳回面（route_gate、review_json_gate、pr_review_contract 经 pr_gate）驳回时均输出全量 `rejection_items`，条目含 item_id/category/expected/found。
- [ ] 构造一个多缺失项 spec/evidence fixture：一轮拿到全量清单、单轮补齐、二轮通过，全程无重复驳回同一项。
- [ ] 构造重复驳回 fixture：二轮传 `--prior-rejection` 后 gate 输出 `repeat_rejection` 段并列出重复 item_id。
- [ ] 未传 `--prior-rejection` 时既有输出与退出码回归全绿。

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-006 B-008（prior 文件缺失 fail-closed；allowed 时空数组而非缺字段） |
| Error / failure paths | covered: B-001 B-002 B-010（全量枚举失败项；gate 自身缺陷显式非零退出） |
| Authorization / permission | N/A: 本地只读 gate，无权限面；授权类判定仍由既有 checker 产出条目，本期不新增权限逻辑 |
| Concurrency / race | N/A: 单进程只读评估，无共享可变状态 |
| Retry / idempotency | covered: B-003 B-012（确定性输出；重跑幂等） |
| Illegal state transitions | covered: B-010（terminal/非法 state 早退路径同样输出结构化清单） |
| Compatibility / migration | covered: B-007（既有字段与退出码不变，新字段纯增量） |
| Degradation / fallback | covered: B-006 B-009（先验文件损坏不静默降级；占位值条目被 gate 自检拒绝） |
| Evidence / audit integrity | covered: B-005 B-009（重复驳回可检测；expected/found 必须可对照审计） |
| Cancellation / interruption | covered: B-012（中断后重跑与完整运行一致） |

## Rollout Notes

纯新增输出字段与可选 CLI 参数，默认不改变任何调用方行为。消费方（implement/review lane）按需读取 `rejection_items` 做单轮补齐；`--prior-rejection` 由编排方在第二轮起传入上一轮 payload。
