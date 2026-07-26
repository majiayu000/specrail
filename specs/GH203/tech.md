# Tech Spec

## Linked Issue

GH-203

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":203,"complete":true,"paths":["skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement/SKILL.md","specs/GH203/product.md","specs/GH203/tasks.md","specs/GH203/tech.md"],"spec_refs":["specs/GH203/product.md","specs/GH203/tech.md","specs/GH203/tasks.md"]}
-->

## Product Spec

见 `specs/GH203/product.md`。本设计覆盖 B-001..B-010。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| shortcut eligibility | `skills/implx/SKILL.md:46`、`skills/implx/SKILL.md:50` | scoped work 选择 bounded mode；shortcut 接受 `complete` 或 `exception_allowed`。 | B-001/B-004 的资格根因。 |
| shortcut route | `skills/implx/SKILL.md:53`、`skills/implx/SKILL.md:57` | 直接路由 implement + PR gate，并声明 heavy/coupling/missing spec 回退。 | 需要补完整证据链与 done-when。 |
| primary review contract | `skills/implx/SKILL.md:223` | 全局 Threads 段要求 exact-head local terminal artifact。 | shortcut 必须显式继承而非依赖远处隐含文字。 |
| bounded coverage | `skills/specrail-implement-queue/SKILL.md:49`、`skills/specrail-implement-queue/SKILL.md:53` | full drain 全分类；bounded 只分类 target/linked PR。 | B-002/B-003 的性能边界。 |
| spec statuses | `skills/specrail-implement-queue/SKILL.md:60`、`skills/specrail-implement-queue/SKILL.md:70` | `complete` 要三件套；`exception_allowed` 是小型无 spec 例外。 | 两类不能被 shortcut 等同。 |
| done-when gate | `skills/specrail-implement-queue/SKILL.md:79` | 要求 checklist、acceptance criteria 或 verification command。 | B-001/B-004 的收敛条件。 |
| scoped implement | `skills/specrail-implement/SKILL.md:12`、`skills/specrail-implement/SKILL.md:25` | 读取 packet、跑 route gate、focused verification。 | shortcut 的实施主路径。 |
| implement boundaries | `skills/specrail-implement/SKILL.md:34` | 只说 passing PR gate，没有明确 artifact/manifest 生成步骤。 | B-007 的合同缺口。 |
| queue readiness evidence | `skills/specrail-implement-queue/SKILL.md:692`、`skills/specrail-implement-queue/SKILL.md:702` | 明确 exact-head review、CI、threads、gate、tier 与 authorization。 | shortcut 必须保持同等级门禁。 |
| PR gate serial order | `skills/specrail-pr-gate/SKILL.md:76`、`skills/specrail-pr-gate/SKILL.md:83` | PR query、review provenance 与 merge dispatch 必须串行。 | B-007..B-010 不得被 shortcut 弱化。 |

## 设计方案

### 1. 封闭的 shortcut 资格

在 `skills/implx/SKILL.md` 把 shortcut 条件写成 conjunction：

- prompt 明确只命名一个 issue；
- `spec_status=complete`，即 product/tech/tasks 全部存在且非 legacy；
- done-when gate 可判定；
- 初步风险不高于 standard；
- remote truth 未显示 multi-issue coupling/ownership conflict。

删除 `exception_allowed` 资格。任何条件未知都回退
`specrail-implement-queue`，不能猜测“应该是小改动”。

### 2. 只省略 queue-only 产物

shortcut 明确省略：全仓 coverage classification、queue-planning YAML、tranche
budget/checkpoint。保留：startup、target packet 读取、duplicate-work evidence、
implement route gate、spec/implementation 对照、focused/full verification、review
artifact/manifest、GitHub evidence、PR gate 与 merge authorization。

`bounded_tranche` 继续留在 queue skill；它只分类目标 issue/linked PR，但仍使用
queue plan/checkpoint，因为范围可能包含多个 item。

### 3. exact-head review evidence

在 shortcut 段和 `specrail-implement` 的 GitHub PR 收口步骤中加入明确动作：

