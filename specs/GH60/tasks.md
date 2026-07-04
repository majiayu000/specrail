# Task Plan

## Linked Issue

GH-60

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Add `budget` object (basis, compaction_budget, item_cap,
      compaction_count, stop_reason, budget_override) to
      `schemas/runtime_checkpoint.schema.json`.
- [ ] Enforce budget declaration and over-budget detection in
      `checks/runtime_ledger_gate.py`.
- [ ] Redefine `full_queue_drain` as repeated bounded tranches in
      `skills/implx/SKILL.md`.
- [ ] Add the hard-stop operational protocol to
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add budget/stop-reason lines to `templates/tranche_checkpoint.md`.
- [ ] Add fixtures (2 pass, 2 fail) and unit tests; update CHANGELOG and
      `AGENT_USAGE.md`.

## Parallelization

- Lane A: schema + runtime_ledger_gate + tests/fixtures.
- Lane B: implx + implement-queue skill text.
- Lane C: template + CHANGELOG + AGENT_USAGE.
Disjoint files; budget field names agreed first.

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Over-budget fixture demonstrably fails; exhaustion fixture passes.

## Handoff Notes

Default budget = stop before the 2nd compaction; runtimes without compaction
visibility use item caps with `basis: item_cap`. GH-62 (spec/impl ratio) adds
sibling per-tranche counters — coordinate the checkpoint schema change if both
land close together.
