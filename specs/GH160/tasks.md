# Task Plan

## Linked Issue

GH-160

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP160-T1` Extend `checks/session_telemetry.py` with strict `token_count` observation parsing and latest/max/p50 aggregation; add focused cases to `tests/test_session_telemetry.py`. Covers: B-001 B-002 B-003 B-009 B-012. Owner: agent. Dependencies: none. Done when: valid runtime-shaped events produce numeric summaries, invalid events produce no trusted zero, and explicit-offset/read-only guarantees remain green. Verify: `python3 -m pytest -q tests/test_session_telemetry.py`.
- [ ] `SP160-T2` Add `checks/runtime_context_budget.py` and connect it at the existing `context_budget` validation point in `checks/runtime_ledger_gate.py`; add `tests/test_runtime_context_budget.py`. Covers: B-004 B-005 B-006 B-007 B-008 B-011. Owner: agent. Dependencies: T1 field contract. Done when: ratios are recomputed, soft/hard/critical convergence rules block invalid continuation, legacy checkpoints retain prior outcomes, and `runtime_ledger_gate.py` remains at or below 800 lines. Verify: `python3 -m pytest -q tests/test_runtime_context_budget.py tests/test_runtime_ledger_gate.py`.
- [ ] `SP160-T3` Extend `schemas/runtime_checkpoint.schema.json` and both tranche checkpoint templates with the optional context observation and convergence-action structure. Covers: B-004 B-005 B-006 B-007 B-008. Owner: agent. Dependencies: T2 field contract. Done when: complete evidence is schema-valid, malformed typed evidence is rejected, and old fixtures stay valid. Verify: `python3 checks/check_workflow.py --repo .`.
- [ ] `SP160-T4` Tighten the Context Budget protocol in `skills/specrail-implement-queue/SKILL.md`, keeping the file at or below 800 lines, then regenerate `skills-lock.json`. Covers: B-005 B-008 B-010 B-011. Owner: agent. Dependencies: T1–T3 field names. Done when: the executable collect/check/converge ordering is explicit, a goal grants no continuation exception, the lock is current, and the file-size check passes. Verify: `wc -l skills/specrail-implement-queue/SKILL.md | awk '$1 <= 800 {ok=1} END {exit !ok}' && python3 checks/check_workflow.py --repo .`.
- [ ] `SP160-T5` Run targeted, full, schema, spec-depth, and implementation-vs-spec checks; record the production KPI as pending unless backed by a real post-rollout drain sample. Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012. Owner: coordinator. Dependencies: T1–T4. Done when: deterministic checks are green and every invariant maps to code/test evidence without claiming an unavailable production result. Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . && python3 tools/spec_depth_audit.py --spec-dir specs/GH160 --gate`.

## Parallelization

The implementation is serial in this single worktree. T1 establishes the
telemetry fields; T2 consumes them; T3 documents the stable contract; T4
updates workflow prose and the lock after names are final. Reviewer lanes are
read-only and run only after each PR head is pushed. No two cargo or test
commands run concurrently in this worktree.

## Verification

- `python3 -m pytest -q tests/test_session_telemetry.py tests/test_runtime_context_budget.py tests/test_runtime_ledger_gate.py`
- `python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo .`
- `python3 tools/spec_depth_audit.py --spec-dir specs/GH160 --gate`
- `git diff --check`

## Handoff Notes

- `pr_tier: heavy`: merge the spec PR before creating the implementation PR.
- The planner lane `/root/planner_gh160` produced zero output after its bounded
  wait and stop request; this failure is recorded but does not substitute for
  the mandatory independent PR reviewer lanes.
- The issue's `<130K` p50 target is an operational post-rollout measurement.
  Local fixtures prove collection and enforcement, not production improvement.
