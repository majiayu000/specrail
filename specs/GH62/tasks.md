# Task Plan

## Linked Issue

GH-62

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP62-T001` Owner: schema | Done when: `schemas/runtime_checkpoint.schema.json` includes `tranche_mix` and per-item `pr_kind` fields | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH62`
- [ ] `SP62-T002` Owner: runtime_gate | Done when: `checks/runtime_ledger_gate.py` recomputes spec-only streaks, validates declarations, and cross-checks counters against item records | Verify: `python3 -m pytest -q tests/`
- [ ] `SP62-T003` Owner: queue_skill | Done when: `skills/specrail-implement-queue/SKILL.md` documents the spec/impl mix gate and explicit spec-only tranche declaration path | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP62-T004` Owner: checkpoint_template | Done when: `templates/tranche_checkpoint.md` includes mix-count and declaration lines | Verify: inspection and workflow validation pass
- [ ] `SP62-T005` Owner: tests | Done when: pass and fail fixtures plus unit tests cover undeclared spec-only streaks and declared spec-only tranches | Verify: `python3 -m pytest -q tests/`
- [ ] `SP62-T006` Owner: docs_changelog | Done when: `CHANGELOG.md` and `AGENT_USAGE.md` document the new mix gate and reporting requirement | Verify: inspection and workflow validation pass

## Parallelization

- Lane A: schema + gate + tests/fixtures.
- Lane B: skill markdown.
- Lane C: template + CHANGELOG + AGENT_USAGE.
Disjoint files; `pr_kind` enum agreed first.

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Undeclared 4-streak fixture demonstrably fails; declared tranche passes.

## Handoff Notes

Default consecutive spec-only cap is 3. Coordinates with GH-60's checkpoint
budget fields — if both land together, make one schema change. The
counter/item cross-check exists so agents cannot self-report a healthy mix
that the item list contradicts.
