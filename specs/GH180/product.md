# Product Spec

## Linked Issue

GH-180

complexity: large

## 用户问题

SpecRail 目前对同一个 spec packet 给出互相冲突的生命周期要求：
`ready_to_spec` / `write_spec` 只负责形成 `product_spec` 与 `tech_spec`，而
`task_plan` 由 `ready_to_implement` / `implement` 阶段创建；但全量 packet 校验又把
缺少 `tasks.md` 一律视为失败。结果是新的 spec PR 只能在“遵守 route 但 CI 红”与
“提前写 tasks、越过 readiness 边界”之间二选一，也会让三文件齐全被误读为已经
获得实现授权。

## 目标

- 定义 staged spec packet 的单一生命周期，使 spec 写作与 task planning 各自由
  正确 route 和可信 readiness 触发。
- 将 packet 的 artifact shape 与 implementation readiness 分开判定，允许
  product/tech-only packet 通过全量结构校验，但绝不因此获得实现资格。
- 为 implement route 定义无循环依赖的 task plan 生成顺序。
- 保持既有三文件 packet 兼容，同时为 GH-180 自身及错误地提前生成 tasks 的在途
  spec PR 提供可审计、不可扩权的迁移路径。

## 非目标

- 不改变 issue #165 的 Gate Availability 行为契约。
- 不自动授予 `ready_to_implement`、`spec_approved` 或任何实现、审批、merge 权限。
- 不删除 task planning，也不允许代码实现先于有效 `tasks.md` 开始。
- 不把 issue body hint、文件存在、agent 自报或历史成功结果升级为可信 readiness。
- 不弱化 product、tech 或 tasks 各自已有的内容校验。

## Behavior Invariants

1. B-001 当一个 packet 含有效 `product.md` 与 `tech.md`、且不含 `tasks.md` 时，
   其 artifact shape 必须判为 `staged`；`--all-specs` 必须将其视为合法的 spec
   阶段 packet，而不是因为缺少 `tasks.md` 报全面失败。
2. B-002 当一个 packet 同时含有效 `product.md`、`tech.md` 与 `tasks.md` 时，
   其 artifact shape 必须判为 `complete`，并继续执行三类 artifact 的全部既有
   内容约束。
3. B-003 `staged`、`complete` 与 implementation readiness 是不同维度：
   `complete` 只证明 artifact 齐全，不能单独证明 `ready_to_implement`、
   `spec_approved`、route 允许或实现授权；`staged` 也不得被呈现为
   implementation-ready。
4. B-004 当 `product.md` 或 `tech.md` 任一缺失、为空、不可读或内容无效时，packet
   必须判为非法；`tasks.md` 存在、旧成功记录或 readiness 证据均不得掩盖该失败。
5. B-005 当 `tasks.md` 存在但无效，packet 不得从 `complete` 降级成看似成功的
   `staged`；必须明确报告 task plan 失败。文件缺失与文件存在但无效具有不同、
   可审计的判定。
6. B-006 当可信当前状态为 `ready_to_spec` 且 `write_spec` route 为 `allowed` 时，
   route 只要求并创建 `product_spec` 与 `tech_spec`；不创建 `task_plan`，且
   product/tech 写成后必须能以 `staged` 形态通过 packet 校验。
7. B-007 当进入 `implement` route 时，入场前提必须是可信当前状态
   `ready_to_implement` 加有效 product/tech；入场检查不得预先要求尚应由该 route
   创建的 `task_plan`。route 创建并验证 `tasks.md` 后，代码实现才可开始，消除
   “先有 tasks 才能进入创建 tasks 的 route”循环。
8. B-008 从 spec 写作进入实现必须遵守
   `ready_to_spec → spec_pr_open → spec_review → spec_approved → ready_to_implement`
   的合法生命周期及当前 `auth_mode` 的人类 gate 规则；无论 packet 是 `staged`
   还是 `complete`，均不得以文件形态跳过状态转换。
9. B-009 readiness-sensitive 判定只能消费可信、当前、与 linked issue 一致的 label
   与 route evidence。缺 evidence、body hint、agent 声明、过期 label、错误 issue
   或互相冲突的 readiness label 均不能产生 implementation-ready 结论。
10. B-010 `--all-specs` 在没有 readiness evidence 时仍必须完整校验并报告 packet
    的 `staged` / `complete` artifact shape，但必须把 implementation readiness
    明确保留为“未证明”，不得把 evidence 缺失静默折算为允许实现。
11. B-011 既有有效三文件 packet 升级后继续判为 `complete`，无需删除或重写
    `tasks.md`；它们也不会因兼容处理而自动获得当前 implementation readiness。
    既有有效 product/tech-only packet 则按 `staged` 规则验证。
12. B-012 对仍处于 `ready_to_spec` 的在途 spec PR，若曾为迎合旧 validator 提前
    加入 `tasks.md`，在可信 `write_spec` route evidence 下删除该 task plan 必须是
    合法的纠偏，并把 packet 恢复为 `staged`；该纠偏不得制造
    `ready_to_implement` 或 spec approval 证据。
13. B-013 在 `ready_to_implement` 或更晚阶段删除、遗漏或破坏有效 `tasks.md`
    时，implementation-ready 判定必须失效并阻断代码实现；系统不得沿用删除前的
    readiness、验证或 task plan 证据。
14. B-014 同一 packet 被并发修改、linked issue 状态变化，或 evidence 采集后
    artifact snapshot 漂移时，readiness-sensitive 结果必须失效并要求基于最新
    状态重新判定；旧结果不得授权新内容。
