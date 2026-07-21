# Product Spec

## Linked Issue

GH-166

## 用户问题

SpecRail 的评审/合并证据（CI rollup、独立 reviewer lane、terminal review summary）全部绑定 PR 的 exact head SHA，绑定粒度是「整个 commit」而非「证据实际覆盖的内容类别」。任何修订——哪怕只改 PR body 一句措辞或某个 markdown 规格文件的一行——head SHA 就变，先前采集的**全部**证据一律作废，触发全量 CI 重跑 + 独立审查重做。

机械绑定点（写作时经 Read 核实）：`checks/runtime_gate_rules.py:221`（terminal review head_sha 必须逐字等于 item head_sha）、`checks/github_pr_evidence.py:325`（pr_snapshot head_sha 不一致即拒绝）、`checks/github_pr_evidence.py:512`（采集期间 head 变化直接抛错要求全量重采）、`checks/pr_gate.py:325`（head_sha 作为整体证据键，无内容类别拆分）。

remem #907/#908 实测（2026-07-21）：一个 7.5h implx auto 会话产出 2 个 PR；只含 3 个 markdown 规格文件的 #907 换了约 8 个 head，remem CI 单一 job 每 head 跑全量 `cargo test`（13–17 分钟/轮），markdown-only 的 #907 把全量 Rust 套件跑了 6–8 遍，纯浪费约 1.5–2 小时；另有 2 次 PR body 手写 SHA 打错（06:38、06:42 UTC）各触发一轮纠正 + 证据重绑，PR 描述编辑触发重复 CI run（08:36 UTC 手动取消 2 个同 SHA run）。本 spec 编码「证据按内容类别绑定 hash」+「机械 SHA 字段必须脚本注入」两项方向，不重开质量机制本身的设计辩论（质量机制有效，问题只在成本模型）。

## 目标

- 引入内容类别证据绑定：证据按 `code_diff` / `spec_files` / `pr_metadata` 三类分别绑定各自 content hash，取代统一的 exact-head SHA 绑定；未变化类别的既有证据在新 head 上仍视为有效。
- 类别变化判定 fail-closed：任一类别 hash 缺失、无法计算、无法比对，或采集期证据不完整时，该类别按「已变化」处理，退回该类别全量取证，绝不静默复用旧证据。
- 机械字段脚本注入：PR body / evidence 中的 head SHA 一类机械字段必须携带脚本注入来源标记，检查侧拒绝无来源标记的手填 SHA，根除手写打错触发的无谓重绑。
- 把上述语义接入既有强制点：`checks/github_pr_evidence.py` 的 head 采集与 snapshot 一致性、`checks/pr_gate.py` 的证据项、`checks/runtime_gate_rules.py` 的 terminal review head 一致性、`checks/runtime_ledger_gate.py` 的 merge-ready 证据校验。

## 非目标

- 不弱化任何既有 fail-closed 语义：CI、reviewer-lane、review-thread、pr_gate、runtime ledger gate、self-review authorization、Bounded Tranche 规则全部保持；本 spec 只细化证据绑定粒度，不放宽任何 gate 结论。
- 不改变 #97 确立的「敏感/enforcement-sensitive 合并绑定 terminal review 证据」硬要求；只把其绑定粒度从 exact-head 细化到内容类别，敏感面证据的复用条件不得弱于现状。
- 不引入跨仓库缓存、远程 hash 存储或网络调用；hash 在本地证据采集阶段计算。
- 不改变任何 human gate（`spec_approval`、`final_pr_review`、`merge`、`security_decision`、`release`）。
- 不改变 `auth_mode` 语义（auto / review 的授权模型不动）。
- 不新增 tier 分类体系，不与 GH-143 的 tier 授权语义交叉。

## Behavior Invariants

