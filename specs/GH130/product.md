# Product Spec

## Linked Issue

GH-130

## 用户问题

GH-93 已入库只读深度审计，但深度纪律仍是建议式：全库 33 份 spec 仅 4 份达到深 spec 水平（边界覆盖 >=5 类），浅 spec 驱动的合并后补漏返工持续复发（fix PR 占比约 27.5%，GH-97 单 issue 消耗 7 个 PR）。GH-59 盲测已证明深 spec 能事前抓到真实漏洞。GH-93 的非目标一节把阻断门禁列为 Phase 2 另行立项，本 spec 即该 Phase 2：给 `tools/spec_depth_audit.py` 增加 `--gate` 硬判定与 trivial 豁免。

## 目标

- 调用方可用一条命令对指定 spec 集合做深度硬判定，未达标即非零退出并给出逐项原因。
- trivial 变更保留明确的低成本豁免通道，避免把小修逼成大 spec packet。

## 非目标

- 不改动 `checks/`、`workflow.yaml`、CI 配置；是否接入 CI 由消费方决定。
- 不回溯性要求存量 spec 达标；gate 只判定本次被审计的集合。
- 不改变 v3 指标语义（`metric_semantics` 版本不变，历史数字仍可对比）。
- 不把 EARS 占比纳入阻断（GH88/GH91 深 spec 在 v3 条件式语义下占比为 0%，启发式不稳定）；仅在模板补写作指引。

## Behavior Invariants

1. B-001 当未传入 `--gate` 时，工具行为与现状完全一致：输出审计表格与汇总，退出码语义不变。
2. B-002 当传入 `--gate` 且被审计集合中存在非 trivial 且任一指标未达阈值的 spec 时，工具应以退出码 1 结束，并对每个未达标 spec 逐项输出指标名、实际值与阈值。
3. B-003 当传入 `--gate` 且所有被审计 spec 均达标或被豁免时，工具应以退出码 0 结束，并在汇总后输出 gate 通过行。
4. B-004 当 spec 的 `product.md` 在 Linked Issue 小节内声明 `complexity: trivial` 时，该 spec 应豁免全部深度阈值，且在 gate 输出中标注为 exempt。
5. B-005 如果 `complexity: trivial` 字样只出现在 Linked Issue 小节之外（例如正文引用或示例），工具应不将其视为豁免声明。
6. B-006 当传入 `--min-invariants`、`--min-boundary` 或 `--min-anchors` 时，gate 应使用传入阈值替代默认值；默认阈值为 invariants>=8、boundary>=8、anchors>=5，依据 GH86/GH88/GH91 深 spec 基线（inv 9–12、边界 10/10、锚点 7–14）。
7. B-007 EARS 占比在 gate 判定中应始终不参与阻断，仅作为审计信息输出。
8. B-008 当被审计集合为空、显式目录缺 `product.md`、或 glob 无匹配时，现有 fail-closed 行为应保持不变：非零退出且不输出伪结果。
9. B-009 gate 模式下工具应保持只读，不写入或修改任何仓库文件（继承 GH-93 B-001）。
10. B-010 当非 trivial spec 缺失 `tech.md` 时，锚点计为 0 并照常参与判定，工具应不因文件缺失而崩溃或跳过该 spec。

## Acceptance Criteria

- [ ] `--gate` 对未达标非 trivial spec 非零退出并逐项列出原因
- [ ] `complexity: trivial`（Linked Issue 小节内）豁免阈值判定；小节外出现不豁免
- [ ] 三项阈值 CLI 可覆盖，默认值与深 spec 基线一致
- [ ] 无 `--gate` 时输出与退出码与现状一致
- [ ] `specs/GH130` 自身通过 `--gate` 默认阈值（dogfood）

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-008 B-010 |
| Error / failure paths | covered: B-002 B-008 |
| Authorization / permission | N/A: 本地只读工具，无权限面 |
| Concurrency / race | N/A: 单进程只读扫描，无共享可变状态 |
| Retry / idempotency | covered: B-009（只读且无副作用，天然幂等） |
| Illegal state transitions | N/A: 无状态机 |
| Compatibility / migration | covered: B-001 B-006（默认行为不变，阈值可覆盖） |
| Degradation / fallback | covered: B-007（EARS 降为信息位而非静默参与阻断） |
| Evidence / audit integrity | covered: B-002 B-003（阻断与通过均有显式输出证据） |
| Cancellation / interruption | N/A: 短生命周期 CLI，无长事务 |

## Rollout Notes

纯新增 CLI 开关，默认不启用，对现有调用方零影响。消费方接入 CI 时建议只对新增 spec 目录启用 `--gate`（`--spec-dir specs/GHxxx --gate`），存量 spec 不回溯。
