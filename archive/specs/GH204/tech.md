# Tech Spec

## Linked Issue

GH-204

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":204,"complete":true,"paths":["integrations/threads.md","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","specs/GH204/product.md","specs/GH204/tasks.md","specs/GH204/tech.md","tests/test_review_contract_docs.py"],"spec_refs":["specs/GH204/product.md","specs/GH204/tech.md","specs/GH204/tasks.md"]}
-->

## Product Spec

见 `specs/GH204/product.md`。本设计覆盖 B-001..B-011。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue authority | `skills/implx/SKILL.md:12`、`skills/implx/SKILL.md:15` | wrapper 声明 queue planning/checkpoint/closure 由 queue Skill 权威定义。 | B-001 的入口。 |
| queue block | `skills/specrail-implement-queue/SKILL.md:201` | 唯一完整 `specrail_implementation_queue` YAML block。 | B-001/B-002 稳定结构。 |
| threads extension | `integrations/threads.md:133`、`integrations/threads.md:138` | threads 引用 queue block，并只追加 orchestration extension。 | B-002 的单一事实源边界。 |
| checkpoint single record | `skills/specrail-implement-queue/SKILL.md:285`、`integrations/threads.md:145` | dispatch gate 只写 checkpoint；handoff/report 引用。 | B-003/B-004。 |
| implx handoff | `skills/implx/SKILL.md:262`、`skills/implx/SKILL.md:279` | wrapper handoff 使用 `thread_dispatch_gate_ref` 指向 checkpoint。 | B-003/B-004 的消费者。 |
| small-file conflict | `integrations/threads.md:28`、`integrations/threads.md:71` | 小单文件一般不用 threads；GitHub review 例外由 fastlane policy 统一。 | B-005/B-006。 |
| fastlane contract | `skills/specrail-implement-queue/SKILL.md:308`、`skills/specrail-implement-queue/SKILL.md:393` | fastlane self-review 可替代 native lane，其他 evidence 不豁免。 | 必须与 GH202 的可信分类绑定。 |
| checkpoint cadence | `skills/specrail-implement-queue/SKILL.md:611`、`skills/specrail-implement-queue/SKILL.md:622` | 三个必写点 + material state change。 | B-007/B-010。 |
| closure cadence | `integrations/threads.md:60` | tranche 末对 touched work 批量 audit。 | B-008/B-009。 |
| durable truth | `skills/specrail-implement-queue/SKILL.md:634`、`integrations/threads.md:178` | checkpoint 是 handoff layer，fresh GitHub/spec 才是 durable truth。 | B-004/B-009/B-010。 |
| file size | `skills/specrail-implement-queue/SKILL.md:872` | 当前文件 872 行，超过 U-16 的 800 行硬上限。 | B-011 的明确阻塞。 |

## 设计方案

### 1. Queue block 与 extension

保留 queue Skill 中唯一完整的 `specrail_implementation_queue` 示例。implx 只声明
delegation；threads 使用不同名称的 orchestration extension，并明确它必须附加/引用
queue block。检查仓库中同名 key 的出现次数，禁止第二个完整定义。

### 2. Checkpoint 单点与引用

`thread_dispatch_gate`（含 native evidence）、`context_budget`、
`output_firewall` 只存在于 runtime checkpoint。`specrail_threads_handoff`、
`implx_handoff` 和 final report 只携带 checkpoint path/ref 与必要 resume metadata，
不得复制子字段。恢复时先运行 `runtime_ledger_gate.py` 并 refresh remote truth；
引用失效即阻断。

### 3. Reviewer 冲突决策表

| 条件 | 行为 |
| --- | --- |
| 非 GitHub/无需 review 的小单文件任务 | 不使用 threads |
| 可信 fastlane + `fastlane_policy` | 可 coordinator self-review；exact-head artifact 与其余 gates 必须 |
| standard/heavy、受保护路径、tier 未知 | native independent reviewer |
| native capability 不可用 | 记录 fallback；不得冒充 native evidence |

