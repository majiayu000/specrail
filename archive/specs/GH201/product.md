# Product Spec

## Linked Issue

GH-201

## 用户问题

native lane 若继承协调者的完整会话历史，input token 会随会话年龄增长，并把无关的
命令输出、先前 issue 和已结束决策复制到每个 implementer/reviewer。实际 lane
完成任务通常只需要任务、目标 ref、规格路径与紧凑 carry；全历史 fork 既增加成本，
也提高过时上下文影响判断的风险。

## 目标

- 所有 lane 统一使用最小、显式、可审计的 context pack。
- 禁止 `fork_turns: all` 或等价的协调者全历史复制。
- 缺少上下文时追加具名文件/证据，而不是退回全历史 fork。

## 非目标

- 不限制 lane 按需读取其任务范围内的仓库文件。
- 不改变 reviewer independence、文件所有权或 merge gate。
- 不要求把用户私有 session/transcript 固化到仓库。

## Behavior Invariants

1. B-001 当系统派发任意 implementer、reviewer、planner、audit 或 merge lane 时，
   context pack 必须只包含任务描述、目标 diff/branch ref、相关 spec 路径和紧凑 carry。
2. B-002 系统不得对任何 lane 使用 `fork_turns: all`、完整协调者 transcript 或等价
   full-history 注入；角色类型不能作为例外。
3. B-003 当 lane 报告上下文不足时，协调者必须追加明确的文件路径、稳定 artifact ID
   或当前证据摘要；不得通过扩大到完整父历史解决。
4. B-004 当 reviewer 执行 re-review 时，优先恢复既有 reviewer lane；无法恢复时，
   新 lane 只接收增量 diff、相关 spec 与 typed prior-findings carry。
5. B-005 当命令产生大输出时，原始 stdout/stderr 必须写入 artifact，lane/父上下文只
   接收退出状态、有界 tail、目标 grep 与 artifact 路径。
6. B-006 当任务恢复、compaction 或 handoff 发生时，系统必须从 durable repo/SpecRail
   artifacts 和 fresh remote truth 重建最小 context；不得读取旧 transcript 或 raw
   session JSONL 作为 live state。
7. B-007 当 context pack 缺少完成任务所需的具名输入且无法安全补齐时，lane 必须停止
   并报告缺失项，不得猜测字段、路径或旧决策。
8. B-008 当多个 lane 并发时，每个 writable lane 必须仍持有显式且不重叠的文件所有权；
   最小上下文不得被解释为省略 ownership、stop condition 或 verification owner。

## 验收标准

- [ ] queue 与 threads integration 对所有 lane 使用相同 minimal context contract。
- [ ] 明确禁止 full-history fork，包括等价行为。
- [ ] context 不足只能通过 targeted paths/artifacts 补充。
- [ ] re-review 使用 resume 或 diff-only compact carry。
- [ ] 大输出与 handoff 保持 artifact-first，不读取 raw session 作为 truth。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-007 |
| 错误与失败路径 | covered: B-003 B-007 |
| 授权/权限 | covered: B-006；不读取未授权 transcript/session |
| 并发/竞态 | covered: B-008 |
| 重试/幂等 | covered: B-004 B-006 |
| 非法状态转换 | covered: B-007 B-008 |
| 兼容/迁移 | covered: B-003；旧执行器可传显式 context pack |
| 降级/回退 | covered: B-003 B-007 |
| 证据与审计完整性 | covered: B-001 B-005 B-006 B-008 |
| 取消/中断 | covered: B-006 B-007 |

## 发布说明

这是 agent orchestration 输入边界的收敛。lane 仍可读取必要仓库上下文，但必须由任务
和显式路径驱动，而不是继承父会话的全部历史。
