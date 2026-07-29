# Tech Spec

## Linked Issue

GH-60

## Product Spec

`specs/GH60/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| implx | `skills/implx/SKILL.md` | Plain implx = full queue drain, no budget | Mode semantics change |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Owns context-budget and runtime-checkpoint behavior (soft language) | Hard-stop contract text |
| checkpoint schema | `schemas/runtime_checkpoint.schema.json` | No budget fields | Structural contract |
| runtime gate | `checks/runtime_ledger_gate.py` | Validates checkpoint merge-readiness | Enforcement of budget evidence |
| checkpoint template | `templates/tranche_checkpoint.md` | Human-readable tranche handoff | Budget/stop-reason fields |

## Proposed Design

1. Budget model in the checkpoint: `budget` object with `basis`
   (`compaction` | `item_cap` | `both`), `compaction_budget` (default 1,
   i.e. stop before the 2nd compaction), `item_cap`, plus observed
   `compaction_count`, `stop_reason`
   (`budget_exhausted` | `queue_empty` | `user_interrupt` | `blocked`), and
   optional `budget_override` (quoted user text + scope).
2. `checks/runtime_ledger_gate.py`: a checkpoint whose
   `compaction_count > compaction_budget` without a recorded override, or a
   drain checkpoint with no declared budget, is a blocking violation. A
   `stop_reason: budget_exhausted` checkpoint with a valid `resume_prompt` is
   a passing terminal.
3. Skill text: `skills/implx/SKILL.md` redefines `full_queue_drain` as
   repeated bounded tranches; `skills/specrail-implement-queue/SKILL.md` gets
   the operational protocol (declare budget at tranche start; monitor
   compaction events; stop-and-checkpoint procedure; reviewer lanes stay
   bounded <2M tokens as the reference model).
4. `templates/tranche_checkpoint.md` gains budget/stop-reason lines so human
   handoffs mirror the schema.
5. Fixtures: compliant exhaustion checkpoint (pass), over-budget continuation
   (fail), missing budget declaration on a drain checkpoint (fail),
   overridden budget with recorded scope (pass).

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | budget declaration fields + gate | missing-budget fixture fails |
| P2 | stop procedure in skill text | doc review + checkpoint fixture |
| P3 | `stop_reason` handling in gate | exhaustion fixture passes |
| P4 | observed compaction fields | over-budget fixture fails |
| P5 | implx mode redefinition | doc review + check_workflow |

## Data Flow

Session start: orchestrator declares budget in the working checkpoint.
During drain: compaction events increment the observed counter. On budget
hit: write final checkpoint with stop_reason + resume_prompt. Next session
resumes from the checkpoint file. Gates read checkpoint JSON locally.

## Alternatives Considered

- Token-count budgets instead of compaction counts: rejected as primary basis
  — token counters are runtime-specific and inflated by caching; compaction
  events are the observable degradation signal. Item caps cover runtimes
  without compaction visibility.
- Letting the model self-assess "context health": rejected — the audit shows
  self-assessment fails exactly when context is degraded.
- Removing `full_queue_drain` entirely: rejected — the mode is useful; the
  fix is bounding its execution, not deleting it.

## Risks

- Security: none.
- Compatibility: old checkpoints lack budget fields; gate applies the new
  requirement only to checkpoints declaring the new contract version.
- Performance: none (fewer runaway sessions, if anything).
- Maintenance: compaction observability differs across runtimes; the
  `basis` field keeps the contract honest about what was measurable.

## Test Plan

- [ ] Unit tests: gate matrix over (declared budget, compaction_count,
      override, stop_reason).
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: encode the audited 50-compaction session shape as
      a fixture and confirm it fails.

## Rollback Plan

Revert gate rule and schema fields in separate commits; skill text reverts to
soft budget language. No stored checkpoints become invalid retroactively if
the gate keys on contract version.
