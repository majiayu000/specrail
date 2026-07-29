# Task Plan

## Linked Issue

GH-168

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP168-T1` 新增 `checks/spec_revision_evidence.py`，实现 `spec_revision_route_eligible(config, issue, classification)`：只接受 linked issue 自身非空 spec packet 子集、registry spec 命中、零 matched code paths，并拒绝 foreign packet/mixed/self-reported paths。Covers: B-001 B-004 B-006。Owner: implementation lane。Depends on: none。Done when: GH168 linked issue 下 GH169 packet 与任一非白名单 path 稳定不具资格，helper 与 `sensitive_enforcement.py` 均 ≤800 行。Verify: `/usr/bin/python3 -m pytest -q tests/test_sensitive_enforcement.py -k spec_revision`。
- [ ] `SP168-T2` 扩展 `checks/github_approved_spec_evidence.py` 与 `checks/github_pr_evidence.py`：采集 linked issue `spec_approved` terminal label、maintainer exact-head `APPROVED` review、review URL/time/actor/commit，并计算 gated-head artifact digest；采集前后 head/relation/file/timeline 漂移 fail closed。Covers: B-002 B-005 B-007 B-008。Owner: implementation lane。Depends on: T1 artifact path contract。Done when: live collector 输出完整 `spec_approval`；`spec_review`、old-head review、post-approval push、非 maintainer 与分页漂移负例全绿。Verify: `/usr/bin/python3 -m pytest -q tests/test_github_pr_evidence.py tests/test_github_pr_evidence_approval.py`。
- [ ] `SP168-T3` 扩展 `schemas/pr_review_gate.schema.json` 与 schema tests：按 `sensitive_route` 要求 `approved_spec` 或 closed `spec_approval` 恰好一个，拒绝 mixed/partial/route mismatch/unknown fields。Covers: B-003 B-009。Owner: implementation lane。Depends on: T2 field contract。Done when: collector 正例 schema-valid，所有错配负例在 gate 前被拒绝。Verify: `/usr/bin/python3 -m pytest -q tests/test_specrail_schema.py -k 'spec_revision or approved_spec'`。
- [ ] `SP168-T4` 在 `checks/spec_revision_evidence.py` 实现 exact-head/digest validator，并让 `checks/sensitive_enforcement.py` 按 T1 资格互斥分流；approved_spec route 保持现有 byte equality。Covers: B-003 B-004 B-005 B-007。Owner: implementation lane。Depends on: T1–T3。Done when: `commit_oid != gated head`、digest mismatch、`spec_review` 或 evidence 混用均 blocked，现有 approved_spec tests 不改断言全绿。Verify: `/usr/bin/python3 -m pytest -q tests/test_sensitive_enforcement.py tests/test_pr_gate.py`。
- [ ] `SP168-T5` 新增 `checks/runtime_sensitive_routes.py` 并接入 `checks/runtime_ledger_gate.py`，扩展 `schemas/runtime_checkpoint.schema.json`：approved_spec item 保持旧要求，spec_revision item 改验 exact-head `spec_approval_evidence`；route/evidence 错配 fail closed。Covers: B-009 B-010 B-011。Owner: implementation lane。Depends on: T3–T4。Done when: spec_revision checkpoint 不因缺 approved_spec 误拒绝，旧 route、head/digest/mixed negatives 全绿，ledger/schema 文件均 ≤800 行。Verify: `/usr/bin/python3 -m pytest -q tests/test_runtime_ledger_gate.py tests/test_specrail_schema.py`。
- [ ] `SP168-T6` 更新 `checks/pr_gate.py`：从已验证对象输出 route/linked issue/artifact paths/actor/time/source/URL/commit/digest audit，缺失或 mismatch blocked；其它 CI/review/thread/merge/auth gates 原样执行。Covers: B-011 B-012。Owner: implementation lane。Depends on: T4–T5。Done when: exact audit 正例通过，删除任一其它 gate 或 audit field 均 blocked。Verify: `/usr/bin/python3 -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py`。
- [ ] `SP168-T7` 新增 collector→schema→PR gate→runtime ledger 端到端 fixture/test，逐项变更 lifecycle、linked issue、review commit、artifact bytes 与 mixed path 验证 fail closed；不得只用手写 `spec_approval` fixture 代替 live adapter。Covers: B-001..B-012。Owner: verification lane。Depends on: T1–T6。Done when: 全链正例绿、每个信任边界至少一条负例，既有 suite 不弱化。Verify: `/usr/bin/python3 -m pytest -q`。
- [ ] `SP168-T8` 更新 `skills/specrail-pr-gate/SKILL.md` 的 route、exact-head approval、互斥/反滥用与 runtime handoff 说明，并运行 workflow/spec-depth/size checks。Covers: B-003 B-007 B-010 B-012。Owner: coordinator。Depends on: T1–T7。Done when: 文档字段与实现一致，`sensitive_enforcement.py`、`runtime_ledger_gate.py`、`runtime_checkpoint.schema.json` 均不超过 800 行，所有 deterministic gates 绿。Verify: `python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH168 --gate && test $(wc -l < checks/sensitive_enforcement.py) -le 800 && test $(wc -l < checks/runtime_ledger_gate.py) -le 800 && test $(wc -l < schemas/runtime_checkpoint.schema.json) -le 800`。

## 并行拆分

T1 先固定 route/path contract；T2/T3 可分别处理 collector 与 schema，但不得同时修改同一文件；T4 消费两者。T5 与 T6 在 T4 字段稳定后可由 disjoint runtime/pr-gate lanes 并行；T7/T8 最后串行收口。所有 reviewer lanes 只读 tracked 文件。

## Verification

- `/usr/bin/python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH168 --gate`
- `git diff --check`

## Handoff Notes

- 本 spec PR 使用当前逐 PR 人工授权，不能用尚未实现的 spec_revision route 自我放行。
- `spec_review` 不是批准；只有 linked issue `spec_approved` + exact-head maintainer `APPROVED` review 两者同时成立。
- implementation PR 使用 `Closes #168`；规格与实现完全合并并通过真实 gate 后才关闭 issue。
