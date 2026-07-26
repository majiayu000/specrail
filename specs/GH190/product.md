# Product Spec

## Linked Issue

GH-190

## 用户问题

queue 要求 auto full-drain 创建包含完整目标、四类终止条件、每 turn 重锚和 token
budget 的 Codex Goal；但 checkpoint 的 active `goal` 字段几乎都可缺失，runtime gate
只校验 `goal_candidate`。因此缺预算、缺终止条件或 objective 漂移的 Goal 仍可通过
checkpoint，并在 compaction 后继续低产出长跑。

## 目标

- 用纯函数 builder 生成唯一、稳定的 Goal payload。
- 用 closed schema 和 runtime gate 绑定 Goal、checkpoint、queue 与 run lease。
- 强制预算来源、终止条件、re-anchor 和状态转换，拒绝部分/漂移证据。
- 不让 Goal 替代 GitHub truth、SpecRail gate 或 checkpoint。

## 非目标

- 不选择默认 token budget 数值，也不设计父/子 aggregate budget。
- 不修改 GH-160 的 context 水位、soft stop 或 handoff。
- 不在测试中真实创建/完成 Goal，不自动合并或写 GitHub。

## Behavior Invariants

1. B-001 当 auto + full_queue_drain + Goal capability 全部成立时，系统必须先构建并验证
   Goal contract，再调用 `create_goal`；不得手写自由文本绕过 builder。
2. B-002 当 builder 输入相同且 queue snapshot 顺序等价时，objective、constraints、
   termination conditions 与 `contract_digest` 必须字节稳定；该摘要必须覆盖全部不可变
   Goal contract 字段，不能只覆盖 objective。
3. B-003 当 active Goal 被创建时，必须具有正整数 `token_budget` 和明确
   `budget_source`；用户未提供且没有维护者批准的 pack default 时必须 fail closed，
   不得静默猜值或创建无预算 Goal。
4. B-004 当 objective 构建时，必须包含 queue empty/fully blocked、budget exhausted、
   user interrupt、only human_decisions remain 四类终止条件，缺失/重复均失败。
5. B-005 当 Goal 活跃时，objective 必须要求每 turn 从当前 runtime checkpoint 加
   fresh remote truth 重锚；仅依赖对话记忆或 Goal status 不合法。
6. B-006 当 `create_goal` 返回后，checkpoint-facing active contract 必须要求并绑定
   goal ID、objective/contract digest、token budget/source、status、repo、run ID 与
   fencing token；创建前 draft 不得被 checkpoint 当作 active Goal 接受。
7. B-007 当 runtime 不支持 Goal、auth_mode 为 review 或 queue_mode 为 bounded 时，
   不得创建 active Goal；必须记录通过现有 gate 的 `goal_candidate`/disabled reason。
8. B-008 当 queue 仍含 actionable item 时，Goal 不得进入 complete；只剩
   `human_decisions` 或 queue empty/fully blocked 才允许完成。
9. B-009 当预算耗尽时，状态必须通过不可变 transition evidence 转为 exhausted，先写
   有效 checkpoint/handoff，再停止；不得把 exhausted 标为 complete、改回 active 或
   自动创建新 Goal 绕过预算。
10. B-010 当用户中断时，状态只能转为 interrupted，并保留最新 checkpoint；不得吞掉
    中断后继续运行。
11. B-011 当 Goal 跨 tranche/session resume 时，repo、goal ID、contract digest、
    run ID/fencing token、budget、创建时 queue baseline 与其后合法 rebind 链必须全部
    匹配；否则需要新 Goal/人工决策。
12. B-012 当 goal payload 缺字段、未知字段、非法状态、partial update、旧 digest 或
    tokens_used 超预算时，schema/gate 必须一次报告全部错误并 fail closed。
13. B-013 当相同有效 checkpoint 重复验证时，结果和错误顺序必须稳定；验证不得调用
    Goal API、写 checkpoint、读取 session 正文或访问网络。
14. B-014 当 Goal API 调用失败/取消或返回缺失 ID 时，不得写 active/success
    checkpoint；恢复必须从 fresh Goal state 与 remote truth 重新决策。
15. B-015 当系统选择预算或判断预算缺失/非法时，必须持久化 user budget 与
    pack-default 两个已评估输入及其可信来源/批准证据，disabled reason 必须由 builder/gate
    重新计算；不得由调用方自报 `missing_budget`/`invalid_budget` 绕过可用预算。
16. B-016 当 Goal 状态变化时，checkpoint 必须追加带顺序号、前序摘要和证据摘要的
    immutable transition event；任一 terminal 状态之后出现 active、事件改写/缺口或当前
    status 与链尾不一致时，resume 必须 fail closed。
17. B-017 当 fresh remote truth 改变 queue 时，创建时 baseline 必须保持不可变，当前
    snapshot 只能通过连续、可验证的 rebind event 更新；正常队列进展不得改写 contract
    digest，断链、跨 repo/run/scope rebind 或当前摘要不匹配必须阻断。
18. B-018 当读取 checkpoint v1–v3 时，不得把旧宽松 `goal` 直接作为 active 证据；
    必须通过确定性、版本条件化迁移生成 v4，保留 legacy provenance，并要求 fresh
    remote/budget evidence 后创建新 Goal 或进入合法 disabled 分支。
19. B-019 当 queue/implx agent 需要创建或绑定 Goal 时，必须调用具名 builder CLI，
    使用 closed JSON input/output 与稳定 decision/reason/exit code；不得要求 Markdown
    skill 进程内调用 Python 或自行拼接 tool payload。

## 验收标准

- [ ] builder 输出稳定，四终止条件、re-anchor、预算与约束不可省略。
- [ ] active Goal schema closed，draft/active 类型分离，runtime gate 验证
      contract/queue/run/checkpoint binding。
- [ ] 预算缺失、terminal transition、queue rebind 与 v1–v3 migration 都有确定性正反
      例，不能靠调用方自报或改写旧状态。
- [ ] queue/implx 通过 agent-facing CLI 取得 tool payload 与 bound active contract。
- [ ] auto/review/bounded/unavailable 与 complete/exhausted/interrupted 路径全覆盖。
- [ ] 测试无 Goal API 副作用，full suite 与 forward dry-run 全绿。
- [ ] 不选择 GH-160 的预算值，不含 GH-160 diff。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-004 B-012 B-014 B-015 |
| 错误与失败路径 | covered: B-003 B-006 B-012 B-014 B-019 |
| 授权/权限 | covered: B-003 B-007 B-011 B-015 |
| 并发/竞态 | covered: B-006 B-011 B-016 B-017 |
| 重试/幂等 | covered: B-002 B-011 B-013 B-014 B-016 B-017 B-019 |
| 非法状态转换 | covered: B-007 B-008 B-009 B-010 B-016 |
| 兼容/迁移 | covered: B-007 B-011 B-018 |
| 降级/回退 | covered: B-003 B-007 B-014 B-018 |
| 证据与审计完整性 | covered: B-005 B-006 B-012 B-013 B-015 B-016 B-017 |
| 取消/中断 | covered: B-010 B-014 |

## 发布说明

active Goal 从松散备注升级为强类型执行合同。没有已批准 token budget 时不再创建
无界 Goal；这不决定预算值，预算策略仍由 GH-160/维护者单独处理。
