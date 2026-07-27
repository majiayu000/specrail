# Tech Spec

## Linked Issue

GH-201

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":201,"complete":true,"paths":["integrations/threads.md","skills-lock.json","skills/specrail-implement-queue/SKILL.md","specs/GH201/product.md","specs/GH201/tasks.md","specs/GH201/tech.md"],"spec_refs":["specs/GH201/product.md","specs/GH201/tech.md","specs/GH201/tasks.md"]}
-->

## Product Spec

见 `specs/GH201/product.md`。本设计覆盖 B-001..B-008。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue dispatch | `skills/specrail-implement-queue/SKILL.md:320`、`skills/specrail-implement-queue/SKILL.md:322` | 定义 task/ref/spec/compact carry，并禁止协调者历史。 | B-001/B-002 的主入口。 |
| reviewer compact carry | `skills/specrail-implement-queue/SKILL.md:383`、`skills/specrail-implement-queue/SKILL.md:384` | reviewer 只接收 exact diff/spec/carry，并优先 resume。 | B-003/B-004。 |
| output firewall | `skills/specrail-implement-queue/SKILL.md:536`、`skills/specrail-implement-queue/SKILL.md:549` | 大输出进入 artifact，父上下文只看摘要。 | B-005。 |
| threads execution | `integrations/threads.md:48`、`integrations/threads.md:54` | integration 层规定 minimal pack 与 large-output summary。 | 所有 native lane 的共同合同。 |
| handoff truth | `integrations/threads.md:178`、`integrations/threads.md:181` | 禁止 raw session 作为 live state，使用 checkpoint/artifact。 | B-006。 |
| ownership | `skills/specrail-implement-queue/SKILL.md:329`、`skills/specrail-implement-queue/SKILL.md:335` | 明确 read-only/writable owner 与 worktree test boundary。 | B-008。 |

## 设计方案

### 1. Minimal context pack

queue 与 threads integration 固定四类输入：

- task statement；
- exact diff 或 branch ref；
- linked spec packet paths；
- compact carry（typed findings、阻断项、已验证命令摘要）。

禁止项包括完整 conversation、raw transcript、历史 tool output 和
`fork_turns: all` 等价物。

### 2. Targeted expansion

lane 缺少信息时，协调者补充一个具名路径、artifact 或 remote evidence 摘要。每次补充
必须能解释与当前任务的关系。无法安全定位时 lane 返回 missing context，不猜测。

### 3. Resume 与 output firewall

re-review 优先 message/resume 既有 lane；新 lane 只获得增量 diff 与 typed carry。
长测试/CI 的 raw output 写入 `artifacts/logs/<tranche>/`，父上下文只消费有界摘要。

### 4. Handoff 和并发

handoff 只引用 runtime checkpoint、spec packet、branch/head 和 fresh GitHub truth。
每个 writable lane 的 ownership 仍是显式不重叠集合，shared verification 由单一
coordinator 负责。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | queue/threads minimal pack | `rg -n "minimal context pack|task statement|compact carry" skills/specrail-implement-queue/SKILL.md integrations/threads.md` |
| B-002 | full-history prohibition | `rg -n "fork_turns: all|full-history" skills/specrail-implement-queue/SKILL.md integrations/threads.md` |
| B-003 | targeted file-path expansion | `rg -n "explicit file paths|context pack" skills/specrail-implement-queue/SKILL.md` |
| B-004 | reviewer resume/diff-only | `.venv/bin/python -m pytest -q tests/test_review_result_semantics.py tests/test_pr_gate_terminal.py` |
| B-005 | output firewall | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_budget.py tests/test_runtime_ledger_gate.py` |
| B-006 | handoff/live truth wording | `rg -n "raw Codex session|transcript|live queue state" integrations/threads.md AGENTS.md` |
| B-007 | missing-context fail-closed | manual contract inspection of queue dispatch and lane stop conditions |
| B-008 | lane ownership/worktree boundary | `rg -n "disjoint|shared verification|worktree" skills/specrail-implement-queue/SKILL.md integrations/threads.md` |

## 数据流

```text
coordinator durable truth
  -> task + ref/diff + specs + compact carry
  -> lane
     -> targeted path/artifact request (optional)
     -> bounded result + artifact paths
  -> coordinator verification
```

不新增 schema 或持久化字段；这是 spawn 输入与 handoff 行为合同。

## 备选方案

- fork 最近 N turns：N 与任务无关，仍可能复制敏感/陈旧信息，拒绝。
- reviewer 全历史、implementer 最小上下文：角色例外会继续造成成本漂移，拒绝。
- 只靠提示词建议：两处 agent-facing contract 必须明确禁止行为，不能依赖习惯。

## 风险

- Security: 全历史可能泄露无关上下文；显式路径降低暴露面。
- Compatibility: 旧 runtime 若不能选择 fork 范围，应使用新 lane + explicit pack。
- Performance: 减少缓存重放和 compaction 压力。
- Maintenance: queue 与 threads 必须保持同一 closed contract。

## 测试计划

- [ ] Unit: bounded review、runtime output-firewall tests。
- [ ] Integration: GH201 packet/depth/workflow checks。
- [ ] Regression: full pytest、all-specs、lock、diff。
- [ ] Manual: 搜索两处合同，确认没有任何 lane 角色例外。

## 回滚方案

回滚 queue/threads 的 minimal-context 段落、GH201 packet 与 lock hash。无数据迁移。
