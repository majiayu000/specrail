# Task Plan

## Linked Issue

GH-62

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Add `tranche_mix` object and per-item `pr_kind` to
      `schemas/runtime_checkpoint.schema.json`.
- [ ] Implement streak recomputation, declaration validation, and
      counter/item cross-check in `checks/runtime_ledger_gate.py`.
- [ ] Add "Spec/impl mix gate" section to
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add mix-count and declaration lines to
      `templates/tranche_checkpoint.md`.
- [ ] Add fixtures (2 pass, 2 fail) and unit tests; update CHANGELOG and
      `AGENT_USAGE.md`.

## Parallelization

- Lane A: schema + gate + tests/fixtures.
- Lane B: skill markdown.
- Lane C: template + CHANGELOG + AGENT_USAGE.
Disjoint files; `pr_kind` enum agreed first.

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Undeclared 4-streak fixture demonstrably fails; declared tranche
      passes.

## Handoff Notes

Default consecutive spec-only cap is 3. Coordinates with GH-60's checkpoint
budget fields — if both land together, make one schema change. The
counter/item cross-check exists so agents cannot self-report a healthy mix
that the item list contradicts.
