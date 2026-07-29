# Tech Spec

## Linked Issue

GH-88

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| GitHub PR collector fields | `checks/github_pr_evidence.py:15` | `PR_VIEW_FIELDS` 不采集 PR body，只读取 `closingIssuesReferences` | partial relation 必须读取稳定的正文引用 |
| Linked issue normalization | `checks/github_pr_evidence.py:372` | `normalize_linked_issue` 返回第一个 closing issue 或 `None` | 需要把 closing 与显式 partial relation 分开建模 |
| Evidence assembly/query | `checks/github_pr_evidence.py:462`, `checks/github_pr_evidence.py:511` | evidence 仅投影 `linked_issue`，query 只防 head SHA 漂移 | 需要采集 live issue 并防 relation 输入漂移 |
| Existing token matcher | `checks/github_duplicate_evidence.py:96` | 查重场景允许标题、分支、正文中的宽松 issue token | 已搜索但语义过宽，不能直接作为可信 partial 证明 |
| Offline PR gate | `checks/pr_gate.py:415` | 只检查 `linked_issue` 是否为正整数 | 需要校验新结构化 partial evidence 的内部一致性 |
| Evidence schema | `schemas/pr_review_gate.schema.json:6` | `linked_issue` 为必填 integer/null，且禁止额外字段 | 需要声明可选、向后兼容的结构化 relation |
| Adapter/gate tests | `tests/test_github_pr_evidence.py:27`, `tests/test_pr_gate.py:17` | 仅覆盖 closing issue fixture | 需要真实 GitHub-shaped partial/negative payload 回归 |
| Queue/PR-gate guidance | `skills/specrail-implement-queue/SKILL.md:80`, `skills/specrail-pr-gate/SKILL.md:12` | 前者声明 `Refs` partial，后者没有对应采集方式 | 必须闭合声明到执行的调用链 |

## 设计方案

### 1. 显式绑定预期 issue

为 `checks/github_pr_evidence.py` 增加可选 `--issue <number>`。不提供该参数时
保持现有 closing 路径；提供时，该 number 是唯一允许提升为 evidence 的目标。
这避免从标题、分支或任意 `#N` 猜测关联。

### 2. 分离 relation 采集

collector 增加 PR `body` 字段，并输出可选 `issue_reference`：

```json
{
  "linked_issue": 671,
  "issue_reference": {
    "number": 671,
    "kind": "partial",
    "source": "pr_body",
    "verified": true,
    "state": "OPEN",
    "closing_issue_numbers": [806]
  }
}
```

- collector 总是把稳定快照中的全部 closing references 归一化到
  `closing_issue_numbers`，不得只保留第一个；数组可为空。
- `closing`：显式目标自身位于 `closing_issue_numbers`，或调用方没有指定目标且沿用
  既有首个 closing projection；source 固定为 `closingIssuesReferences`。
- `partial`：只有显式 `--issue N`、正文精确 `Refs #N`、同仓 live issue N
  存在且为 `OPEN`，并且 N 不在 `closing_issue_numbers` 时成立，source 固定为
  `pr_body`。数组中存在其他 bounded closing issue 合法且必须保留审计。
- `linked_issue` 保留为兼容投影，必须与 `issue_reference.number` 一致。

宽松的 `references_issue_text` 已用于 duplicate-work discovery，它会接受标题、
分支和普通 token，不能满足 B-003。为 partial evidence 增加目的明确的严格 matcher，
只接受可见 Markdown 正文中的 `Refs` 关系，排除 fenced code、HTML comment 与缩进
代码，不创建第二个通用 matcher。为守住单文件 800 行硬上限，relation parsing 与
normalization 位于聚焦的 `checks/github_issue_reference.py`，collector 只负责查询与
组装；既有宽松 duplicate-work matcher 保持原位且不复用。

### 3. 只读 live issue 验证与稳定性

新增只读 `gh issue view <N> --repo OWNER/REPO --json number,state,url` 查询。
nonexistent、编号不匹配、非 `OPEN` 或命令错误直接抛出 `EvidenceError`。

一次采集前后继续比较 `headRefOid`，并新增对 `body` 与
`closingIssuesReferences` 的比较。任一变化都拒绝结果并要求重跑。issue 查询失败
不使用缓存、正文或默认值降级。

### 4. Offline gate 与 schema

`pr_review_gate.schema.json` 增加可选 `issue_reference` object；必填子字段为
`number`、`kind`、`source`、`verified`、`closing_issue_numbers`，`state` 为 partial
所需的可选 schema 字段。保留 `linked_issue` 顶层字段与旧 fixture 兼容。

`pr_gate.py` 增加 relation consistency checker：

- 字段缺失时沿用 legacy `linked_issue` 评估。
- 字段存在时要求 number 与 `linked_issue` 一致、`verified: true`。
- `partial` 只接受 `pr_body` + `OPEN`，且 number 不得出现在
  `closing_issue_numbers`。
- `closing` 只接受 `closingIssuesReferences`，且 number 必须出现在
  `closing_issue_numbers`。
- 任何未知 kind/source 或矛盾组合均为 `blocked`。

gate 保持离线，不执行 GitHub 查询，也不推断 issue 完成度或 closure。decision
输出回显 `issue_reference` 供审计，但不新增任何 closure/final-completion 字段或动作。

### 5. 文档与锁文件

