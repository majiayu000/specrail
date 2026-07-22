# Product Spec

## Linked Issue

GH-165

## 用户问题

`specrail-workflow`、`specrail-implement`、`specrail-plan-tasks`、
`specrail-write-tech-spec`、`specrail-write-product-spec`、
`specrail-triage-issue`、`specrail-diagnose-ci` 与
`specrail-release-note` 把各自的 mandatory gate 表述为 “when available”，却没有定义
gate 缺失或执行失败时的行为。调用方因此可能在未接入 SpecRail 的仓库中跳过门禁，继续
产出看似经过 SpecRail 校验的路由、规格、计划、实现、诊断或发布结论；其中路由器的静默
降级还会把未经验证的前提传给所有下游 skill。

## 目标

- 为八个目标 skill 建立一致、可观察且 fail-closed 的 Gate Availability 契约。
- 让 gate 存在、缺失、执行失败与人工授权降级成为互斥且可审计的结果。
- 阻止未接入 SpecRail 的仓库、路由器或叶子 skill 把未校验路径表现为 SpecRail 成功。
- 保留人工在知情后选择普通或降级工作流的能力，同时限制授权作用域并明确披露结果。
- 用确定性规则阻止 mandatory gate 再次退化为只有 “when available” 的可选措辞。

## 非目标

- 不为未接入 SpecRail 的仓库自动安装、复制或生成 gate。
- 不改变 `route_gate.py` 已定义的 decision 语义、状态机或各 route 的业务准入条件。
- 不把队列 auto 授权、普通执行授权或历史授权自动扩张为 gate-unavailable 授权。
- 不规定具体检查器、共享文件、schema 或 skill 分发机制；这些属于技术规格。
- 不把其他可选集成（例如 reviewer lane、外部适配器或线程能力）的 “when available”
  一概视为 mandatory route gate 缺陷。

## Behavior Invariants

1. B-001 当八个目标 skill 声明某个 gate 为 route 前提时，该 gate 必须是进入对应
   SpecRail route 的 mandatory precondition；仅出现 “when available” 而未定义缺失行为，
   不构成完整契约。
2. B-002 当 `specrail-workflow` 选择或分派 route 时，必须先确定该 route 所需 gate 的
   可用性并处理其 decision；上游未验证、缺失或失败的结果不得作为已通过前提传给下游
   skill。
3. B-003 当声明的 gate 存在且可执行时，目标 skill 必须在产生对应 route 的完成结论或
   外部可见结果前执行它，并按 gate 的真实 decision 处理；只有 `allowed` 可以表述为
   gate passed，其他 decision 不得改写、遗漏或表述为无条件成功。
4. B-004 当声明的 gate 文件缺失时，目标 skill 必须停止 SpecRail route，明确说明仓库未
   提供所需 gate，并且不得投机执行一个已知不存在的命令或静默切换为成功路径。
5. B-005 当 gate 因解释器、权限、依赖、输出格式、进程退出或其他运行错误而未产生有效
   decision 时，结果必须等价于 gate unavailable，而不是 `allowed`；失败原因必须在用户
   可见结果中保持可辨识。
6. B-006 当 gate unavailable 且当前人工在获知缺失 gate、影响与替代路径后明确授权继续
   时，目标 skill 才可执行显式 degraded operation；授权必须限定到当前 repository、route
   与 task/run，不得自动覆盖其他 skill、其他仓库或后续运行。
7. B-007 当只有普通执行授权、`implx auto` 队列授权、历史授权、推断授权或事后追认时，
   它们均不得替代 B-006 的 gate-unavailable 专用授权；缺少该专用授权时结果必须停止并
   请求人工决定。
8. B-008 当 degraded operation 被授权时，其用户可见结果或 handoff 必须包含稳定标记
   `SpecRail gate status: unavailable`，并记录 route、未执行成功的 gate、unavailable
   原因以及非空的人工授权内容或可追溯引用。
9. B-009 当结果带有 `SpecRail gate status: unavailable` 时，该结果不得声称自身
   SpecRail-gated、verified、gate passed、merge-ready 或已满足后续 gate；普通或降级任务
   的产物可供人工检查，但不能充当缺失门禁的通过证据。
10. B-010 当 degraded 状态、披露标记、失败原因与授权证据任一缺失、为空、相互矛盾或
    作用域不匹配时，该结果必须 fail closed；“已授权 + 无 gate 前提证据”仍不得表现为
    成功。
