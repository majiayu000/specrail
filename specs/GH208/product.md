# Product Spec

## Linked Issue

GH-208

complexity: large

## 用户问题

SpecRail 的治理合同已经从辅助代理交付的最小约束，膨胀为一套与 GitHub
并行的运行时状态机。普通修复也会加载队列预算、Goal、checkpoint、review
轮次、tier 授权和 closure 等多套证据，导致 PR 数量、等待 turn、重复审查和
上下文成本持续上升。维护者需要一个默认轻量、只在高风险变更中启用严格
证据的工作流，而不是继续压缩文字但保留全部机制。

## 目标

- 将默认流程收敛为 `fastlane`、`standard`、`heavy` 三个验证 profile。
- 让 GitHub Issue、PR、CI 与 review 成为唯一 durable truth；本地 checkpoint
  只允许作为可选恢复游标。
- 删除 Goal/checkpoint 绑定、active-run lease、attempt ledger、runtime
  telemetry gate 和逐轮授权等未证明收益的治理状态机。
- 将核心 checker、schema 和技能阅读集缩减到可审计规模。
- 保留安全敏感路径的 fail-closed 行为和人类最终审批边界。
- 让 review 在一次 full review 和一次 diff-only review内收敛。

## 非目标

- 不自动 merge、final approval、公开安全信息或修改仓库权限。
- 不实现跨机器分布式队列锁。
- 不承诺兼容旧 runtime checkpoint、tier authorization 或 Goal ledger。
- 不为删除的治理功能再建立迁移状态机；旧 artifact 只返回明确的 unsupported
  诊断。
- 不在本变更中自动关闭消费仓库的 Issue/PR。

## Behavior Invariants

1. B-001 当任务被分类为 `fastlane` 时，工作流必须只要求 linked Issue、当前
   diff、项目测试、一次 review 和人工 merge 边界；不得要求 spec packet、
   runtime checkpoint、hosted review、GraphQL thread、Goal 或 tier
   authorization。
2. B-002 当任务被分类为 `standard` 时，工作流必须要求 linked Issue、可测试
   计划、项目测试和一次 full review；只有修复 full-review finding 后才允许一次
   diff-only review。
3. B-003 当任务涉及 auth、payments、secrets、数据迁移、权限或仓库声明的
   sensitive path 时，必须分类为 `heavy`，要求 durable spec、独立 review 和
   明确的人类 merge authorization；缺失证据必须 fail closed。
4. B-004 缺少 SpecRail pack 的未采用仓库不得因为 SpecRail checker 不存在而
   被阻断；已经显式采用且声明 mandatory asset 的仓库若资产缺失，必须返回明确
   error，不得静默放行。
5. B-005 Issue 生命周期只能使用 `new_issue`、`needs_info`、
   `ready_to_spec`、`ready_to_implement`、`in_progress`、`review`、`done`
   和 `parked` 八个状态；同一 Issue 不得同时具有 readiness 与 `parked`。
6. B-006 `duplicate`、`abandoned` 和 `security_private` 必须作为 outcome
   而不是主状态机节点；CI、review 和 merge readiness 必须作为 PR 证据而不是
   Issue 状态。
7. B-007 默认一个真实用户目标对应一个主 Issue 和一个 implementation PR；
   只有 `heavy` profile 或维护者明确要求时才创建独立 spec PR。
8. B-008 review 必须最多包含一次 full review 和一次 diff-only review；
   第二轮只允许阻断修复 diff 新引入或未修复的 P0/P1。
9. B-009 P2/P3 finding 默认记录在当前 Issue/PR 的 follow-up section，不得由
   agent 自动创建新 Issue；只有维护者明确提升优先级后才能成为独立工单。
10. B-010 已过时 commit 上的 hosted/cloud review thread 不得单独阻断 merge；
    当前 head 上未解决的 P0/P1 仍必须阻断。
