# Tech Spec

## Linked Issue

GH-34

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Change |
| --- | --- | --- | --- |
| Runtime gate | `checks/runtime_ledger_gate.py` | No checkpoint evaluator exists | Add offline checkpoint validation with merge-ready evidence checks |
| Schema | `schemas/runtime_checkpoint.schema.json` | No runtime checkpoint contract exists | Add JSON schema for checkpoint artifacts |
| Templates | `templates/tranche_checkpoint.md`, `templates/zh-CN/tranche_checkpoint.md` | No tranche handoff template exists | Add English and zh-CN checkpoint templates |
| Queue docs | `AGENTS.md`, `AGENT_USAGE.md`, `README.md`, `integrations/threads.md` | Long queue guidance is advisory only | Document bounded tranches, output firewall, checkpoints, and canonical truth |
| Skills | `skills/implx/SKILL.md`, `skills/specrail-implement-queue/SKILL.md`, `skills/specrail-workflow/SKILL.md` | Queue skills lack long-run handoff guardrails | Add context-budget, output-firewall, checkpoint, and Goal-use guidance |
| Skill lock | `skills-lock.json` | Pins existing skill hashes | Refresh changed skill hashes |

## 设计方案

Add `checks/runtime_ledger_gate.py` as an offline deterministic evaluator. The
gate reads a checkpoint JSON file, validates required top-level fields, validates
context-budget ordering, enforces `output_firewall.raw_log_policy=file_only`,
and blocks invalid merge-ready items.

The evaluator intentionally duplicates the high-value schema constraints needed
for CLI decisions instead of relying on schema documentation alone. It must
block empty top-level identifiers and invalid status values because the CLI gate
is the mechanism agents run before handoff or resume.

The checkpoint remains optional and local. It does not write GitHub state and
does not replace issue labels, PR evidence, review threads, merge state, or
SpecRail spec packets.

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 bounded tranche fields are required | `evaluate_checkpoint` top-level checks | `test_runtime_ledger_gate_blocks_invalid_top_level_contract` |
| P2 raw logs are file-only | `output_firewall.raw_log_policy` check | `test_runtime_ledger_gate_blocks_bounded_stdout_policy` |
| P3 merge-ready needs authorization and evidence | merge-ready branch in evaluator | `test_runtime_ledger_gate_blocks_merge_ready_without_authorization`, review-thread and PR-gate tests |
| P4 stale PR gate head SHA blocks | `pr_gate.head_sha` comparison | `test_runtime_ledger_gate_blocks_stale_pr_gate_head_sha` |
| P5 CLI returns JSON and non-zero on blocked | CLI wrapper | CLI JSON contract test plus invalid-checkpoint manual reproduction |

## 数据流

Input is a local JSON checkpoint, usually `.specrail/runtime/current.json`.
Output is a JSON or text decision with `decision`, `errors`, `warnings`, and
`satisfied`. The gate reads no network state and writes no files. GitHub and
SpecRail artifacts remain the source of truth for live queue state.

## 备选方案

- Document checkpoints without a gate: rejected because long-run handoffs need
  deterministic validation.
- Make the checkpoint canonical workflow state: rejected because GitHub and
  SpecRail artifacts already own durable truth.
- Enforce raw log policy only in prose: rejected because output-firewall
  violations need a checkable contract.

## 风险

- Security: No secret-handling path is added; the output-firewall guidance
  reduces parent-context exposure of raw logs.
- Compatibility: The checkpoint is optional and local, so existing workflows
  keep working.
- Performance: Gate input is one local JSON file.
- Maintenance: Evaluator and schema must stay aligned for required fields and
  status values.

## 测试计划

- [ ] Unit tests: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`
- [ ] Full tests: `python3 -m pytest -q`
- [ ] Workflow validation: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Whitespace check: `git diff --check`
- [ ] Manual regression: invalid checkpoint with blank top-level fields returns
      `blocked`.

## 回滚方案

Remove `checks/runtime_ledger_gate.py`, runtime checkpoint schema/templates,
docs/skill guidance, refreshed skill hashes, and `specs/GH34`. Existing
SpecRail issue/spec/PR workflows continue to work without runtime checkpoints.
