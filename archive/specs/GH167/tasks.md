# Task Plan

## Linked Issue

GH-167

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP167-T1` 固化 manifest v2 与轮次派生：在 `checks/review_result_semantics.py` 接受 v1 单 artifact 兼容路径和 `version: 2`/`bounded_diff_v1` 路径；从实际 artifacts 验证 round=`1..N`、artifact/head 唯一、round>=2 scoped、base=上一轮 head，并生成 trusted `round_audit`。v1 多 artifact、v2 缺字段或声明/实际不一致均 block。Covers: B-001 B-004 B-011 B-012. Owner: agent. Depends on: none. Done when: 连续、重复、缺口、回退、v1/v2 migration 用例全部通过。Verify: `/usr/bin/python3 -m pytest -q tests/test_review_result_semantics.py tests/test_review_json_gate.py`.

- [ ] `SP167-T2` 收敛 bounded finding schema 与 shared semantics：更新 `schemas/review_result.schema.json`，新增 `round_policy_version: 1` 条件形态；bounded `prior_findings[]` 使用 `{finding_id, source_artifact_id, status, evidence_pointer:{kind,value}}` 闭集。shared semantics 校验 typed pointer、来源 artifact、复合键唯一、完整 carry，并计算 escalation 的“历史 unresolved + 当前 critical/important/actionable”精确并集。旧 v1 单轮空 carry 不变。Covers: B-006 B-007 B-008 B-009 B-010. Owner: agent. Depends on: SP167-T1. Done when: 正文回放、自由散文、未知来源、重复键、漏/多移交负例与合法 compact 正例全绿。Verify: `/usr/bin/python3 -m pytest -q tests/test_review_result_semantics.py tests/test_specrail_schema.py`.

- [ ] `SP167-T3` 实现可信 scoped diff：`checks/review_json_gate.py` 对 bounded round>=2 用参数数组运行固定 `git diff --no-ext-diff --binary base..head --`，要求 `--diff` 原始字节、实际 Git 输出、artifact `diff_sha256` 三者一致；`resumed` 与 `diff_only` 均强制 base/hash。把跨 artifact 算法留在 shared semantics，修改后两个 Python 文件各 `<800` 行。Covers: B-004 B-005 B-014. Owner: agent. Depends on: SP167-T1 SP167-T2. Done when: 正确 range（含空/binary）通过，全 PR diff、错 hash/base、缺 Git object 均 block，文件行数门禁通过。Verify: `/usr/bin/python3 -m pytest -q tests/test_review_json_gate.py && test "$(wc -l < checks/review_json_gate.py)" -lt 800 && test "$(wc -l < checks/review_result_semantics.py)" -lt 800`.

- [ ] `SP167-T4` 建立外部一次性 cap 授权：`checks/github_review_evidence.py` 加载闭集授权文件与 maintainer role map，`checks/github_pr_evidence.py` 暴露 `--round-cap-authorization`/`--maintainer-role-map` 并输出规范化 `round_cap_authorizations[]`；`schemas/pr_review_gate.schema.json` 增加该顶层闭集。每条授权精确绑定 id、PR、prior/target head、round、`continue_once`、actor/source/time，auto 合并授权不得自动填充。Covers: B-002 B-003 B-013. Owner: agent. Depends on: SP167-T1. Done when: 缺/错 role map、伪造 actor、错 PR/head/round、未知字段被拒，规范授权通过。Verify: `/usr/bin/python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_github_pr_evidence_cli.py tests/test_specrail_schema.py`.

- [ ] `SP167-T5` 接入终审合同：`schemas/pr_review_gate.schema.json` 为 `review_evidence` 增加闭集 `round_audit`；`checks/pr_review_contract.py` 从安全路径重载 manifest v2 并比对派生 audit，为每个 over-cap round 匹配唯一 exact-bound 授权，拒绝 id 跨 round/head/PR 复用及 artifact 内 `human_full_review_request`/actor/source 替代。Covers: B-002 B-003 B-011 B-013. Owner: agent. Depends on: SP167-T1 SP167-T4. Done when: trusted reload 篡改、授权复用和缺授权用例 block，合法第 4 轮只通过一次。Verify: `/usr/bin/python3 -m pytest -q tests/test_pr_gate_terminal.py tests/test_github_pr_evidence.py tests/test_runtime_ledger_review.py`.

- [ ] `SP167-T6` 同步 reviewer/queue/threads 权威合同与编排：更新 `review/agent_first_review.md`、`skills/specrail-review-pr/SKILL.md`、`skills/specrail-implement-queue/SKILL.md`、`skills/implx/SKILL.md`、`integrations/threads.md`，写明 v2 输出、第 2 轮起 exact scoped diff、compact carry、cap=3 后停止、人工逐轮 `continue_once` 与完整 finding 移交；明确 auto 模式和 `human_full_review_request` 均不能提供 cap 授权。新增 `tests/test_review_contract_docs.py` 检查稳定 marker 并拒绝旧“full=2 + human extra full pass”语义。Covers: B-002 B-003 B-004 B-005 B-006 B-010 B-015. Owner: agent. Depends on: SP167-T1..SP167-T5. Done when: review、queue、implx、threads 合同字段/停止语义一致，任一文档回漂会使测试失败。Verify: `/usr/bin/python3 -m pytest -q tests/test_review_contract_docs.py && python3 checks/check_workflow.py --repo . --all-specs`.

- [ ] `SP167-T7` 端到端回归与 PR 证据演练：构造 v1 单轮兼容、v2 三轮、无授权第 4 轮、exact 授权第 4 轮、复用授权第 5 轮、full PR diff、compact carry 漏项/正文回放、当前 actionable finding 漏移交及权威合同回漂场景；逐层运行 review gate、manifest loader、GitHub adapter、PR gate 和文档一致性测试。Covers: B-001..B-015. Owner: agent. Depends on: SP167-T1..SP167-T6. Done when: 所有正反场景有自动化测试，错误可定位且全量验证通过。Verify: `/usr/bin/python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && git diff --check`.

## Parallelization

T1 先确定 manifest v2/round audit。T2 与 T4 在 T1 后可并行，文件所有权分别为 result schema/shared semantics 与 GitHub adapter/PR schema；因 T4、T5 都修改 `schemas/pr_review_gate.schema.json`，必须由同一 owner 串行或在 T4 后交接。T3 依赖 T1/T2；T5 依赖 T1/T4；T6 在字段稳定后执行；T7 最后串行。任何并行 lane 不得共享可写文件。

## Verification

- `/usr/bin/python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `git diff --check`
- `test "$(wc -l < checks/review_json_gate.py)" -lt 800`
- `test "$(wc -l < checks/review_result_semantics.py)" -lt 800`

## Handoff Notes

- 本实现属于审查/授权合同变更，`pr_tier: heavy`；实现 PR 必须保留独立终审、CI、reviewThreads、pr_gate 与本次用户明确 heavy merge 授权。
- cap 授权不是 merge authorization。auto 模式只能授权本次合并动作，不能自动创造第 4+ 轮 `continue_once` 决定。
- `round_audit` 只能由仓库安全路径加载的 manifest/artifacts 派生；adapter 与调用者不得手工覆盖。
- Git diff 必须用固定参数数组生成并按原始字节比较，禁止 shell 字符串与无法验证来源的 patch fallback。
- v1 单 artifact 是唯一兼容路径；不要为 v1 多 artifact 添加 warning-only 降级。
