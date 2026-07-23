# Product Spec

## Linked Issue

GH-189

## 用户问题

同一仓库的多个 Codex 会话可以同时运行 `implx`。现有 GitHub duplicate-work gate
只能发现 PR/branch 重复，`.specrail/runtime/current.json` 也没有 owner、lease 或
fencing token。两个会话因此可能重复开 lane、覆盖 checkpoint、串用 Goal，并把大量
token 消耗在同一队列上。

## 目标

- 为同一 Git common dir 下的所有 worktree 提供唯一 active-run lease。
- 在 lane、checkpoint 与远端写入前用 fencing token 阻止旧/并发 owner。
- 支持同一 run 跨 compaction/session 的显式 resume，以及可审计 stale takeover。
- 保持检查有界、无 polling、无进程终止和无隐式远端动作。

## 非目标

- 不实现跨机器/网络文件系统的强一致分布式锁。
- 不 kill、暂停或关闭其他 Codex 进程，不用 GitHub label 充当 mutex。
- 不替代 GitHub truth、runtime checkpoint、Goal 或 SpecRail gate。
- 不处理 GH-160。

## Behavior Invariants

1. B-001 当两个 worktree 共享同一 Git common dir 时，它们必须解析到同一 lease
   位置和 repo identity。
2. B-002 当不存在 lease 时，多个并发 acquire 中最多一个 run 可以原子获得有效
   `run_id` 与单调递增 `fencing_token`。
3. B-003 当有效 lease 已由另一个 run 持有时，新 run 必须在创建 lane、写 checkpoint
   或执行 GitHub write 前阻断，并报告非敏感 owner/expiry 证据。
4. B-004 当持有者在关键边界续租时，必须提交匹配的 run ID、fencing token 和当前
   lease digest；任一不匹配均不得更新。
5. B-005 当 lease 到期时，它必须进入 `stale` 而不是自动变成 `free`；不同 run
   takeover 需要本轮显式人工授权与原因。
6. B-006 当授权 takeover 成功时，新 fencing token 必须大于旧 token，并保留旧/new
   run ID、旧 digest、actor marker 与原因的审计记录。
7. B-007 当同一 run 跨 compaction 或新 session resume 时，只有 checkpoint/Goal
   的 repo、run ID 和 fencing token 全部匹配才可续租。
8. B-008 当 lease JSON 缺失字段、损坏、部分写入、符号链接、权限错误或路径逃逸时，
   inspect 必须返回 `corrupt/unsafe` 并 fail closed。
9. B-009 当系统时钟回拨、PID 被复用或进程不存在时，不得单独据此释放或接管 lease。
10. B-010 当 owner 正常完成或收到用户中断时，只能释放与自己 run ID/token/digest
    匹配的 lease；不得删除其他 owner 或更新后的 lease。
11. B-011 当 lease 操作被取消或写入失败时，不得产生已获取/已续租/已释放结论；
    下一次操作必须从磁盘重新读取。
12. B-012 当普通 pack check 运行时，它只校验 schema/tool 资产，不 acquire、renew、
    release 或读取活动 repo 的 lease。
13. B-013 当 lease 状态静态不变时，重复 inspect 的状态、摘要与退出码必须一致，且
    输出不得包含 session 正文、secret、绝对 home 路径或 PID 细节。
14. B-014 当文件系统不支持所需原子语义或 repo identity 无法稳定解析时，系统必须
    报告 unsupported 并阻断并发 auto-run，不得降级成无锁继续。

## 验收标准

- [ ] 跨两个 worktree 的并发测试证明最多一个 owner 获得 lease。
- [ ] acquire/renew/release/resume/stale/takeover/损坏路径均有确定性测试。
- [ ] 所有 lane、checkpoint 和 remote-write 边界都验证当前 fencing token。
- [ ] 无自动 takeover、无 kill、无 polling、无 GitHub mutex。
- [ ] full tests 与跨 worktree forward test 全绿，diff 不含 GH-160。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002 B-008 |
| 错误与失败路径 | covered: B-003 B-004 B-008 B-011 B-014 |
| 授权/权限 | covered: B-005 B-006 B-010 |
| 并发/竞态 | covered: B-001 B-002 B-004 B-010 B-011 |
| 重试/幂等 | covered: B-004 B-007 B-010 B-013 |
| 非法状态转换 | covered: B-003 B-005 B-006 B-007 B-010 |
| 兼容/迁移 | covered: B-001 B-012 B-014 |
| 降级/回退 | covered: B-008 B-009 B-014 |
| 证据与审计完整性 | covered: B-006 B-007 B-013 |
| 取消/中断 | covered: B-010 B-011 |

## 发布说明

启用后，同一 Git 仓库默认只允许一个 active implx run。发现 stale lease 时只报告
takeover 所需证据，必须由用户明确授权；现有单会话流程不改变。