1. 由 local CLI 或 native reviewer lane 产生 review JSON；
2. 生成/更新 manifest，terminal artifact 绑定 current head；
3. 运行 `review_json_gate.py` 与 manifest semantics；
4. `github_pr_evidence.py` 必须用 `--review-manifest`，不得只提供
   `--review-source`；
5. 执行 fresh `pr_gate.py`，然后才可报告 readiness 或 dispatch merge。

fastlane 若使用 #202 self-review，其 artifact/manifest 规则相同。

### 4. 漂移与回退

head、目标 packet 或风险变化后重跑资格核对。发现 heavy、耦合或 spec 不再 complete
时，记录 shortcut fallback reason 并进入 queue skill；不得继续沿用已省略的计划假设。
Skill 修改完成后刷新 `skills-lock.json`。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | implx closed eligibility | `rg -n "Single-issue short circuit|spec_status.*complete|done-when" skills/implx/SKILL.md` |
| B-002 | shortcut omitted artifacts list | `rg -n "full-queue coverage|queue-planning|tranche budget" skills/implx/SKILL.md` |
| B-003 | queue coverage scope | `rg -n "full_queue_drain.*classify|bounded_tranche.*classify" skills/specrail-implement-queue/SKILL.md` |
| B-004 | complete-only + no exception | manual contract inspection of `skills/implx/SKILL.md` and `skills/specrail-implement-queue/SKILL.md` |
| B-005 | fallback closed set | `rg -n "multi-issue|heavy|ownership|fall back" skills/implx/SKILL.md` |
| B-006 | duplicate + implement route | `rg -n "duplicate-work|route gate|route_gate.py" skills/implx/SKILL.md skills/specrail-implement/SKILL.md` |
| B-007 | exact-head artifact/manifest | `rg -n "exact-head|review-manifest|review_json_gate" skills/implx/SKILL.md skills/specrail-implement/SKILL.md` |
| B-008 | retained PR evidence classes | `rg -n "CI|review threads|merge state|pr_gate" skills/implx/SKILL.md skills/specrail-implement/SKILL.md` |
| B-009 | authorization separation | `rg -n "Authorization Mode|human authorization|standing merge" skills/implx/SKILL.md` |
| B-010 | drift/re-entry | `rg -n "head changes|eligibility|fall back" skills/implx/SKILL.md` |

## 数据流

```text
explicit one-issue scope
  -> target-only remote/spec qualification
  -> complete packet + decidable done-when + non-heavy?
       no  -> queue skill / human route
       yes -> duplicate evidence -> implement route gate
           -> scoped implementation + verification
           -> exact-head local review JSON + manifest
           -> current GitHub PR evidence + serial pr_gate
           -> applicable merge authorization
```

无新 schema 或 runtime 持久化格式；本变更只收紧 agent-facing route contract。

## 备选方案

- 保留 `exception_allowed`：会让“无 spec 例外”被错误解释为“spec 完整”，拒绝。
- shortcut 仍进入 queue skill 再立刻返回：保留了要消除的启动成本，拒绝。
- 只依赖 PR gate 最终报缺证据：失败发生太晚且容易形成重复 review round，拒绝。
- 单 issue 一律不使用 reviewer lane：tier 与 review independence 是另一维度，拒绝。

## 风险

- Security: 错分 heavy 为 shortcut 会省略风险规划；未知风险回退 queue。
- Compatibility: `exception_allowed` 调用不再 shortcut，但仍可走正常显式例外流程。
- Performance: complete scoped issue 避免 O(open issues) 分类和三类 queue 产物。
- Maintenance: shortcut 证据链需与 implement/PR gate 保持引用一致。

## 测试计划

- [ ] Contract: 搜索资格、回退、exact-head artifact/manifest 与 retained gates。
- [ ] Integration: GH203 packet/depth/workflow/Skill lock。
- [ ] Regression: review semantics、PR gate 与 workflow full suite。
- [ ] Manual: 分别演练 complete、exception_allowed、heavy、head-drift 四种路由。

## 回滚方案

回滚 implx/implement/queue 合同、GH203 packet 与 lock hash。回滚只恢复旧启动成本；
不得保留 shortcut 路由同时删除 exact-head artifact 要求。
