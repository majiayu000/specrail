# Tech Spec

## Linked Issue

GH-57

## Product Spec

`specs/GH57/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| pr gate skill | `skills/specrail-pr-gate/SKILL.md` | Defines gate evidence but no ordering contract vs merge | Home of the serial-ordering rule |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Requires gate evidence before merge but does not forbid parallel dispatch | Orchestrator-facing contract text |
| gate check | `checks/pr_gate.py` | Validates gate evidence content | Enforcement point for ordering fields |
| schema | `schemas/pr_review_gate.schema.json` | Structural contract for gate evidence | Gains ordering fields |
| fixtures/tests | `tests/`, `examples/fixtures/` | Existing gate fixtures | Positive/negative ordering fixtures |

## Proposed Design

1. Extend the pr_gate evidence contract with two fields per merge candidate:
   `gate_query_completed_at` (or a monotonic ordinal such as a step index) and
   `gate_query_head_sha`. The merge record carries `merge_dispatched_at` (or
   ordinal) and `merge_head_sha`.
2. `checks/pr_gate.py` enforces: ordering fields present; query completion
   strictly precedes merge dispatch; `gate_query_head_sha == merge_head_sha`;
   zero unresolved threads at query time. Any missing or inverted ordering is
   a blocking violation with an explicit message.
3. Update `schemas/pr_review_gate.schema.json` to require the new fields on
   merge-ready records (structural authority; gate remains behavioral
   authority, consistent with GH-40's contract-authority split).
4. Skill text: add a "Serial gate ordering" section to
   `skills/specrail-pr-gate/SKILL.md` and a matching prohibition in
   `skills/specrail-implement-queue/SKILL.md`: never dispatch gate query and
   merge in one parallel batch; re-query on staleness.
5. Fixtures: one passing record (query before merge, same SHA), negative
   records (query after merge; SHA mismatch; missing fields).

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `checks/pr_gate.py` ordering + SHA check | unit test with passing fixture |
| P2 | skill contract text | doc review + check_workflow |
| P3 | staleness rule in pr_gate check | negative fixture: SHA mismatch |
| P4 | schema required fields | schema instance test; missing-field fixture fails |
| P5 | ordering comparison in pr_gate check | negative fixture: query postdates merge |

## Data Flow

Orchestrator runs gate query -> writes gate evidence JSON (with completion
marker + head SHA) -> dispatches merge -> records merge marker. Reviewer of
record runs `python3 checks/pr_gate.py` over the evidence; check reads only
local JSON, no network calls.

## Alternatives Considered

- Enforce ordering purely in skill prose without check support: rejected —
  the audited failure happened despite prose-level gate requirements; the
  deterministic check is the point.
- Wall-clock timestamps only: kept as default but allow a monotonic step
  ordinal, since parallel batches may share timestamps; ordinal comparison is
  unambiguous.
- Intercepting `gh` calls at runtime: rejected — SpecRail is a contract pack,
  not a proxy; out of scope.

## Risks

- Security: none; check reads local evidence files only.
- Compatibility: existing pr_gate evidence producers must add fields; older
  fixtures need updating in the same PR.
- Performance: negligible; a few field comparisons.
- Maintenance: ordering fields must stay aligned between schema and check;
  covered by instance-validation tests (GH-40 pattern).

## Test Plan

- [ ] Unit tests: pr_gate ordering pass/fail cases (missing field, inverted
      order, SHA mismatch, stale query).
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: run `checks/pr_gate.py` against a real recorded
      merge evidence sample.

## Rollback Plan

Revert in two commits: (1) restore schema/check to previous field set,
(2) remove skill-text sections. No persisted state migration needed.
