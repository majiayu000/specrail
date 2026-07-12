# Product Spec

## Linked Issue

GH-88

## 用户问题

SpecRail 的队列契约允许一个 issue 由多个 PR 分片完成：中间分片使用
`Refs #<issue>` 保持 issue 开放，最终分片才使用 closing keyword。但当前 PR
evidence 只认识 GitHub `closingIssuesReferences`，导致合法 partial PR 被投影为
`linked_issue: null` 并在 merge gate 中阻塞。

这会迫使执行者在“误关未完成 issue”和“无法通过门禁”之间二选一，也使队列
已经声明的 `completion_mode: partial | final` 无法落到实际证据链。

## 目标

- 让调用方能够为 PR 指定一个预期 issue，并采集可审计的 `partial` relation。
- 保持 issue 关联证据与 issue closure 意图为两个独立概念。
- 对缺失、歧义、不存在、已关闭或不匹配的 partial 引用 fail closed。
- 保持既有 closing-reference evidence 与离线 fixture 兼容。

## 非目标

- 不把正文中任意 `#N`、分支名或标题自动提升为可信 partial relation。
- 不改变 GitHub closing keyword 或 sidebar link 的语义。
- 不让 evidence adapter、`pr_gate.py` 或 agent 获得关闭 issue 的权限。
- 不放宽 CI、review、thread、merge-state 或 human-authorization 门禁。

## Behavior Invariants

1. B-001 未显式指定预期 issue 时，现有 `closingIssuesReferences` 路径行为保持
   不变；已有 closing evidence 继续产生相同的 `linked_issue`。
2. B-002 非关闭式 relation 只能由调用方显式指定预期 issue 后采集；adapter
   不得从任意正文 token、标题或分支名猜测目标 issue。
3. B-003 partial PR 正文必须包含与预期 issue 精确匹配的独立
   `Refs #<issue>` 引用；普通提及、错号、数字前缀命中或 `Fixes` 文本均不满足。
4. B-004 partial relation 只在预期 issue 能从同一 GitHub repository 查询到且
   live state 为 `OPEN` 时成立；不存在、跨仓替代、编号不一致或已关闭均拒绝。
5. B-005 有效 relation 产生结构化、可审计的 issue-reference evidence，至少
   记录 issue number、`kind`、`source` 与 `verified`；兼容字段
   `linked_issue` 必须投影为同一 number。
6. B-006 `kind: partial` 必须与 `source: pr_body`、`verified: true`、
   `state: OPEN` 同时成立；任一字段缺失、为空、越界或互相矛盾时
   `pr_gate.py` 判为 `blocked`。
7. B-007 `kind: closing` 必须来自 `closingIssuesReferences`；partial evidence
   不得伪装或升级为 closing evidence。
8. B-008 显式预期 issue 决定 gate 投影的唯一目标；同一 PR 可以为其他 bounded
   issue 携带 closing reference，但 collector 必须完整保留这些编号供审计，且不得
   用“第一个”closing issue 覆盖显式目标。只有预期 issue 自身出现在 closing
   references 中时，才可把该目标判为 `closing`；否则必须按 B-003/B-004 验证
   `partial`，既不能误升格也不能因其他 closing issue 拒绝真实 mixed relation。
9. B-009 PR 正文、head SHA 或 closing references 在一次 gate query 中发生变化
   时，证据采集失败并要求重跑，不得组合不同时刻的 relation 与 review 证据。
10. B-010 adapter 报告的 partial evidence 可满足 merge-readiness 的
    `linked_issue` 要求，但不得产生 closure/final-completion 字段或动作，也不得成为
    issue closure、完成度或 final-slice 证明；预期 partial issue 必须保持 `OPEN`。
11. B-011 存量手写 evidence/fixtures 只有合法 `linked_issue`、没有新结构化字段
    时继续按原契约评估；新 adapter 输出则必须携带自洽的结构化 relation。
12. B-012 同一稳定远端状态下重复采集产生相同的 relation 语义；网络、权限、
    JSON 或 live issue 查询失败均显式报错，不得降级为成功或猜测结果。

## 验收标准

- [x] 有效 `Refs #N`、显式 issue N 与 live OPEN issue 产生已验证 partial evidence。
- [x] missing、mismatched、closed、nonexistent、ambiguous 与漂移路径均有负例测试。
- [x] mixed relation（预期 `Refs #N` + 其他 `Closes #M`）保留全部 closing 编号，
      但 `linked_issue` 仍稳定投影为 N。
- [x] `pr_gate.py` 接受自洽 partial evidence并拒绝不完整/矛盾 evidence。
- [x] 既有 closing path、fixture 与无新字段的离线 evidence 保持兼容。
- [x] schema、skills、usage 文档与 deterministic checks 同步通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002, B-003, B-006 |
| 错误与失败路径 | covered: B-004, B-008, B-009, B-012 |
| 授权/权限 | covered: B-012；查询权限失败必须显式报错，merge 授权仍由既有 gate 负责 |
| 并发/竞态 | covered: B-009 |
| 重试/幂等 | covered: B-012 |
| 非法状态转换 | covered: B-004, B-006, B-007 |
| 兼容/迁移 | covered: B-001, B-011 |
| 降级/回退 | covered: B-012；禁止 silent fallback |
| 证据与审计完整性 | covered: B-005, B-006, B-008, B-010 |
| 取消/中断 | N/A：collector 为一次性只读命令；中断后从头重跑，不保存部分状态 |

## 发布说明

这是向后兼容的 evidence-contract 扩展。调用方仅在采集 partial relation 时需要
新增显式 issue 参数；closing-reference 调用保持不变。