11. B-011 当叶子 skill 被直接调用而未经过 `specrail-workflow` 时，它必须独立执行同一
    Gate Availability 契约；不得借用路由器、其他 skill、其他 lane 或其他 route 的 gate
    结果。
12. B-012 当同一仓库中并发或交错运行多个 route 时，每次 gate 结果必须绑定到其对应的
    repository、route 与 task/run；下游动作不得因另一个并发调用已通过而提前开始，也
    不得用较早调用的结果覆盖当前失败。
13. B-013 当 gate 返回拒绝 decision、unavailable 或 degraded evidence 不完整时，重试
    必须使用当前前提重新评估，并保留先前失败供审计；重复执行、重复授权或后续成功不得
    删除失败记录，也不得把旧结果改写为成功。
14. B-014 当当前 workflow state 不允许目标 route 时，即使 gate 可用、曾经通过或存在
    degraded 授权，也不得跳过非法状态转换；Gate Availability 不扩张 route 权限。
15. B-015 当已接入 SpecRail 的仓库提供有效 gate 时，现有合法 route 与 decision 行为
    保持兼容；本变更只把 gate 缺失、无效执行和误导性成功从隐式行为收紧为显式停止或
    授权降级。
16. B-016 当未接入 SpecRail 的仓库调用目标 skill 时，默认结果必须是显式停止 SpecRail
    route，并可说明普通非 SpecRail 工作流这一替代选项；不得自动安装 gate，也不得把
    替代工作流冠以 SpecRail 已校验的名称。
17. B-017 当调用在 gate 执行、人工授权或 route 产出之间被取消或中断时，未完成调用不得
    留下成功结论；恢复后必须针对当前 repository、route 与 task/run 重新确认 gate 状态，
    不能沿用无法证明完整的部分结果。
18. B-018 当分发或验证目标 skill 集时，任何 mandatory gate 若只有条件式可选措辞而没有
    gate 存在、缺失、执行失败与人工降级行为，验证必须确定性拒绝；八个目标 skill 必须
    同时满足同一规则，不能只修复单个样本。

## 验收标准

- [ ] 八个目标 skill 均明确区分 gate 存在且产生有效 decision、gate 缺失、gate 执行失败
      与人工授权 degraded operation 四条路径。
- [ ] `specrail-workflow` 在选路和下游分派之前 fail closed，叶子 skill 直接调用时也执行
      同一契约。
- [ ] 未接入 SpecRail 的仓库默认不会执行必然失败的 gate 命令，也不会产生看似
      SpecRail-gated 的成功结论。
- [ ] 普通执行、`implx auto`、历史或事后授权不能替代当前 repository/route/task/run 的
      gate-unavailable 专用授权。
- [ ] 合规 degraded 结果包含稳定标记、失败原因与授权证据；缺失、空白、矛盾或越界组合
      均被拒绝，且 degraded 结果不能满足下游 gate。
- [ ] 并发、重试与中断后恢复均不能借用、覆盖或丢失其他调用和先前失败的 gate 证据。
- [ ] 已接入 SpecRail 且 gate 有效的既有 route 保持原有 decision 行为，非法状态转换仍
      被阻断。
- [ ] 确定性验证能一次性暴露八个目标 skill 中所有不完整 Gate Availability 契约，而非只
      报告或修复一个样本。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-004, B-008, B-010 |
| 错误与失败路径 | covered: B-003, B-005, B-010, B-013 |
| 授权/权限 | covered: B-006, B-007, B-010, B-014 |
| 并发/竞态 | covered: B-002, B-011, B-012 |
| 重试/幂等 | covered: B-012, B-013 |
| 非法状态转换 | covered: B-002, B-014 |
| 兼容/迁移 | covered: B-015, B-016, B-018 |
| 降级/回退 | covered: B-004, B-005, B-006, B-008, B-009, B-016 |
| 证据与审计完整性 | covered: B-008, B-009, B-010, B-011, B-013 |
| 取消/中断 | covered: B-017 |

## 发布说明

这是一次 fail-closed contract 收紧。已提供有效 gate 的 SpecRail 仓库继续按既有 decision
运行；未接入或 gate 无法执行的仓库将不再静默获得 SpecRail 成功结论。维护者可选择先接入
所需 gate、改用明确标识的普通非 SpecRail 工作流，或在知情后为当前
repository/route/task/run 单独授权 degraded operation。该变更不会自动安装 gate，也不会
把现有队列授权扩张为缺失门禁授权。
