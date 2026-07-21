# Task Plan

## Linked Issue

GH-168

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP168-T1` `checks/sensitive_enforcement.py` 新增 `spec_revision_route_eligible(config, repo, classification)`：仅读可信 classification（`matched_paths` 空 + `changed_paths` 每项均为 `specs/GH<linked_issue>/{product,tech,tasks}.md` 且命中 `enforcement.sensitive_registry.specs` + `matched_specs` 非空），任一不满足返回 False。配套单元用例（正向资格、夹带代码路径、夹带非本 issue markdown、自报路径不作数）。Covers: B-001 B-004 B-006. Owner: agent. Done when: 资格函数覆盖全部拒绝分支且用例全绿. Verify: `python3 -m pytest -q tests/test_sensitive_enforcement.py -k spec_revision`
- [ ] `SP168-T2` `checks/sensitive_enforcement.py` 新增 `validate_spec_revision_evidence(evidence, repository, issue)`：要求 `spec_approval` 对象含 maintainer_actor / timezone-aware approved_at / state_source=label / state_trusted=true / lifecycle_state ∈ {spec_review, spec_approved}，缺失或非法 fail-closed 抛 `SpecRailError`；拒绝 approved_spec 与 spec_approval 混用。配套单元用例（缺字段、agent 自报、时间戳非 aware、混用）。Covers: B-002 B-003 B-005. Owner: agent. Done when: 证据校验覆盖全部拒绝分支且用例全绿. Verify: `python3 -m pytest -q tests/test_sensitive_enforcement.py -k spec_revision`
- [ ] `SP168-T3` `checks/sensitive_enforcement.py` `evaluate_sensitive_evidence` 分流接线：`requires_approval` 且 T1 资格为真时调 T2、satisfied 追加 spec-revision route 标记；资格为假时保持现状调 `validate_approved_spec_evidence`（含 `gated_head_sha`）逐字节不变。两条 route 互斥穷尽。Covers: B-003 B-007 B-008 B-009. Owner: agent. Done when: 分流用例全绿且既有 sensitive_enforcement 用例零改动全绿. Verify: `python3 -m pytest -q tests/test_sensitive_enforcement.py tests/test_pr_gate.py`
- [ ] `SP168-T4` `checks/pr_gate.py` 敏感面消费点透传 route 结论：结果对象新增 `sensitive_route` 与 spec-revision route 审计记录（artifact 路径集 + maintainer actor/时间戳/来源），审计缺失即 blocked；未触发敏感面时字段缺省、输出逐字节不变。Covers: B-008 B-010 B-007. Owner: agent. Done when: pr_gate route 用例全绿且既有 `tests/test_pr_gate.py` 零改动全绿. Verify: `python3 -m pytest -q tests/test_pr_gate.py tests/test_pr_gate_terminal.py`
- [ ] `SP168-T5` 端到端回归：构造 spec-only enforcement-sensitive PR fixture（带 maintainer spec_approval）跑 gate CLI 得非 approved_spec-blocked 且 `sensitive_route=spec_revision`；同一 fixture 夹带 gate 代码、抹掉 spec_approval、抹掉 CI/threads/reviewer/merge_state 证据，逐个确认回落 approved_spec 或 blocked 及错误信息可定位。Covers: B-001 B-004 B-005 B-008 B-010. Owner: agent. Done when: 演练脚本化为测试或记录于 PR 描述附命令输出. Verify: `python3 checks/pr_gate.py --repo . --evidence tests/fixtures/gh168-spec-revision.json --json`
- [ ] `SP168-T6` `skills/specrail-pr-gate/SKILL.md` 补充 spec-revision route 的证据要求、与 approved_spec 的互斥边界、反滥用约束说明；文档与 gate 语义对齐。Covers: B-003 B-004. Owner: agent. Done when: SKILL.md 含 spec-revision route 说明且 workflow 校验通过. Verify: `grep -q spec_revision skills/specrail-pr-gate/SKILL.md && python3 checks/check_workflow.py --repo .`

## 并行拆分

T1 与 T2 同改 `checks/sensitive_enforcement.py`，串行（T1 先落资格函数，T2 落证据校验）；T3 依赖 T1/T2；T4 只改 `checks/pr_gate.py`，依赖 T3 确定的 route 输出契约；T5 依赖 T3/T4；T6 只改 `skills/specrail-pr-gate/SKILL.md`，依赖 T1-T4 定稿的字段名。

## Verification

- `python3 -m pytest -q tests/test_sensitive_enforcement.py tests/test_pr_gate.py tests/test_pr_gate_terminal.py`
- `python3 checks/check_workflow.py --repo .`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH168 --gate`

## Handoff Notes

- 本 spec/实现 PR 自身即 enforcement-sensitive 规格变更（正是本 issue 的死锁场景）：合并前逐 PR maintainer 人工授权，不得引用尚未存在的 spec-revision route 给自己放行。
- spec-revision route 的 route 选择必须由可信路径快照机械推导（B-001/B-004/B-006），标签仅作生命周期状态的 maintainer 信任来源，勿把 route 选择做成自声明字段。
- B-007/B-008 零回归是硬约束：以既有 pr_gate / sensitive_enforcement 测试零改动全绿为准绳。
