# Task Plan

## Linked Issue

GH-97

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

<!-- specrail-planned-changes
{"version":1,"issue":97,"complete":true,"paths":["workflow.yaml","checks/check_workflow.py","checks/github_approved_spec_evidence.py","checks/github_pr_evidence.py","checks/github_pr_snapshot.py","checks/pr_gate.py","checks/route_gate.py","checks/runtime_gate_rules.py","checks/runtime_ledger_gate.py","checks/sensitive_enforcement.py","checks/review_json_gate.py","checks/review_result_semantics.py","checks/closure_audit.py","schemas/pr_review_gate.schema.json","schemas/runtime_checkpoint.schema.json","schemas/review_result.schema.json","schemas/closure_audit_result.schema.json","tests/test_check_workflow.py","tests/test_github_pr_evidence.py","tests/test_pr_gate.py","tests/test_route_gate.py","tests/test_runtime_ledger_gate.py","tests/test_specrail_schema.py","tests/test_review_json_gate.py","tests/test_closure_audit.py"],"spec_refs":["specs/GH97/product.md","specs/GH97/tech.md","specs/GH97/tasks.md"]}
-->

## 实现任务

- [ ] `SP97-T1` Owner: agent; Dependencies: approved spec; PR: partial implementation A (`Refs #97`); Files: `workflow.yaml`, configured-path helpers, approved-spec adapter/evidence, `checks/route_gate.py`, `checks/github_pr_evidence.py`, `checks/pr_gate.py`, runtime gate/schema integration and focused tests; Done when: consumer registry 命中由受信任、规范化的 planned/current-head paths 自行计算；approved spec 由 maintainer-controlled label + merged base head + repo/issue/path/hash/actor/timestamp 证据生成并重新验证；`enforcement_sensitive` 缺失/冲突、forged/body-hint approval、批准后 spec 改变、true 无 approved spec、unsafe path 全部 fail closed，且非敏感 PR 保持兼容；Verify: focused workflow/route/evidence/PR/runtime/schema pytest、pack check。
- [ ] `SP97-T2` Owner: agent; Dependencies: `SP97-T1`; PR: partial implementation B (`Refs #97`); Files: `schemas/review_result.schema.json`, shared review semantic validator, trusted manifest/lane-roster integration, `checks/review_json_gate.py`, `schemas/pr_review_gate.schema.json`, `checks/github_pr_evidence.py`, `checks/pr_gate.py`, runtime gate/schema integration and focused tests/fixtures; Done when: adapter 发现并验证全部 manifest artifacts，terminal exact-head artifact、每 lane/head 唯一 terminal、concurrent clean+blocking、重复 terminal、stale/superseded、zero blocking/actionable findings、prior finding carry-forward、resolver/re-review 与受限 self-review 全部 fail closed；pre-merge 只使用 canonical `gate_query_completed_at` 并验证 review→gate 同-head 时序，不要求 future dispatch；Verify: focused review/evidence/PR/runtime/schema pytest、pack check。
- [ ] `SP97-T3` Owner: agent; Dependencies: `SP97-T2`; PR: final implementation C (`Closes #97`); Files: `schemas/closure_audit_result.schema.json`, `checks/closure_audit.py`, asset registration、相关 tests/fixtures、consumer-facing docs/skills/lock when CLI contract requires; Done when: post-dispatch same-head ordering 被验证，external merge 缺链返回稳定 schema-valid violation/`required_follow_up`，只声明 advisory detection 且不调用 GitHub 写 API；Verify: closure audit pytest/CLI smoke、full pytest、all-spec workflow check、skill lock verification。
- [ ] `SP97-T4` Owner: verification owner; Dependencies: each implementation PR head; Files: full repository read/verification only; Done when: 每个 serial slice 的 focused checks 通过，final slice 所有 deterministic checks 通过；Verify: `python3 checks/check_workflow.py --repo . --all-specs`, `python3 -m pytest`, `git diff --check`。
- [ ] `SP97-T5` Owner: independent reviewer lane; Dependencies: each implementation head; Files: read only; Done when: reviewer 对 spec coverage、fail-closed behavior、path trust、compatibility 和 tests 给出 current-head verdict，blocking findings 已修复；Verify: review artifact + PR gate + GraphQL reviewThreads + CI on each final head。

## 并行拆分

- 三个 implementation PR 都会修改 shared gate/schema/fixtures，严格按 `SP97-T1 → T2 → T3`
  串行；禁止平行 writable lane。
- 每个下游 worktree 只能在上游 PR merge、fresh `origin/main` 和 overlapping-file audit 后创建。
- 当前 spec tranche 与后续每个 implementation tranche 都只使用一个 writable worker；reviewer
  lane 始终只读，full verification 由 coordinator 串行执行。

## 验证

- `python3 -m pytest tests/test_review_json_gate.py tests/test_github_pr_evidence.py tests/test_pr_gate.py tests/test_route_gate.py tests/test_runtime_ledger_gate.py tests/test_closure_audit.py`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH97`
- `python3 checks/check_workflow.py --repo .`
- `python3 -m pytest`
- `git diff --check`

## Handoff Notes

本 issue 是 `majiayu000/remem#813` 的 `SP813-T3` 上游依赖。SpecRail 只拥有 evidence、gate、
closure violation 和 `required_follow_up` payload contract；remem 的 controller 负责把 payload
持久化为 GitHub issue。禁止发布 release、直接修改 remem synced copies 或把本地 gate 描述为
server-side protection。最终 PR 使用 `Closes #97`；合并后 remem 再固定上游 commit 并同步。
