# Task Plan

## Linked Issue

GH-57

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Add ordering fields (`gate_query_completed_at`/ordinal,
      `gate_query_head_sha`, merge markers) to
      `schemas/pr_review_gate.schema.json`.
- [ ] Implement ordering + head-SHA + staleness enforcement in
      `checks/pr_gate.py` with explicit violation messages.
- [ ] Add "Serial gate ordering" contract text to
      `skills/specrail-pr-gate/SKILL.md`.
- [ ] Add the parallel-dispatch prohibition and re-query rule to
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add positive and negative fixtures plus unit tests.
- [ ] Update CHANGELOG for the new required evidence fields.

## Parallelization

- Lane A: `checks/pr_gate.py` + tests + fixtures.
- Lane B: `schemas/pr_review_gate.schema.json`.
- Lane C: skill markdown files + CHANGELOG.
Disjoint file sets; schema/check field names agreed in tech spec first.

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Negative fixture (query postdates merge) demonstrably fails the gate.

## Handoff Notes

Field naming must match between schema, check, and skill examples; if a
monotonic ordinal is chosen over wall-clock timestamps, record the decision
here for GH-58/GH-59 evidence structures to reuse.
