# Product Spec

## Linked Issue

GH-191

## 用户问题

GH-157 已在 queue Skill 写入 Same-Issue Circuit Breaker，但三个阈值仍靠模型阅读
git/checkpoint 后主观判断，runtime schema 没有逐 issue attempt history，gate 也不计算
熔断。compaction 或新会话因此会忘记已做过的近同工作，继续消耗 token 却不收敛。

## 目标

- 记录 append-only、与 head/run/tranche 绑定的逐 issue attempt evidence。
- 用可机器判定的 durable progress fingerprint 计算 GH-157 三类阈值。
- 在开 lane 和远端动作前由 offline gate 一次报告全部 trip reason。
- 保持 park/draft 等外部动作受当前会话授权控制。

## 非目标

- 不重做 GH-157 的 skip label、Done-When 或阈值产品决策。
- 不按提交数量惩罚真实进展，不读取原始 session transcript。
- 不自动 park/draft/close issue，不处理 GH-160。

## Behavior Invariants

1. B-001 当某 issue 开始一次实现 round 时，必须记录唯一 attempt ID、issue、run、
   tranche、before head、work fingerprint 与目标 acceptance/task IDs。
2. B-002 当 round 结束/中断时，必须追加 after head、verification/review/coverage
   evidence 与 outcome；不得覆盖或删除以前 attempt。
3. B-003 当且仅当新增具名 acceptance/task coverage、修复一个绑定 head 的失败指纹、
   解决 blocking review finding 或产生 terminal GitHub transition 时，才计 durable progress。
4. B-004 当只有新 commit/message、格式改写、重复测试、相同失败或自报“完成”时，
   不得计 durable progress。
5. B-005 当同一 issue 累计五个带 commit 的 attempt 仍无 durable progress 时，breaker
   必须 trip，并列出五项证据。
6. B-006 当连续三个 attempt 的规范化 work fingerprint 相同且无 durable progress 时，
   breaker 必须 trip；改写 commit message 不得改变 fingerprint。
7. B-007 当三个已结束 tranche 都处理该 issue 且没有 durable progress 时，breaker
   必须 trip，并绑定 tranche/run evidence。
8. B-008 当多个阈值同时满足时，gate 必须一次返回全部 trip reasons，稳定排序且不在
   首个原因停止。
9. B-009 当 history 缺失、被覆盖、重复、跨 issue/head/run 串线、未来时间或证据不可读
   时，gate 必须 fail closed，不得按“无历史”继续。
10. B-010 当 breaker trip 时，queue 不得开新 lane或继续该 issue；park/draft/comment
    只有在当前会话明确授权相应远端写时才执行，否则只报告建议。
11. B-011 当人工重新 scope 并解除 parked 时，旧 history 必须保留；新 scope revision
    作为明确 epoch 开始，不能伪造删除旧失败。
12. B-012 当相同 ledger/remote evidence 重复验证时，decision、fingerprint、原因顺序
    与退出码必须相同；collector/gate 只读且输出有界。

## 验收标准

- [ ] 5 attempts、3 same fingerprint、3 tranches 三阈值均有边界正反测试。
- [ ] 多提交真实进展不误触发，改写 message 不能绕过。
- [ ] ledger append-only 且绑定 issue/head/run/tranche。
- [ ] trip 在 lane/remote write 前阻断，外部写仍需授权。
- [ ] compaction/resume forward test 不丢历史，full suite 全绿且无 GH-160 diff。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001 B-002 B-009 |
| 错误与失败路径 | covered: B-008 B-009 B-010 |
| 授权/权限 | covered: B-010 B-011 |
| 并发/竞态 | covered: B-002 B-009 |
| 重试/幂等 | covered: B-002 B-011 B-012 |
| 非法状态转换 | covered: B-009 B-010 B-011 |
| 兼容/迁移 | covered: B-011 |
| 降级/回退 | covered: B-009 B-010 |
| 证据与审计完整性 | covered: B-001 B-002 B-003 B-004 B-008 B-012 |
| 取消/中断 | covered: B-002 B-009 |

## 发布说明

本变更不改变 GH-157 阈值，只把其判断改为 durable evidence。已有历史不足时 fail
closed 并要求一次显式 migration/baseline，不能假装从零开始。
