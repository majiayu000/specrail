# Product Spec

## Linked Issue

GH-142

## 用户问题

GH-130 的 `--gate`（PR #132）只拦截新增 spec。main 上 46 个 spec 在默认阈值下有 35 个 FAIL（audit 实测：有锚点 16/46、边界≥5 类 12/46、EARS≥60% 仅 7/46），集中在 GH5–GH63 老区段。GH97 已示范浅 spec 的代价：0 锚点/边界 2 类 → 一题 7 个 PR 连环补漏（#99→#102→#103→#109→#114→#115）。存量浅 spec 处于"既不达标、也未被禁止作为实现依据"的第三态，后续 issue 引用它们时没有任何拦截。

## 目标

- 全库 46 个 spec 收敛到二态：gate 达标（含 trivial 豁免）或显式 `status: legacy`；audit 汇总无第三态。
- legacy spec 被禁止作为新实现的依据：implement 路由遇到 legacy spec 时判 blocked，强制走 needs_spec 重写。
- 处置方式采用混合方案：活跃区段回填达标（GH1、GH95、GH97、GH100、GH104、GH106、GH111 共 7 个），其余 28 个老区段 spec 显式标记 legacy。

## 非目标

- 不改变 v3 指标语义与默认阈值（8/8/5），不为存量 spec 降低门槛。
- 不改动 trivial 豁免通道（GH130 B-004/B-005 语义不变）。
- 不删除或重写 legacy spec 正文；标记是追加式的。
- 不接入 CI 强制（是否把全库 `--gate` 挂进 CI 由消费方另行决定）。

## Behavior Invariants

1. B-001 当 spec 的 `product.md` 在 Linked Issue 小节内声明 `status: legacy` 时，`spec_depth_audit.py --gate` 应将该 spec 判定为 legacy 态：豁免深度阈值判定，并在 gate 输出中列入独立的 legacy 名单（与 trivial exempt 名单分开）。
2. B-002 如果 `status: legacy` 字样只出现在 Linked Issue 小节之外（正文引用、示例、代码块，包括整个文件不存在 Linked Issue 小节而标记落在正文的情形），工具应不将其视为 legacy 声明，沿袭 GH130 B-005 的小节限定语义。
3. B-003 当 `--gate` 审计任意集合时，允许状态应恰为二态：达标（含 trivial 豁免）或显式 legacy；若存在任一"未达标且未标记 legacy"的第三态 spec，工具应以退出码 1 结束并逐项输出 FAIL 原因。
4. B-004 当同一 `product.md` 同时声明 `complexity: trivial` 与 `status: legacy` 时，legacy 应优先生效，该 spec 在 gate 输出中只出现在 legacy 名单，不出现在 trivial exempt 名单。
5. B-005 当 implement 路由（`checks/route_gate.py`）的 linked issue 对应 spec packet 的 `product.md` 声明 legacy 时，路由判定应为 blocked：missing 含 `non_legacy_spec`，reasons 明确指向 needs_spec 重写；即使 product/tech/tasks 三件齐备且状态标签合法，legacy spec 也不得作为 `spec_status: complete` 的依据。
6. B-006 当 spec 未声明 legacy 时，implement 路由与非 `--gate` 的 audit 调用行为应与现状完全一致（零回归：输出列、退出码、决策语义不变）。
7. B-007 当 legacy 判定所需的 `product.md` 存在但读取失败时，route_gate 应 fail-closed 报错并判 blocked，不得静默视为非 legacy 放行。
8. B-008 当 backfill 集合（GH1、GH95、GH97、GH100、GH104、GH106、GH111）完成回填后，每个 spec 应通过 `--gate` 默认阈值（8/8/5）；不得通过降低阈值、追加 `complexity: trivial` 或标记 legacy 来规避回填。
9. B-009 当执行 legacy 标记 sweep 时，目标集合应由审计输出机械枚举（`--gate` 的 FAIL 列表减去 backfill 白名单），不得手工挑选；实现 PR 中应附当次枚举命令与输出作为证据。
10. B-010 当为 spec 标记 legacy 时，只允许在 Linked Issue 小节追加一行显式文本；若目标 `product.md` 为老格式、不存在 Linked Issue 小节（本 spec 写作时为 GH5、GH7、GH9、GH13 共 4 个），允许在文件末尾追加一个最小 Linked Issue 小节（`## Linked Issue` 标题行 + `GitHub issue: #<n>` 行 + `status: legacy` 行，共 +3 行）；两种情形均为纯追加，不得删除或改写原 spec 既有内容；追加后的最小小节即为 B-001 语义下的 Linked Issue 小节，标记应被工具识别；摘除 legacy 标记的唯一途径是重写该 spec 使其通过 `--gate` 默认阈值。
11. B-011 当 `--gate` 输出汇总时，应报告二态计数（达标数、trivial 豁免数、legacy 数），且三者之和等于被审计 spec 总数（无第三态时）；退出码 0 与该等式同时成立才算通过。
12. B-012 当调用方不传 `--gate` 时，audit 表格与汇总的既有列语义、退出码应保持兼容；legacy 信息仅以增量列或增量行形式出现。

