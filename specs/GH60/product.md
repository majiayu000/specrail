# Product Spec

## Linked Issue

GH-60

## User Problem

`full_queue_drain` has no hard context budget. Audited sessions show a 72.6MB
log with 50 compaction events and a cumulative token counter of 944,437,310
ending mid-queue; a 20h12m session with 18 compactions; and a single
13.1-hour turn (duration_ms 47130965) that the user had to interrupt (see
GH-60 issue body for rollout file paths). After repeated compaction the gate
contracts, queue state, and tribal knowledge degrade, so the tail end of a
long drain is unauditable and low quality. Bounded reviewer lanes
(<2M tokens) behaved correctly throughout the same audit and are the
reference model.

## Goals

- Force `full_queue_drain` to execute as a sequence of bounded tranches with a
  hard context/compaction budget per session.
- On budget exhaustion: write a runtime checkpoint and hand off to a fresh
  session; treat this as a normal terminal, not a failure.
- Make over-budget continuation detectable as a contract violation.

## Non-Goals

- No change to queue selection or prioritization logic.
- No runtime enforcement inside the agent platform (SpecRail cannot stop a
  session); enforcement is contract text plus checkpoint evidence checks.
- No removal of `full_queue_drain` as a user-facing mode; only its execution
  shape changes.

## Behavior Invariants

1. A drain session has a declared hard budget before implementation work
   starts: a compaction budget (default: stop before the 2nd compaction
   event) and/or an item cap per tranche.
2. When the budget is reached, the session stops taking new queue items,
   writes a runtime checkpoint (queue truth, per-item state, resume prompt),
   and hands off; in-flight single items may complete only if that does not
   require another compaction.
3. Budget exhaustion with checkpoint + handoff is a successful terminal state;
   continuing to drain past the budget is a contract violation.
4. The checkpoint records the budget declaration, observed compaction count,
   and stop reason, so an auditor can verify compliance.
5. `full_queue_drain` semantics become "drain via repeated bounded tranches
   with checkpoint handoffs", not "one unbounded session".

## Acceptance Criteria

- [ ] `skills/implx/SKILL.md` and `skills/specrail-implement-queue/SKILL.md`
      state the hard-stop budget contract (declare budget up front; stop
      before the 2nd compaction by default; checkpoint + handoff on
      exhaustion).
- [ ] `schemas/runtime_checkpoint.schema.json` (or the checkpoint contract)
      includes budget fields: declared budget, compaction count, stop reason;
      `checks/runtime_ledger_gate.py` flags checkpoints showing over-budget
      continuation.
- [ ] Fixtures: budget-respected checkpoint passes; over-budget-continuation
      checkpoint fails.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- Compaction occurs mid-item: finish or checkpoint the current item safely,
  then stop; do not start the next item.
- User explicitly overrides the budget in-conversation: allowed, but the
  override and its scope must be recorded in the checkpoint.
- Very small queues that never approach the budget: contract is vacuous;
  checkpoint still records the declared budget.
- Runtime does not expose a compaction counter: fall back to an item cap and
  record `budget_basis: item_cap`; absence of any declared budget is the
  violation.

## Rollout Notes

Checkpoint schema gains budget fields (additive). Existing long-drain habits
change user-visibly: drains now end with a resume prompt instead of running
overnight. CHANGELOG and `AGENT_USAGE.md` should describe the
resume-in-fresh-session loop.
