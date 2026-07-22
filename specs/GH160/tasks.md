# Task Plan

## 关联 Issue

GH-160

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP160-T1` 扩展 `checks/session_telemetry.py`：严格解析 `token_count`，输出 latest/max/lower-median p50、有效/无效计数、runtime window 与 conflict；在 `tests/test_session_telemetry.py` 添加 focused cases。Covers: B-001 B-002 B-003 B-009 B-012。Owner: implementation lane。Depends on: none。Done when: 合法 runtime event 产生纯数值 summary；invalid/conflicting event 不产生可信 ratio；offset/read-only 行为全绿。Verify: `python3 -m pytest -q tests/test_session_telemetry.py`。
- [ ] `SP160-T2` 新增 `checks/runtime_context_budget.py` 并接入 `checks/runtime_ledger_gate.py` 的既有 validation point；新增 `tests/test_runtime_context_budget.py`。Covers: B-004 B-005 B-006 B-007 B-008 B-011。Owner: implementation lane。Depends on: T1 field contract。Done when: runtime window 必须等于 `window_tokens`，window conflict/ratio mismatch/soft-stop 非 handoff 均 blocked，legacy checkpoint 保持原判定，主 ledger 文件 ≤800 行。Verify: `python3 -m pytest -q tests/test_runtime_context_budget.py tests/test_runtime_ledger_gate.py`。
- [ ] `SP160-T3` 扩展 `schemas/runtime_checkpoint.schema.json` 与两份 tranche template，加入完整 optional observation/convergence shape。Covers: B-003 B-004 B-005 B-006 B-007 B-008。Owner: implementation lane。Depends on: T2 field contract。Done when: 完整证据 schema-valid，partial/typed-invalid evidence 被拒绝，旧 fixtures 保持通过。Verify: `python3 checks/check_workflow.py --repo .`。
- [ ] `SP160-T4` 新增 `skills/specrail-implement-queue/references/context-budget.md`，把详细 Context Budget / Bounded Tranche 协议从主 skill 抽出；主 `SKILL.md` 保留触发与路由并重建 `skills-lock.json`。Covers: B-005 B-008 B-010 B-011。Owner: implementation lane。Depends on: T1–T3 final fields。Done when: collect→checkpoint→gate→handoff 顺序明确，goal 不提供继续例外，reference 自包含，主 skill ≤800 行且 lock current。Verify: `wc -l skills/specrail-implement-queue/SKILL.md | awk '$1 <= 800 {ok=1} END {exit !ok}' && python3 checks/check_workflow.py --repo .`。
- [ ] `SP160-T5` 运行 targeted/full/schema/spec-depth/implementation-vs-spec checks，并让 implementation PR 使用 `Refs #160`。Covers: B-001..B-011。Owner: coordinator。Depends on: T1–T4。Done when: 所有确定性 gate 绿，PR 不含 closing keyword，且未把缺失的生产 KPI 写成通过。Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH160 --gate`。
- [ ] `SP160-T6` 在 implementation merge 后运行命名 bounded drain，并把 sample window、context p50、`<130K` 比较、token/PR 与版本证据附到 GH-160。Covers: B-012。Owner: coordinator/operator。Depends on: merged T1–T5。Done when: 真实证据可复核后才关闭 issue；否则保持 `rollout evidence pending`。Verify: issue attachment/link + closure audit。

## 并行拆分

implementation 在单一 worktree 串行：T1 定义 telemetry fields，T2 消费，T3 固化 schema，
T4 在字段稳定后抽取 workflow reference，T5 汇总验证。Reviewer lanes 只读且只在稳定 head
后运行。T6 是 merge 后 operational task，不与 implementation 文件写入并行。

## 验证

- `python3 -m pytest -q tests/test_session_telemetry.py tests/test_runtime_context_budget.py tests/test_runtime_ledger_gate.py`
- `python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH160 --gate`
- `git diff --check`

## Handoff Notes

- `pr_tier: heavy`：先合并 spec PR，再创建独立 implementation PR。
- Spec PR 与 implementation PR 均使用 `Refs #160`；T6 证据完成前 GH-160 保持 open。
- 当前独立 reviewer 发现的六项 blocking spec drift 已在本修订中逐项闭环；push 后由
  reviewer successor 复核，不由 implementation lane 自行批准。