## Acceptance Criteria

- [ ] `status: legacy`（Linked Issue 小节内）使 spec 进入 legacy 态并豁免阈值；小节外出现不生效
- [ ] implement 路由对 legacy spec 判 blocked 且 missing 含 `non_legacy_spec`，有测试覆盖
- [ ] 28 个老区段 spec 全部标记 legacy，标记集合可由枚举命令复现；其中 4 个无 Linked Issue 小节的老格式 spec（GH5、GH7、GH9、GH13）以追加最小小节的方式标记且被 gate 识别为 legacy
- [ ] 7 个 backfill spec 通过 `--gate` 默认阈值
- [ ] `python3 tools/spec_depth_audit.py --repo . --gate` 全库退出码 0，汇总二态计数完整
- [ ] `specs/GH142` 自身通过 `--gate` 默认阈值（dogfood）

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-003 B-007 B-010（未标记的浅 spec 视为第三态 FAIL；product.md 读取失败 fail-closed；老格式 spec 缺失 Linked Issue 小节时追加最小小节，追加后标记必须被解析器识别，而落在任何 Linked Issue 小节之外的标记依 B-002 仍不计——负例） |
| Error / failure paths | covered: B-003 B-007（gate FAIL 逐项输出；路由读取失败判 blocked） |
| Authorization / permission | covered: B-005（legacy spec 不得作为 implement 路由的 complete 依据，齐备文件也无授权效力） |
| Concurrency / race | N/A: 单进程只读审计与本地路由判定，无共享可变状态 |
| Retry / idempotency | covered: B-006 B-011（审计与路由判定只读幂等，重复运行输出与计数一致） |
| Illegal state transitions | covered: B-004 B-005 B-010（trivial+legacy 冲突以 legacy 优先；legacy→complete 是被阻断的非法转移；摘除标记必须先达标） |
| Compatibility / migration | covered: B-006 B-012（未标记 spec 与非 gate 调用零回归；legacy 信息仅增量出现） |
| Degradation / fallback | covered: B-001 B-010（legacy 是显式可见的降级态，不允许静默降级或伪装达标） |
| Evidence / audit integrity | covered: B-009 B-011（sweep 集合由审计输出机械枚举并留证；汇总计数等式作为完整性证据） |
| Cancellation / interruption | N/A: 短生命周期 CLI 与只读判定，无长事务；中断后重跑幂等 |

## Rollout Notes

先合 tooling（audit legacy 态 + route_gate 阻断），再做 sweep 与 backfill；sweep 与 backfill 可并行（spec 目录互不相交）。全库 `--gate` 通过后，本 issue 的验收命令可作为后续 CI 接入的现成入口。