`fastlane_policy` 资格由 GH202 的可信 current-head 分类决定，本变更不再复制其阈值
或保护路径清单。

### 4. Cadence 与内容精简

checkpoint 仅在 tranche start、merge-ready 前、tranche end 和 material state
change 更新。closure audit tranche 末批量一次。精简 queue Skill 时优先：

- 删除与 implx/threads/专门 Skill 重复的解释性段落；
- 用具名 cross-reference 替代重复决策表；
- 合并重复 boundary/output 句子；
- 保留机器字段、closed-set 值、命令、异常和授权条件。

最终以 `wc -l` 验证 `<=800`，并运行全文关键词与现有 gate tests 防止语义丢失。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | queue authority + unique block | `test "$(rg -l '^specrail_implementation_queue:$' skills integrations | wc -l | tr -d ' ')" -eq 1` |
| B-002 | threads extension contract | `rg -n "authoritative queue block|orchestration extension|appended" integrations/threads.md` |
| B-003 | checkpoint-only fields | `rg -n "recorded exactly once|references the checkpoint|do not copy" skills/implx/SKILL.md integrations/threads.md skills/specrail-implement-queue/SKILL.md` |
| B-004 | handoff validation/recovery | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_runtime_ledger_budget.py` |
| B-005 | fastlane conflict resolution | `rg -n "fastlane_policy|small single-file" integrations/threads.md skills/specrail-implement-queue/SKILL.md` |
| B-006 | standard/heavy fallback | `rg -n "standard.*heavy|doubt.*tier|native reviewer" skills/specrail-implement-queue/SKILL.md integrations/threads.md` |
| B-007 | checkpoint cadence | `rg -n "three required points|tranche start|merge readiness|tranche end|material state" skills/specrail-implement-queue/SKILL.md` |
| B-008 | closure batch cadence | `rg -n "once per tranche|one batch|mid-tranche" integrations/threads.md` |
| B-009 | fresh truth conflict handling | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_closure_audit.py` |
| B-010 | hard-stop/minimal resume | `rg -n "raw Codex session|transcript|checkpoint and resume" skills/specrail-implement-queue/SKILL.md integrations/threads.md AGENTS.md` |
| B-011 | file size + workflow integrity | `test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 800 && .venv/bin/python checks/check_workflow.py --repo .` |

## 数据流

```text
queue skill authoritative plan
  -> runtime checkpoint
       - thread_dispatch_gate
       - context_budget
       - output_firewall
  -> implx/threads handoff refs (no copies)
  -> runtime_ledger_gate + fresh GitHub/spec truth on resume

threads orchestration extension
  -> references queue plan
  -> tranche-end batched closure audit
```

## 备选方案

- 把 queue block 移到 threads：没有 threads 的执行器会失去核心合同，拒绝。
- 让每个 handoff 内嵌快照：恢复方便但立即重建漂移源，拒绝。
- 删除 runtime checkpoint，完全依赖 GitHub：预算/output firewall/native dispatch
  不是 GitHub durable state，拒绝。
- 为小文件保留两套优先级规则：继续歧义，拒绝；统一引用 GH202 policy。

## 风险

- Security: 过度精简可能删除授权条件；关键词检查、focused tests 与独立 review 必须。
- Compatibility: handoff 的复制字段不再权威，但稳定 checkpoint field/schema 不变。
- Performance: 少重复写 checkpoint，closure audit 与合同加载更紧凑。
- Maintenance: cross-reference 目标改名会断链；workflow check 与 lock 捕获漂移。

## 测试计划

- [ ] Contract: 唯一 queue block、checkpoint-only refs、fastlane 决策表。
- [ ] Unit: runtime ledger、budget、review 和 closure audit。
- [ ] Integration: GH204 packet/depth、workflow、Skill lock。
- [ ] Regression: full pytest、all specs、diff check、queue line count。

## 回滚方案

整体回滚 threads/implx/queue 合同、GH204 packet 与 lock。若仅恢复重复 block，必须同时
恢复相应消费者，否则会产生两个权威版本；禁止只回滚引用的一侧。