更新 PR-gate skill 与 `AGENT_USAGE.md`，说明 partial PR 必须把预期 issue 传给
adapter。更新 `skills-lock.json` 中受影响 skill hash。队列 skill 的
`Refs #<issue>` 规则保持不变，只补充可执行命令提示。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 closing path 不变 | `normalize_issue_reference` closing 分支 | `python3 -m pytest -q tests/test_github_pr_evidence.py -k closing` |
| B-002 显式 issue 才允许 partial | CLI parser、collector | `python3 -m pytest -q tests/test_github_pr_evidence.py -k expected_issue` |
| B-003 精确、可见的 `Refs #N` | `github_issue_reference.py` strict partial matcher | `python3 -m pytest -q tests/test_github_pr_evidence.py -k partial_reference_text` |
| B-004 live OPEN 同仓 issue | issue collector/normalizer | `python3 -m pytest -q tests/test_github_pr_evidence.py -k partial_issue_state` |
| B-005 结构化 evidence + 兼容投影 | `build_evidence`、schema | `python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_specrail_schema.py` |
| B-006 partial 字段闭集与组合 | `pr_gate.py` relation checker | `python3 -m pytest -q tests/test_pr_gate.py -k partial` |
| B-007 closing 来源约束 | `pr_gate.py` relation checker | `python3 -m pytest -q tests/test_pr_gate.py -k closing_reference` |
| B-008 显式目标与 mixed closing refs | collector normalization | `python3 -m pytest -q tests/test_github_pr_evidence.py -k 'mismatch or mixed_relation'` |
| B-009 query 输入漂移拒绝 | `collect_evidence` snapshot checks | `python3 -m pytest -q tests/test_github_pr_evidence.py -k change_during_gate_query` |
| B-010 partial 不承载 closure | evidence kind/source contract、docs | `python3 -m pytest -q tests/test_pr_gate.py::test_pr_gate_allows_verified_partial_reference_without_treating_it_as_closing` + 下方 Remem #801 live read-only adapter→gate 验证 |
| B-011 legacy evidence 兼容 | optional schema field、gate fallback | `python3 -m pytest -q tests/test_pr_gate.py -k legacy` |
| B-012 幂等与显式错误 | collector error paths | `python3 -m pytest -q tests/test_github_pr_evidence.py` |

## 数据流

```text
explicit --issue N ─┐
PR body/closing refs ├─ github_pr_evidence.py ─ issue_reference + linked_issue
live gh issue view ──┘                                  │
                                                       ▼
                                          offline pr_gate.py consistency check
```

collector 只向 stdout 输出 JSON；不写 GitHub 状态。gate 只读 evidence JSON；不发
网络请求。issue completion/closure 仍由队列 completion semantics 与 closure audit
决定。

## 备选方案

- 自动接受正文任意 `#N`：拒绝；普通讨论文本和“仍有 #N 未完成”等语句会被误认。
- 将 `Refs` 改为 `Fixes`：拒绝；会错误关闭 umbrella issue。
- 只设置 `linked_issue` 而不记录 relation：拒绝；无法审计证据来源或阻止伪造。
- 把 GitHub 查询放进 `pr_gate.py`：拒绝；破坏采集/策略分离和离线可测性。

## 风险

- Security: PR body 是作者可编辑输入；通过显式 issue binding、live issue 查询与
  strict matcher 限制信任边界。
- Compatibility: 新字段为可选，legacy fixture 保持有效；adapter 新输出更严格。
- Performance: partial 路径增加一次 `gh issue view`，相对现有两次 PR query 和
  GraphQL thread query 可忽略。
- Maintenance: relation 规则同时存在于 collector/schema/gate；用共享字段闭集和
  cross-layer tests 防止再次漂移。

## 测试计划

- [x] Unit tests: strict matcher、normalization、schema 与 gate 决策矩阵。
- [x] Integration tests: fake `gh` CLI 覆盖 partial success 与 live issue failure。
- [x] Regression tests:
  `test_build_evidence_records_other_closing_issues_without_reclassifying_expected_partial`
  锁定 `Refs #671` + `Closes #806` 的 mixed relation；
  `test_pr_gate_allows_verified_partial_reference_without_treating_it_as_closing`
  断言 gate 只满足关联要求且不产生 closure/final-completion 字段或动作。
- [x] Manual verification: 在真实、已合并的 Remem PR #801 上做只读 adapter→gate
  验证。PR 的历史事实是 `Closes #806` + `Refs #671`，GH671 当前仍为 `OPEN`；PR
  已合并会使 gate 因 `state` 阻塞，但 relation 本身必须满足且不能授权关闭 GH671：

```bash
python3 checks/github_pr_evidence.py \
  --github-repo majiayu000/remem --pr 801 --issue 671 \
  --review-source independent_lane \
  --json > /tmp/specrail-gh88-remem801-evidence.json
python3 checks/pr_gate.py --repo . \
  --evidence /tmp/specrail-gh88-remem801-evidence.json \
  --mode required --json > /tmp/specrail-gh88-remem801-gate.json || test $? -eq 1
jq -e '.linked_issue == 671 and .issue_reference.kind == "partial" and
  .issue_reference.state == "OPEN" and
  (.issue_reference.closing_issue_numbers | index(671) | not) and
  (.issue_reference.closing_issue_numbers | index(806) != null)' \
  /tmp/specrail-gh88-remem801-evidence.json
jq -e '.linked_issue == 671 and .issue_reference.kind == "partial" and
  (.satisfied | index("issue_reference: verified partial GH-671") != null) and
  (has("issue_closure") | not) and (has("completion_mode") | not) and
  (.blocked_actions | index("close_issue") | not)' \
  /tmp/specrail-gh88-remem801-gate.json
gh issue view 671 --repo majiayu000/remem --json state \
  --jq 'select(.state == "OPEN") | .state'
```

## 回滚方案

回滚 collector、`github_issue_reference.py`、schema、gate、tests、skills/docs 与 GH88
spec packet 的对应 commit。
所有新增行为均为只读 evidence 采集/评估，无远端数据迁移；回滚后 partial PR 恢复
为旧的 fail-closed 行为。