15. B-015 对相同 artifact snapshot 与相同 evidence 重复校验必须得到同一 shape
    与 readiness 结论；失败后重试必须重新验证全部前提，不能只修一个字段后复用
    旧的成功片段或 rejection 之前的授权。
16. B-016 GH-180 在旧 validator 下的 bootstrap 必须分两阶段并留下真实证据：先以
    live issue #180 的 `ready_to_spec` label、`state_source: label`、
    `state_trusted: true` 与 `write_spec: allowed` 创建并验证 product/tech；随后只有本次
    `auth_mode: auto` 已明确记录 spec-approval waiver 并把 live issue 合法迁移到
    `ready_to_implement` 后，重新采集 current issue/duplicate evidence 且
    `implement: allowed`，才可创建 `tasks.md` 使 GH-180 自身在旧 CI 下形成完整 packet。
    任一阶段不得伪造 readiness，且 task plan 完成前不得开始生产代码实现。
17. B-017 B-016 的 bootstrap 必须限于 GH-180 本次 lifecycle-contract 迁移并被显式
    记录；evidence 缺失、采集失败、权限不足、issue/head/packet 不匹配、未完成真实状态
    转换或迁移完成后的其它 packet 均不得复用该例外。新 validator 落地后，在途
    `ready_to_spec` packet 必须使用 B-012 的 staged 纠偏路径，不能继续提前创建 tasks。
18. B-018 每次 packet 判定必须给出可审计结果，至少能区分 linked issue、artifact
    shape、发现的 artifact、各 artifact 校验结果、readiness 是否被证明、evidence
    来源与阻断原因；使用 bootstrap 或纠偏路径时还必须标明对应依据。
19. B-019 若校验、spec 写作或 task planning 被取消/中断，已落下的部分文件只能按
    当前真实 shape 重新校验；半写文件、临时成功状态与未完成 transition 不得被
    提升为 `staged`、`complete` 或 implementation-ready。

## 验收标准

- [ ] 有效 product/tech-only packet 被报告为 `staged` 并通过全量结构校验；补上
  有效 tasks 后被报告为 `complete`，两者均不会仅凭文件形态获得实现资格。
- [ ] 缺 product、缺 tech、无效 tasks、tasks-only 与空/不可读 artifact 均有
  稳定负例，且不得通过降级成 `staged` 掩盖错误。
- [ ] `write_spec` 在 `ready_to_spec` 只形成 product/tech；`implement` 先凭可信
  `ready_to_implement` 与 product/tech 入场，再创建并验证 tasks，最后才允许代码实现。
- [ ] readiness 缺失、冲突、过期、错误 issue、body hint、自报状态与 artifact
  并发漂移均不能产生 implementation-ready 结论。
- [ ] 既有完整 packet 保持兼容；提前生成 tasks 的 `ready_to_spec` 在途 PR 可以在
  可信 route evidence 下删除 tasks 并恢复为 `staged`。
- [ ] GH-180 bootstrap 先接受 live `ready_to_spec` + `write_spec: allowed` 形成
  product/tech，再记录本次 auto waiver、真实迁移到 `ready_to_implement` 并以 fresh
  evidence 获得 `implement: allowed` 后创建 tasks；任一步缺证、伪造或跨 issue 复用均失败。
- [ ] 同一输入重复校验结果稳定，失败重试、取消和中断不会复用旧授权或产生部分成功。
- [ ] validator、route 与审计输出对同一 packet 的 shape、readiness 和阻断原因一致。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001, B-004, B-005, B-009（缺 tasks 是合法 staged；缺 product/tech、空文件或缺 evidence 分别 fail closed） |
| 错误与失败路径 | covered: B-004, B-005, B-013, B-017, B-019（无效 artifact、采集/权限失败、部分写入均不可伪装成功） |
| 授权/权限 | covered: B-003, B-008, B-009, B-016, B-017（shape 不授权；只接受可信 readiness/route evidence） |
| 并发/竞态 | covered: B-014（artifact、issue 状态或 evidence snapshot 漂移后必须重判） |
| 重试/幂等 | covered: B-015, B-019（同输入同结论；失败或中断后全量重验，不复用旧片段） |
| 非法状态转换 | covered: B-006..B-008, B-012, B-013（write_spec/implement 职责分离，禁止靠文件跳状态） |
| 兼容/迁移 | covered: B-011, B-012, B-016, B-017（旧完整 packet、提前 tasks 纠偏与 GH-180 两阶段 bootstrap 均有窄化合同） |
| 降级/回退 | covered: B-005, B-010, B-013, B-017（结构可验证不等于授权；错误 tasks/evidence 不得静默回退成功） |
| 证据与审计完整性 | covered: B-009, B-010, B-014..B-018（来源、snapshot、重试、bootstrap 与判定理由均可追溯） |
| 取消/中断 | covered: B-019（只认中断后的真实文件与状态，部分完成不升级） |

## 发布说明

这是 staged packet lifecycle 的兼容性迁移。升级后，product/tech-only packet 是
合法的 spec 阶段形态；既有三文件 packet 保持有效，但 artifact 齐全不再暗示
implementation readiness。GH-180 的一次性 bootstrap 必须按真实 `ready_to_spec` →
auto waiver 记录 → `ready_to_implement` 两阶段证据执行；其它在途 spec PR 必须使用
staged 纠偏，不能通过提前创建 tasks、伪造 readiness 或跳过校验完成迁移。
