# Tech Spec

## Linked Issue

GH-202

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":202,"complete":true,"paths":["checks/github_pr_evidence.py","checks/github_pr_snapshot.py","checks/pr_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/runtime_tier_authorization.py","integrations/threads.md","schemas/pr_review_authorizations.schema.json","schemas/pr_review_gate.schema.json","schemas/runtime_checkpoint.schema.json","schemas/runtime_tier_authorization.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","specs/GH202/product.md","specs/GH202/tasks.md","specs/GH202/tech.md","tests/test_github_pr_evidence.py","tests/test_github_pr_evidence_approval.py","tests/test_pr_gate.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py"],"spec_refs":["specs/GH202/product.md","specs/GH202/tech.md","specs/GH202/tasks.md"]}
-->

## Product Spec

见 `specs/GH202/product.md`。本设计覆盖 B-001..B-010。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| runtime tier rules | `checks/runtime_tier_authorization.py:33`、`checks/runtime_tier_authorization.py:47` | 只校验 `changed_lines` 类型和非空路径；敏感性仅在值为 `true` 时阻断。 | B-001..B-003 的当前 fail-open 根因。 |
| runtime self-review dispatch | `checks/runtime_gate_rules.py:286` | `basis=fastlane_policy` 直接进入弱校验并跳过普通 lane-failure 路径。 | 需要保留封闭豁免而非通用 bypass。 |
| runtime PR binding | `checks/runtime_ledger_gate.py:201`、`checks/runtime_ledger_gate.py:218` | 复制 content binding；只有 item 自报敏感为 `true` 时才对比 PR gate。 | B-005/B-009 需要双向、完整绑定。 |
| PR review gate | `checks/pr_gate.py:486` | 统一检查 review contract，但现有 self-review 授权仍以 lane failure 为前提。 | 需要只为可信 fastlane basis 增加 PR 层判定。 |
| PR evidence adapter | `checks/github_pr_evidence.py:454`、`checks/github_pr_evidence.py:526` | current-head 前后各采一次文件 snapshot，但没有输出可信 tier 分类。 | B-004 的主要 evidence 入口。 |
| GitHub file snapshot | `checks/github_pr_snapshot.py:89` | 收集完整 touched paths 并检测分页/漂移，尚未汇总 REST 文件 additions/deletions。 | 可在现有 exact-head 边界内取得 `changed_lines`。 |
| authorization schemas | `schemas/pr_review_authorizations.schema.json:26`、`schemas/runtime_tier_authorization.schema.json:11` | schema 接受 self-review 和 tier evidence 的形状，未表达可信来源/current head。 | 缺失字段必须在 schema 与 gate 双重 fail closed。 |
| PR/runtime schemas | `schemas/pr_review_gate.schema.json:789`、`schemas/runtime_checkpoint.schema.json:631` | 两个持久化面尚未强制 fastlane basis 的组合字段。 | 防止一层实现、一层仍接受不完整证据。 |
| regression tests | `tests/test_runtime_ledger_gate.py:104`、`tests/test_pr_gate.py:394`、`tests/test_github_pr_evidence_approval.py:425` | 已覆盖自评、runtime tier 和 snapshot 基础行为。 | 追加 fail-open 复现与 exact-head 分类用例。 |

## 设计方案

### 1. 单一确定性 fastlane 分类器

`checks/runtime_tier_authorization.py` 暴露可供 PR gate/runtime gate 共同调用的
确定性验证逻辑。默认 fastlane 阈值为 50 changed lines；受保护路径至少覆盖
API/schema、migration、auth/security 与 CI workflow。输入缺失、路径不完整、
布尔值伪装成整数、未知来源或超阈值均返回阻断原因。checkpoint 自报只作为待核对
副本，不能作为事实来源。

### 2. exact-head GitHub tier evidence

扩展 `collect_pr_file_snapshot`：在现有 REST 分页稳定性检查中汇总每个文件的
`additions + deletions`，并保留排序后的完整路径集合。`github_pr_evidence` 仅在
`self_review_authorization.basis=fastlane_policy` 时派生：

- `pr_tier=fastlane`；
- `pr_tier_evidence.changed_lines`；
- `pr_tier_evidence.touched_paths`；
- evidence source、head SHA 与 snapshot identity；
- 由受保护路径分类得到的显式 `enforcement_sensitive=false`。

若 head before/after、REST/GraphQL path snapshot 或分类结果不一致，adapter 抛出
evidence error，不生成部分允许结果。

### 3. PR gate 封闭豁免

