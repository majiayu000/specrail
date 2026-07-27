# Tech Spec

## Linked Issue

GH-199

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":199,"complete":true,"paths":["skills-lock.json","skills/specrail-implement-queue/SKILL.md","specs/GH199/product.md","specs/GH199/tasks.md","specs/GH199/tech.md"],"spec_refs":["specs/GH199/product.md","specs/GH199/tech.md","specs/GH199/tasks.md"]}
-->

## Product Spec

见 `specs/GH199/product.md`。本设计覆盖 B-001..B-008。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| runtime budget | `checks/runtime_budget_dimensions.py:159`、`checks/runtime_budget_dimensions.py:168`、`checks/runtime_budget_dimensions.py:184` | 校验 `full_test_head_sha` 存在并与 current PR head 对齐。 | 现有确定性预算是文档合同的机器边界。 |
| queue budget declaration | `skills/specrail-implement-queue/SKILL.md:474` | 声明 `max_full_test_runs_per_head` 与 `full_test_head_sha`。 | 绑定本地完整测试次数和 head。 |
| test layering | `skills/specrail-implement-queue/SKILL.md:594`、`skills/specrail-implement-queue/SKILL.md:602` | 区分迭代 focused tests、首次 full-suite 与 review-fix CI 路径。 | GH-199 的主要可执行合同。 |
| readiness verification | `skills/specrail-implement-queue/SKILL.md:694` | merge readiness 前汇总 focused、deterministic、CI 与 spec 对照。 | 防止性能优化绕过最终证据。 |
| CI coverage registry | `workflow.yaml:69`、`workflow.yaml:73` | repo 配置声明 check 覆盖的内容类别。 | 只有已知覆盖类别可参与证据复用。 |
| PR evidence reuse | `checks/pr_gate.py:191`、`checks/pr_gate.py:209` | 校验复用组件与 current content bindings。 | exact-head 复用继续由 gate fail closed。 |

## 设计方案

### 1. 三层测试职责

queue Skill 使用唯一顺序：

1. 编辑循环只跑 focused tests；
2. 首个 merge-candidate head 跑一次本地 full-suite，记录
   `full_test_head_sha`；
3. review-fix 新 head 跑 focused tests，并在 build/test 输入未变化且 CI coverage
   已声明时，消费 current-head 绿色 CI。

### 2. 失效条件

以下任一条件使 CI 替代路径失效：check 缺失或非绿色、check 未声明覆盖
`code_inputs`/`spec_files` 中的实际变更类别、build/test 配置被修改、证据采集期间 head
变化。执行者必须重新取得完整证据或报告阻断。

### 3. 预算与审计

`max_full_test_runs_per_head` 不因 review-fix 自动清零。若政策要求重跑而预算不允许，
checkpoint 必须显示冲突并交给人类，不得删除旧计数。`skills-lock.json` 在 Skill
最终字节确定后刷新。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | queue test layering | `rg -n "During iteration, run only the focused tests" skills/specrail-implement-queue/SKILL.md` |
| B-002 | queue full-suite contract + runtime budget | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_budget.py` |
| B-003 | review-fix current-head CI path | `rg -n "review-fix|CI rollup" skills/specrail-implement-queue/SKILL.md` |
| B-004 | CI failure/coverage invalidation wording | `.venv/bin/python -m pytest -q tests/test_github_pr_content_binding.py tests/test_pr_gate.py` |
| B-005 | content binding and exact-head semantics | `.venv/bin/python -m pytest -q tests/test_review_content_binding.py tests/test_pr_gate_terminal.py` |
| B-006 | `workflow.yaml` coverage registry + PR evidence | `.venv/bin/python -m pytest -q tests/test_github_pr_content_binding.py` |
| B-007 | append-only runtime budget conflict | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_budget.py` |
| B-008 | exact-head snapshot/race handling | `.venv/bin/python -m pytest -q tests/test_github_pr_evidence.py tests/test_pr_gate.py` |

## 数据流

```text
edit -> focused tests
     -> merge-candidate head -> one local full suite -> full_test_head_sha
     -> review-fix head -> focused tests
                        -> declared current-head CI coverage
                        -> PR evidence/content binding
                        -> pr_gate
```

所有数据均为本地 checkpoint 或 GitHub read-only evidence；本变更不增加持久化和远端写。

## 备选方案

- 每个 head 无条件重跑 full-suite：安全但重复等待最大，拒绝。
- 永远只信 CI：consumer CI 可能不覆盖完整套件，拒绝。
- 按文件名启发式猜 CI 覆盖：不可审计，拒绝；覆盖必须来自 repo 配置和 evidence。

## 风险

- Security: 错误复用会让未覆盖改动进入 merge gate；未知覆盖必须 fail closed。
- Compatibility: existing exact-head artifacts 继续有效；只澄清执行纪律。
- Performance: 对正常 review-fix 去掉重复本地 full-suite。
- Maintenance: 文档合同必须与 runtime budget 和 content-binding tests 一起验证。

## 测试计划

- [ ] Unit: runtime budget 与 content-binding tests。
- [ ] Integration: `check_workflow.py --repo . --spec-dir specs/GH199`。
- [ ] Regression: 全量 pytest、all-specs、diff check、Skill lock。
- [ ] Manual: 核对 queue 文本同时包含 CI 替代条件与 fail-closed 失效条件。

## 回滚方案

回滚 GH-199 的 queue 文本、规格包和对应 lock hash。回滚后恢复旧的保守执行指导，
不会改变 gate 数据格式。
