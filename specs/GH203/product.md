# Product Spec

## Linked Issue

GH-203

## 用户问题

implx 在用户明确只要求处理一个、规格完备的 issue 时，仍可能先执行全队列覆盖分类、
queue-planning YAML 与 tranche 预算，固定成本与目标规模不成比例。现有
single-issue shortcut 虽然尝试跳过这些 queue-only 产物，却把
`exception_allowed` 也当作“规格完备”，并只笼统路由到 implement + PR gate，没有
明确要求 exact-head 本地 review artifact/manifest，容易把性能短路误解为审查短路。

## 目标

- 对恰好一个规格完整、done-when 可判定且非 heavy 的 scoped issue，跳过只服务于
  多项 queue 的全量分类、规划 YAML 和 tranche budget。
- 保留 implement route、duplicate-work、spec 对照、测试、exact-head review、
  current PR evidence、PR gate 与 merge authorization。
- 让 `bounded_tranche` 只分类目标 issue/PR，让 `full_queue_drain` 才承担全仓分类。
- 对规格缺失、`exception_allowed`、heavy 或多 issue 耦合 fail closed 到完整 queue
  路径或人工决策。

## 非目标

- 不让无 `product.md`/`tech.md`/`tasks.md` 的工作借 shortcut 实现。
- 不为单 issue 放宽 CI、review threads、merge state、human gate 或 security gate。
- 不改变 plain `implx` 默认的 `full_queue_drain` 语义。
- 不把“跳过 native implementation lane”解释为允许跳过本地 reviewer evidence。

## Behavior Invariants

1. B-001 当用户明确把范围限制为恰好一个 issue，且该 issue 的 product/tech/tasks
   packet 完整、非 legacy、done-when 可判定并初步分类为 fastlane/standard 时，
   implx 必须走 single-issue shortcut。
2. B-002 当 B-001 成立时，系统不得构建全仓 spec coverage map、queue-planning
   YAML 或 tranche budget；只读取目标 issue、其 packet、既有 PR/branch 与必要
   remote truth。
3. B-003 当使用 `bounded_tranche` 而非 single-issue shortcut 时，Spec Coverage
   Gate 只分类命名目标及其 linked PR；只有 `full_queue_drain` 分类全部 open
   issue/PR。
4. B-004 `exception_allowed`、`needs_spec`、`needs_tasks`、legacy packet 或缺失可判定
   done-when 的 issue 不得进入 single-issue shortcut；不得用 issue body 或聊天上下文
   冒充完整 spec packet。
5. B-005 当 shortcut 发现 multi-issue coupling、combined acceptance surface、
   heavy/security/schema/migration/cross-module 风险或重复工作归属冲突时，必须停止
   shortcut 并回退 queue/人工路由，不能继续按“小改动”处理。
6. B-006 shortcut 必须在实施前运行 duplicate-work evidence 与 `implement` route
   gate，并只执行目标 tasks/acceptance criteria；任何 gate 非 `allowed` 都必须停止。
7. B-007 当 shortcut 产出 GitHub PR 或修改既有 PR head 时，merge-readiness evidence
   必须包含通过 schema/语义校验的 exact-head 本地 review artifact 与 manifest；
   仅传 `review_source`、hosted review 或协调者文字结论均不满足。
8. B-008 shortcut 的 PR 必须继续满足 current-head CI、resolved threads、clean
   merge state、linked-work、spec-vs-implementation 对照和 fresh `pr_gate=allowed`；
   shortcut 只能省略 queue-only 规划成本。
9. B-009 review 模式仍需适用的人工或 tier-scoped merge authorization；auto 模式
   只有显式 `implx auto` 才提供 standing authorization，shortcut 自身不授权 merge。
10. B-010 当执行中断、PR head 漂移或 shortcut 资格在实现中失效时，恢复流程必须
    重新核对目标 packet、风险与 current remote truth；无法继续证明单 issue 边界时
    回退 queue，不得复用旧分类。

## 验收标准

- [ ] shortcut 只接受完整、非 legacy 的三件套 packet，不再接受
  `exception_allowed`。
- [ ] shortcut 明确列出 duplicate/route/spec-check/exact-head local
  review/manifest/PR gate 证据链。
- [ ] `bounded_tranche` 只分类目标；plain `implx` 继续全队列分类。
- [ ] heavy、多 issue、风险或资格漂移明确回退 queue。
- [ ] 单 issue 性能优化不改变任何 merge-readiness 或授权门禁。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001 B-004 B-006 B-007 |
| 错误与失败路径 | covered: B-004 B-005 B-006 B-010 |
| 授权/权限 | covered: B-006 B-009 |
| 并发/竞态 | covered: B-005 B-010 |
| 重试/幂等 | covered: B-010 |
| 非法状态转换 | covered: B-004 B-006 B-009 |
| 兼容/迁移 | covered: B-003；plain implx 和 bounded queue 语义保持 |
| 降级/回退 | covered: B-005 B-010 |
| 证据与审计完整性 | covered: B-006 B-007 B-008 B-009 |
| 取消/中断 | covered: B-010 |

## 发布说明

single-issue shortcut 只减少 queue-only 编排产物，不减少规格或审查证据。此前依赖
`exception_allowed` 的调用将回退正常 queue/人工路由；已完整规格的小 issue 获得
更低启动成本。