11. B-011 duplicate-work 与 closure 检查默认输出 advisory warning；只有安全
    属性、当前 head CI、当前 P0/P1 review 或明确人工 gate 可以返回 blocking。
12. B-012 GitHub Issue、labels、PR、reviews、branches 和 CI 是 durable truth；
    本地 checkpoint 只能保存 `completed`、`pending`、`blocked`、
    `artifact_refs` 和 `resume_action`，不得复制 CI、review、merge、授权、
    budget、Goal、branch 或 worktree 状态。
13. B-013 `implx` 不得创建或验证 Goal contract、active-run lease、attempt
    ledger、progress fingerprint、decision receipt、reservation 或 runtime
    telemetry；并发运行由操作者避免，或由宿主提供单个非持久 OS lock。
14. B-014 核心 `checks/*.py` 模块总数不得超过 18，pack-owned JSON schema
    不得超过 8；删除能力时必须同时删除其 schema、fixture、测试和文档入口。
15. B-015 `skills/specrail-implement-queue/SKILL.md` 不得超过 200 行，
    `skills/implx/SKILL.md` 不得超过 60 行；fastlane 启动阅读集不得超过
    3 个文件和 12 KiB。
16. B-016 新增 blocking gate 必须引用真实事故和预期拦截场景，并在同一变更中
    删除或降级至少一个同类非安全 gate；30 天无真实拦截且无安全属性的 gate
    必须降级为 warning 或删除。
17. B-017 旧 runtime checkpoint、tier authorization 或 review-round artifact
    被输入时，系统必须返回单一、明确、可行动的 unsupported 诊断，不得把旧字段
    解释成当前授权或静默成功。
18. B-018 任一 profile 的 checker 遇到缺失、无效或互相矛盾的当前必需证据时，
    必须一次返回全部问题；不得逐项失败导致多轮重试。
19. B-019 所有 GitHub 写动作、push、PR 创建、标签变更、关闭和 merge 继续要求
    当前用户授权；`implx auto` 只能授权本次明确 invocation 的正常交付动作，
    不能授权 force-push、权限变更或安全披露。
20. B-020 缩减完成必须通过全量 pack 检查与测试，并至少完成一次本地
    fastlane、standard、heavy fixture E2E；不得只用行数下降宣称完成。

## 验收标准

- [x] `checks/*.py` 文件数不超过 18，schema 文件数不超过 8。
- [x] queue skill 不超过 200 行，implx 不超过 60 行。
- [x] fastlane 强制阅读集不超过 3 个文件、12 KiB。
- [x] 八状态 workflow、mutually exclusive readiness/parked 校验通过。
- [x] runtime/Goal/lease/attempt-ledger 模块及其 schema、fixture、测试入口删除。
- [x] review contract 对 P0/P1、P2/P3、outdated hosted thread 和两轮上限有正反测试。
- [x] `python3 checks/check_workflow.py --repo . --all-specs` 通过。
- [x] `python3 -m pytest -q` 通过。
- [x] fastlane、standard、heavy 三条 E2E fixture 通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-004, B-018 |
| 错误与失败路径 | covered: B-003, B-017, B-018 |
| 授权/权限 | covered: B-003, B-019 |
| 并发/竞态 | covered: B-013 |
| 重试/幂等 | covered: B-008, B-018 |
| 非法状态转换 | covered: B-005, B-006 |
| 兼容/迁移 | covered: B-017 |
| 降级/回退 | covered: B-004, B-011 |
| 证据与审计完整性 | covered: B-003, B-012, B-016, B-018 |
| 取消/中断 | covered: B-012, B-013 |

## 发布说明

这是 breaking workflow release。旧 runtime checkpoint、tier authorization 和
review-round artifact 不迁移；采用仓库升级后应从 GitHub 当前状态重建可选恢复游标。
发布说明必须列出删除的 checker/schema、profile 选择规则和人类 gate 保留项。
