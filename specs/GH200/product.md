# Product Spec

## Linked Issue

GH-200

## 用户问题

implx 对普通 PR 经常同时启动 mechanical、cross、adversarial 与 final reviewer，
造成多份重复上下文和串行等待。另一个放大器是：review artifact 仅因 JSON
格式、必填元数据或 manifest 结构错误被 gate 拒绝时，执行者会误开新 review
round，并重复测试和 GitHub evidence 采集，尽管代码 head 和审查结论均未改变。

## 目标

- 将 fastlane/standard PR 的默认独立审查收敛为一个 reviewer lane。
- 区分“审查结论变化”与“artifact 表示缺陷”，对后者只修复 artifact。
- 保留 heavy tier、lane failure、bounded review 与人类升级路径。

## 非目标

- 不限制维护者明确要求的额外审查。
- 不把代码/规格 finding 误分类成 artifact 格式问题。
- 不放宽 `review_json_gate`、manifest 语义、review threads 或 final review gate。

## Behavior Invariants

1. B-001 当 PR 为 fastlane 或 standard tier 且无已记录 lane failure 时，系统默认只
   启动一个独立只读 reviewer/merge-reviewer lane。
2. B-002 只有当 PR 为 heavy tier、维护者明确要求额外审查，或既有 reviewer lane
   失败需要独立重试时，系统才可启动第二个或更多 reviewer lane，并记录触发依据。
3. B-003 当 artifact 因 JSON shape、必填元数据、manifest 路径或同类表示缺陷失败，
   且原始 reviewer 输出与 PR head 均未变化时，系统必须从既有输出重新生成 artifact，
   不得把该操作记为新的 review round。
4. B-004 B-003 的修复路径只重新运行 `review_json_gate` 和 manifest 语义校验；不得
   重跑测试、重采未变化 head 的 GitHub evidence，或再次派发 reviewer。
5. B-005 如果失败涉及真实 finding、审查范围缺失、reviewer 输出缺失/不可恢复或 PR
   head 已变化，则 artifact-only 路径不适用；系统必须进入正常修复与 bounded
   re-review 流程。
6. B-006 当 reviewer lane 失败时，失败记录必须保留 lane id、failure kind 与可审计
   marker；重试必须使用不同 lane，不能把失败 lane 改写成通过。
7. B-007 当进入第二轮及后续审查时，系统必须遵守 `bounded_diff_v1`：使用
   `resumed|diff_only`、携带紧凑 prior findings，并保持 round cap 与升级授权。
8. B-008 当 artifact 修复、lane 重试或证据采集被中断时，恢复流程必须先核对 current
   head 和既有输出身份；无法证明不变时按 B-005 处理，不得静默复用。

## 验收标准

- [ ] fastlane/standard 默认单 reviewer lane。
- [ ] heavy、人工要求和 lane failure retry 是额外 lane 的封闭例外。
- [ ] artifact 格式缺陷只重生成 artifact 并重跑 artifact gate。
- [ ] head 变化或真实 finding 不得进入 artifact-only 路径。
- [ ] bounded review、lane failure 与人工 final review 规则保持不变。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-005 |
| 错误与失败路径 | covered: B-003 B-005 B-006 |
| 授权/权限 | covered: B-002 B-007；维护者升级权限不变 |
| 并发/竞态 | covered: B-008 |
| 重试/幂等 | covered: B-003 B-004 B-006 B-007 |
| 非法状态转换 | covered: B-003 B-005 B-006 |
| 兼容/迁移 | covered: B-007；既有 bounded manifest 保持兼容 |
| 降级/回退 | covered: B-005 B-006 |
| 证据与审计完整性 | covered: B-002 B-003 B-004 B-006 B-008 |
| 取消/中断 | covered: B-008 |

## 发布说明

这是 reviewer orchestration 的成本收敛。不会减少真实审查覆盖，也不会把 hosted
review、artifact 修复或协调者自评冒充独立审查。
