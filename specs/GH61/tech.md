# Tech Spec

## Linked Issue

GH-61

## Product Spec

`specs/GH61/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| review skill | `skills/specrail-review-pr/SKILL.md` | Defines one review pass; silent on rounds | Round/mode contract |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Owns threads orchestration for reviewer lanes | Lane input + resume rules |
| threads doc | `integrations/threads.md` | Native lane dispatch guidance | Resume capability description |
| review gate | `checks/review_json_gate.py` | Validates review result JSON | Enforcement point |
| schema | `schemas/review_result.schema.json` | Review result structure | Gains round/mode fields |

## Proposed Design

1. Extend `schemas/review_result.schema.json` with `review_round` (int >= 1),
   `review_mode` (`full` | `resumed` | `diff_only`), `base_head_sha` (head
   reviewed in the prior round, required for `diff_only`), and optional
   `human_full_review_request` (quoted text).
2. `checks/review_json_gate.py`: for a given PR, order review results by
   round; reject `review_round >= 3` with `review_mode: full` unless
   `human_full_review_request` is present; require `base_head_sha` on
   `diff_only`; require a findings checklist section
   (`prior_findings[]` with per-finding status) on `resumed` and `diff_only`
   rounds.
3. Skill text: `specrail-review-pr` documents the three modes and the
   checklist format; `specrail-implement-queue` documents lane input scope
   (diff + spec packet + checklist; never coordinator history) and the
   resume-first preference with the cap fallback.
4. `integrations/threads.md`: note that re-review should message/resume the
   existing reviewer lane when the runtime supports it, instead of spawning a
   new fork.
5. Fixtures: rounds 1-2 full (pass), round 3 full without request (fail),
   round 3 diff_only with checklist (pass), resumed round without checklist
   (fail).

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | schema round/mode fields | instance validation test |
| P2 | resume preference in skill text + checklist requirement | resumed-without-checklist fixture fails |
| P3 | cap logic in review_json_gate | round-3-full fixture fails |
| P4 | lane input scope contract text | doc review |
| P5 | human-request escape hatch | fixture with request passes |

## Data Flow

Reviewer lane emits review result JSON (round, mode, findings, checklist) ->
orchestrator stores it with the PR evidence -> `checks/review_json_gate.py`
validates the per-PR round sequence locally. No new network calls.

## Alternatives Considered

- Hard cap on total rounds (e.g. 5) instead of mode switching: rejected —
  the problem is cost-per-round (full history replay), not rounds existing;
  fixes legitimately need verification.
- Token-budget enforcement per lane in the gate: rejected — token counts are
  runtime-specific; input-scope rules are portable and reviewable.
- Always diff-only after round 1: rejected — a second full pass catches
  cross-cutting regressions cheaply enough; cap of 2 balances cost and rigor.

## Risks

- Security: none.
- Compatibility: older review results lack round/mode; gate applies the rule
  only when the fields are present or the repo declares the new contract
  version.
- Performance: strictly reduces cost.
- Maintenance: round ordering assumes results are collected per PR; the gate
  needs a stable grouping key (PR number + head SHA), documented in the
  schema.

## Test Plan

- [ ] Unit tests: round-sequence matrix (caps, modes, checklist presence,
      human request).
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: encode the audited PR #489 five-round shape as
      fixtures and confirm round 3+ full rounds fail.

## Rollback Plan

Revert gate rule, then schema fields, then skill text in independent commits.
No persisted-state migration.
