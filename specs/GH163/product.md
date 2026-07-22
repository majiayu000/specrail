# Product Spec

## Linked Issue

GH-163

## 用户问题

`specrail-review-pr` 在未接入 SpecRail gate 的仓库中会继续执行并产出看似已
通过门禁的 review。调用方无法区分“门禁真实通过”和“门禁缺失或执行失败”，
从而形成静默降级。

## 目标

- gate 存在时强制执行，并按真实 decision 处理。
- gate 缺失或执行错误时 fail closed，不把降级路径伪装成成功。
- 人工明确授权的降级 review 必须留下机器可校验的授权与披露证据。

## 非目标

- 不为未接入 SpecRail 的仓库自动安装 gate。
- 不把 advisory review 提升为 final approval 或 merge authority。
- 不改变未声明 degraded 字段的既有 review artifact 行为。

## Behavior Invariants

1. B-001 当 `checks/route_gate.py` 存在时，`review_pr` 必须执行该 gate；
   非 `allowed` decision 不得被当作成功。
2. B-002 当 `checks/route_gate.py` 不存在时，SpecRail `review_pr` 路由必须停止，
   且不得投机执行一个已知不存在的命令。
3. B-003 当 gate 命令因文件、解释器或运行错误而未产生有效 decision 时，结果必须
   等价于 gate unavailable，而不是 `allowed`。
4. B-004 只有当前人工明确授权时才允许继续 degraded review；artifact 必须记录
   `gate_status: unavailable` 与非空 `gate_authorization`。
5. B-005 degraded review 的 `## Summary` 必须包含稳定标记
   `SpecRail gate status: unavailable`（大小写精确匹配）；完整 review body 与 published
   comment text 均不得声称 SpecRail-gated、verified 或 merge-ready。
6. B-006 `gate_status`、`gate_authorization` 与 unavailable marker 必须双向一致：
   状态越界、缺少或空白授权、marker 不在 `## Summary`、marker 未配套
   `gate_status: unavailable`，或授权字段脱离 unavailable 状态单独出现时，JSON
   gate 与 schema-backed manifest 都必须 fail closed。
7. B-007 schema-backed review manifest 必须接受满足 B-004/B-005 的 artifact 供审计与
   发布，但 `gate_status: unavailable` 必须产生 merge-readiness blocker，不能作为 PR
   gate 的 terminal clean evidence；未声明的新字段仍由 `additionalProperties: false`
   拒绝。
8. B-008 未声明 `gate_status` 与 `gate_authorization` 的既有 artifact 保持原行为，
   不因本变更被强制迁移为 degraded review。
9. B-009 gate 拒绝时必须保留 rejection evidence，后续修复不得通过忽略门禁推进。

## 验收标准

- [ ] gate 存在、缺失、执行错误三条路径均有明确且互斥的行为。
- [ ] 合规 degraded artifact 同时通过 JSON gate 与 schema-backed manifest loader。
- [ ] 缺授权、缺披露、非法状态和孤立授权均被确定性拒绝。
- [ ] focused tests、完整 `pytest` 与 `python3 checks/check_workflow.py --repo .`
      全部通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002, B-004, B-006 |
| 错误与失败路径 | covered: B-001, B-003, B-009 |
| 授权/权限 | covered: B-004, B-006 |
| 并发/竞态 | N/A：离线 artifact gate，无共享并发状态 |
| 重试/幂等 | covered: B-009 |
| 非法状态转换 | covered: B-006 |
| 兼容/迁移 | covered: B-007, B-008 |
| 降级/回退 | covered: B-002, B-003, B-004, B-005 |
| 证据与审计完整性 | covered: B-004, B-005, B-006, B-009 |
| 取消/中断 | N/A：命令可安全重跑，无部分持久化状态 |

## 发布说明

这是 fail-closed contract 修复。未接入 SpecRail 的仓库应改用普通 code review；
只有人工明确授权的 degraded review 可继续，并必须携带机器可读披露。