1. B-001 当采集 PR 证据时，系统应为该 head 计算并记录三类内容 hash：`code_diff_hash`（规范化后的代码 diff 内容 hash）、`spec_files_hash`（spec packet 下受版本管理的规格文件内容 hash）、`pr_metadata_hash`（PR body/标题等元数据 hash）；三类 hash 与 head SHA 一并写入证据，作为后续复用判定的锚点。
2. B-002 当 PR 产生新 head，且新 head 的 `code_diff_hash` 与既有 CI/代码审查证据绑定的 `code_diff_hash` 逐字相同时，该 CI/代码审查证据应被判定在新 head 上仍然有效，不因 head SHA 变化而作废，无需重跑该类别取证。
3. B-003 当 PR 产生新 head，且新 head 的 `spec_files_hash` 与既有规格类审查证据绑定的 `spec_files_hash` 逐字相同时，该规格类证据应被判定在新 head 上仍然有效，不因 head SHA 变化而作废。
4. B-004 当某类别的内容 hash 相对既有证据发生变化时，只有该变化类别需要重新取证；其余未变化类别的既有证据不受影响，仍按 B-002/B-003 复用。
5. B-005 当 `pr_metadata_hash` 变化而 `code_diff_hash` 与 `spec_files_hash` 均未变化时，任何 CI 证据与 review 证据都不因该元数据变化而作废；纯 PR-body/元数据修订不得触发 CI 或 review 重跑。
6. B-006 当任一类别的内容 hash 缺失、无法计算、无法与既有证据比对，或证据未记录该类别 hash 时，该类别应按「已变化」fail-closed 处理，要求该类别重新全量取证，不得静默复用旧证据。
7. B-007 当证据中出现机械字段 head SHA（PR body 记录的 head、evidence 的 `head_sha`/`gate_query_head_sha` 等）时，该字段必须携带脚本注入来源标记（表明其由 `git rev-parse` 一类命令产出）；缺少来源标记的手填 SHA 应被检查侧拒绝为无效证据。
8. B-008 当脚本注入的 head SHA 与实际采集到的 live head 不一致时，判定为证据陈旧/污染并拒绝，要求重新注入，不得以任一侧为准静默通过。
9. B-009 当 `checks/runtime_gate_rules.py` 校验 terminal review 与 item head 的一致性时，若新 head 的 `code_diff_hash` 与 review 绑定的 `code_diff_hash` 相同（代码类内容未变），terminal review 应被判定仍有效，不因 head_sha 逐字不等而失效；`code_diff_hash` 变化或缺失时维持现状按 head_sha 严格一致要求（fail-closed）。
10. B-010 当 PR 触及 enforcement-sensitive 面（GH-97 语义）时，敏感面证据的复用不得弱于现状：敏感相关证据的类别复用只在对应内容 hash 逐字一致时成立，任一相关类别 hash 缺失或变化即要求重新取证并重新绑定 terminal review，fail-closed 不放宽。
11. B-011 当证据采集期间 live head 发生变化时，系统应按变化类别重新采集受影响类别的证据；未受影响类别的既有 hash 与证据仍可复用，但采集完成后记录的三类 hash 必须对应同一最终 head，不得混绑不同 head 的类别 hash。
12. B-012 当以类别复用（B-002/B-003/B-005）通过某个 gate 时，证据/checkpoint 应留存完整审计记录：三类内容 hash、各类别所复用证据的原绑定 hash 与来源、以及机械 SHA 字段的注入来源标记；审计字段缺失时相关 gate 应判定 blocked，不得事后补记。

## 验收标准

- [ ] 证据模型区分 `code_diff` / `spec_files` / `pr_metadata` 三类内容 hash，各类独立绑定并可独立复用，有测试覆盖
- [ ] 纯 PR-body 或纯 spec-markdown 修订产生新 head 时，未变化类别的既有 CI/review 证据被判定仍有效、不触发该类别重跑，有测试覆盖
- [ ] 类别变化判定 fail-closed（hash 缺失/无法计算/无法比对按已变化），敏感面复用不弱于 #97 现状，有测试覆盖
- [ ] 机械 SHA 字段必须携带脚本注入来源标记，手填/无来源 SHA 被检查侧拒绝，有测试覆盖
- [ ] `python3 checks/check_workflow.py --repo .` 与既有 pr_gate/runtime_ledger_gate/github_pr_evidence 测试兼容回归全绿

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-006 B-012（类别 hash 缺失或未记录 fail-closed 按已变化；审计字段缺失即 blocked） |
| 错误与失败路径 | covered: B-006 B-008（hash 无法计算/比对退回全量取证；注入 SHA 与 live head 不一致即拒绝） |
| 授权/权限 | N/A：本 spec 不改变 human gate 与 auth_mode 授权模型，只改证据绑定粒度；授权项证据仍按现状校验 |
| 并发/竞态 | covered: B-011（采集期 live head 变化时按类别重采，最终三类 hash 必须对应同一 head，禁止混绑） |
| 重试/幂等 | covered: B-002 B-003（同一 content hash 的重复复用判定结论一致，只读幂等，无跨进程状态） |
| 非法状态转换 | covered: B-011 B-012（混绑不同 head 的类别 hash 为非法状态；缺审计字段的类别复用被 blocked） |
| 兼容/迁移 | covered: B-009 B-010（新增 hash 字段缺失时回退现状 exact-head 严格校验；敏感面不弱于 #97） |
| 降级/回退 | covered: B-006 B-009（一切歧义显式降级为「已变化/严格一致」，退回全量取证，不静默取轻） |
| 证据与审计完整性 | covered: B-007 B-012（机械 SHA 需注入来源标记；类别复用须留存三类 hash 与原绑定审计记录） |
| 取消/中断 | covered: B-011（采集中断/head 变化时按类别重采，未受影响类别证据保留但需重新对齐最终 head） |

## 发布说明

新增三类内容 hash 字段全部可选：未声明这些字段的既有 checkpoint/evidence 走现状 exact-head 严格校验路径，输出零变化（B-009/B-010 兼容回归护住），无数据迁移。实现顺序建议：先在 `checks/github_pr_evidence.py` 采集侧产出三类 hash 与注入来源标记，再让 `checks/pr_gate.py` / `checks/runtime_gate_rules.py` / `checks/runtime_ledger_gate.py` 在证据声明了类别 hash 时启用类别复用判定；采集侧字段未被消费前零行为变化，可安全分步合入。本实现 PR 自身触及 gate/enforcement 证据语义，按 heavy/敏感流程逐 PR 人工授权合并。
