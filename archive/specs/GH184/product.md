# Product Spec

## Linked Issue

GH-184

## 用户问题

hosted checks 为空有两种成因，但 `checks/pr_gate.py` 只有一种结论。CI 未完成或失败时，重试与新一轮 review 是有效动作；而当仓库的 workflow 根本不会为该 PR 触发时（典型是 stacked PR 的 base 不是 default branch，workflow 只声明 `pull_request.branches: [<default>]`），`checks` 永远为空，任何轮次都不会改变它。

reviewer lane 无法区分二者，于是对第二类反复重开 round。实测：`majiayu000/rnk` PR #75–#79 的 `statusCheckRollup` 长度恒为 0（base 指向另一条 `spec/*` 分支），#69/#73/#74（base=main）各有 16 个 check；PR #74 走到 round 10，每轮都记 `dependency_blocked`。该仓库侧的 workflow 触发修复见 majiayu000/rnk#81。

## 目标

- `pr_gate` 能接受一份显式、封闭、fail-closed 的 `checks_unavailable` 声明，声明 hosted CI 对该 PR 结构性不可用，并以本地验证命令替代 hosted 证据。
- 缺少或不合法的声明时行为逐字不变：空 `checks` 仍然 blocked，`missing_evidence_field:checks` 仍然产出。
- 接受路径不得静默降级：结论中必须出现带 `degraded:` 前缀的 satisfied 条目，指明降级原因与差异化的 base ref。
- review skill 明确：结构性 CI 缺失是一次性结论，不是重开新一轮 review 的理由；首选修复仓库 workflow 触发。

## 非目标

- 不做自动探测：gate 不读取 GitHub、不解析 workflow 文件，只校验采集方提供的声明。
- 不放宽 human merge authorization、review thread、spec、enforcement-sensitive 等任何其它门。
- 不为「CI 未完成 / CI 失败 / CI 尚未为当前 head 触发」提供绕过路径。
- 不引入除 `hosted_ci_not_triggered_for_base` 之外的降级原因。

## Behavior Invariants

1. B-001 `checks` 为非空列表时行为不变；此时若同时出现 `checks_unavailable`，必须以 reason 拒绝，不得二选一地忽略其一。
2. B-002 `checks` 为空列表且无 `checks_unavailable` 时，输出 `missing: checks` 与 `CI/check evidence is missing`，与变更前逐字一致。
3. B-003 `checks` 缺失或非列表（类型错误）时，仍走原始 missing 路径，不进入声明校验。
4. B-004 `checks_unavailable` 必须是对象，字段集合封闭；出现未知字段即拒绝。
5. B-005 `reason` 只接受 `hosted_ci_not_triggered_for_base`。
6. B-006 `base_ref` 与 `default_base_ref` 均为非空字符串；当证据顶层存在同名字段时必须逐字相等；两者相互之间必须不同。
7. B-007 `workflow_trigger_evidence` 为非空字符串，`local_verification` 为非空字符串数组，`verified` 必须严格为 `true`。
8. B-008 任一校验失败时，`checks` 重新计入 missing，且不得产出任何 `degraded:` satisfied 条目。
9. B-009 全部校验通过时，产出且仅产出一条 `degraded:` satisfied 条目，包含 reason、`base_ref`、`default_base_ref` 与本地验证命令条数。
10. B-010 该路径不改变 human authorization 的判定：仍由既有逻辑决定 `needs_human`，接受降级不等于 `allowed`。
11. B-011 schema 与 gate 判定一致：schema 对相同的非法声明同样拒绝，且 `checks` 仍是 required 字段。

## 边界情况清单

| 边界类别 | 判定 |
| --- | --- |
| 空输入 / 缺失输入 | `checks: []` 且无声明 → `missing: checks`；`checks` 键缺失或非列表 → 同样走原路径，不进入声明校验（B-002 B-003） |
| 错误 / 失败输入 | 声明非对象、字段类型错误、未知字段、`reason` 越出枚举 → 全部 blocked 并保留 `missing: checks`（B-004 B-005 B-008） |
| 权限 / 未授权 | 降级不授予任何合并权；`human_authorization` 缺失时结论仍是 `needs_human`（B-010） |
| 并发 / 同时执行 | gate 是离线纯函数，不读写远端或共享状态；同一 PR 的多个 lane 各自评估各自的证据文件，互不影响判定 |
| 重试 / 幂等 | 同一份证据重复评估结论逐字一致；重试本身不放宽任何字段要求，声明也不随重试次数生效 |
| 非法状态 / 状态转换 | `checks` 非空却同时声明 `checks_unavailable` → 以 reason 拒绝，不允许「两种证据取其一」（B-001） |
| 兼容 / 迁移 | 不带声明的既有证据行为逐字不变，`checks` 在 schema 中仍是 required；旧证据无需迁移（B-002 B-011） |
| 降级 / 回退 | 这是本 spec 引入的唯一降级路径，且必须产出带 `degraded:` 前缀的 satisfied 条目，禁止静默通过（B-009） |
| 证据 / 审计完整 | `workflow_trigger_evidence` 与 `local_verification` 均为必填并进入结论文本，降级理由可被事后审计（B-007 B-009） |
| 取消 / 中断 | 不适用：评估是同步纯函数调用，没有可中断的长任务或需要回滚的中间状态 |