扩展 self-review authorization schema/builder，显式记录 `basis` 与
`conversation_marker`。`pr_gate` 只有在 basis 为 `fastlane_policy` 且可信 tier
evidence/current head/显式非敏感全部通过时，才不要求 `lane_failures`。其它 basis
或普通 self-review 继续使用现有 lane-failure 授权。review artifact/manifest、CI、
threads、linked issue、clean merge state 和 merge authorization 仍由现有 gate
统一评估。

### 4. Runtime 与 PR gate 精确绑定

`runtime_ledger_gate` 读取本地 `pr_gate` 终态 artifact 后，fastlane self-review
必须精确复制：

- `pr_tier`；
- `pr_tier_evidence`；
- `enforcement_sensitive`；
- tier evidence 的 head/source/snapshot binding；
- 既有 content binding。

缺字段、不一致、旧 head 或 `pr_gate != allowed` 均阻断。runtime 自身再次运行共享
分类器，形成 defense in depth。

### 5. 合同与 lock

queue/implx/threads 文字明确：fastlane 自评是 reviewer-lane 前置的窄豁免，不是
review artifact、CI 或 merge authorization 豁免。schema 改动与 Skill 最终字节
确定后更新 `skills-lock.json`。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | shared fastlane classifier + PR gate | `.venv/bin/python -m pytest -q tests/test_pr_gate.py tests/test_runtime_ledger_gate.py` |
| B-002 | explicit sensitive classification | `.venv/bin/python -m pytest -q tests/test_pr_gate.py tests/test_runtime_ledger_gate.py tests/test_specrail_schema.py` |
| B-003 | threshold/protected-path fail-closed | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py tests/test_github_pr_evidence_approval.py` |
| B-004 | snapshot line totals + head race | `.venv/bin/python -m pytest -q tests/test_github_pr_evidence.py tests/test_github_pr_evidence_approval.py` |
| B-005 | runtime copy of PR gate tier fields | `.venv/bin/python -m pytest -q tests/test_runtime_ledger_gate.py` |
| B-006 | terminal local review contract | `.venv/bin/python -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py tests/test_review_result_semantics.py` |
| B-007 | review authorization separation | `.venv/bin/python -m pytest -q tests/test_pr_gate.py tests/test_runtime_ledger_authorization.py` |
| B-008 | auto mode gate preservation | `.venv/bin/python -m pytest -q tests/test_runtime_gate_rules.py tests/test_runtime_ledger_gate.py` |
| B-009 | drift/content binding invalidation | `.venv/bin/python -m pytest -q tests/test_github_pr_content_binding.py tests/test_runtime_ledger_gate.py` |
| B-010 | partial/error collection | `.venv/bin/python -m pytest -q tests/test_github_pr_evidence_approval.py tests/test_runtime_ledger_gate.py` |

## 数据流

```text
GitHub exact-head file pages
  -> stable touched_paths + additions/deletions
  -> deterministic protected-path/threshold classification
  -> PR evidence (tier + source/head/snapshot + sensitive=false)
  -> pr_gate + exact-head local review/CI/thread/merge checks
  -> allowed pr_gate artifact
  -> runtime checkpoint exact copy + shared classifier recheck
  -> merge authorization gate
```

GitHub adapter 保持只读；runtime/pr gates 保持离线，不添加远端写。

## 备选方案

- 继续信 checkpoint 自报：无法防止实现者把 heavy 改动标成 fastlane，拒绝。
- 仅检查 PR body 的 `enforcement_sensitive:false`：PR 作者可控且不能证明完整路径，
  拒绝。
- 仅依赖 reviewer tier attestation：self-review 中不存在独立证明方，且会错误解锁
  `standard_auto`，拒绝。
- fastlane 一律禁用：安全但失去 #202 的成本目标；采用可信 current-head 窄通道。

## 风险

- Security: 路径分类漏项会放宽 review；缺失/未知必须 fail closed，consumer 可叠加
  更严格 registry。
- Compatibility: 旧 fastlane self-review checkpoint 将被拒绝并回退独立 lane。
- Performance: 复用已存在的 PR file snapshot，只增加线性汇总与确定性路径判断。
- Maintenance: classifier 必须由 PR/runtime 两层共享，避免阈值和保护路径漂移。

## 测试计划

- [ ] Unit: threshold、protected paths、缺失敏感性、布尔/负数/超大行数。
- [ ] Integration: GitHub paginated snapshot -> evidence -> PR gate -> runtime gate。
- [ ] Regression: review artifact、authorization、content binding、schema 与 workflow。
- [ ] Manual: 重放已发现的 `changed_lines=100000`/缺失敏感性绕过样例并确认阻断。

## 回滚方案

整体回滚 GH-202 的 adapter/gate/schema/合同与规格提交。回滚会恢复 reviewer lane
前置要求；不得只回滚 shared classifier 而保留 `pr_gate` 豁免，以免重现 fail-open。
