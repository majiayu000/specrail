# Task Plan

## Linked Issue

GH-60

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP60-T001` Owner: schema | Done when: `schemas/runtime_checkpoint.schema.json` includes a `budget` object with basis, compaction budget, item cap, compaction count, stop reason, and override fields | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH60`
- [ ] `SP60-T002` Owner: runtime_gate | Done when: `checks/runtime_ledger_gate.py` enforces budget declaration and over-budget continuation detection | Verify: `python3 -m pytest -q tests/`
- [ ] `SP60-T003` Owner: implx_skill | Done when: `skills/implx/SKILL.md` defines `full_queue_drain` as repeated bounded tranches with checkpoint handoff | Verify: inspection and workflow validation pass
- [ ] `SP60-T004` Owner: queue_skill | Done when: `skills/specrail-implement-queue/SKILL.md` documents the hard-stop operational protocol | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP60-T005` Owner: checkpoint_template | Done when: `templates/tranche_checkpoint.md` includes budget and stop-reason lines | Verify: inspection and workflow validation pass
- [ ] `SP60-T006` Owner: tests_docs | Done when: pass and fail fixtures, unit tests, `CHANGELOG.md`, and `AGENT_USAGE.md` cover budget exhaustion and over-budget continuation | Verify: `python3 -m pytest -q tests/`

## Parallelization

- Lane A: schema + runtime_ledger_gate + tests/fixtures.
- Lane B: implx + implement-queue skill text.
- Lane C: template + CHANGELOG + AGENT_USAGE.
Disjoint files; budget field names agreed first.

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Over-budget fixture demonstrably fails; exhaustion fixture passes.

## Handoff Notes

Default budget = stop before the 2nd compaction; runtimes without compaction
visibility use item caps with `basis: item_cap`. GH-62 (spec/impl ratio) adds
sibling per-tranche counters — coordinate the checkpoint schema change if both
land close together.
