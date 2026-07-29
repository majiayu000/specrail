# Tech Spec

## Linked Issue

GH-58

## Product Spec

`specs/GH58/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Requires unresolved-thread truth before merge; silent on who resolves | Ownership contract text |
| review skill | `skills/specrail-review-pr/SKILL.md` | Defines reviewer lane duties | Reviewer-side resolve duty |
| gate check | `checks/pr_gate.py` | Checks thread counts, not resolver identity | Enforcement point |
| schema | `schemas/pr_review_gate.schema.json` | Gate evidence structure | Gains per-thread resolver fields |
| implx | `skills/implx/SKILL.md` | Already states coordinator self-review is not a native thread | Precedent for role separation |

## Proposed Design

1. Extend per-thread gate evidence with `resolved_by` (login or lane id) and
   `resolver_role` (`reviewer_lane` | `human` | `implementer` | `unknown`).
2. `checks/pr_gate.py`: for every gate-relevant thread, require resolver
   fields; block when `resolver_role` is `implementer` or `unknown` for a
   thread opened by a reviewer lane; treat `outdated: true, resolved: false`
   as unresolved.
3. Update `schemas/pr_review_gate.schema.json` accordingly (structural
   authority mirrors the gate, per the GH-40 authority split).
4. Skill text: add a "Thread resolution ownership" section to
   `skills/specrail-review-pr/SKILL.md` (reviewer lane re-checks the fix and
   resolves its own threads) and a prohibition in
   `skills/specrail-implement-queue/SKILL.md` (implementation/orchestrator
   lanes never call `resolveReviewThread` on reviewer threads; on reviewer
   unavailability, route to the GH-59 failure path).
5. Fixtures: reviewer-resolved pass; implementer-resolved fail; missing
   attribution fail; outdated-unresolved fail.

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | skill contract text | doc review + check_workflow |
| P2 | `checks/pr_gate.py` resolver-role block | negative fixture fails |
| P3 | schema + check required fields | missing-attribution fixture fails |
| P4 | outdated-unresolved handling in check | outdated fixture fails |
| P5 | contract text (comment/push allowed) | doc review |

## Data Flow

Reviewer lane resolves thread on GitHub -> orchestrator collects thread list
(id, resolved, outdated, resolver) into gate evidence JSON ->
`checks/pr_gate.py` validates locally. Resolver identity comes from the
GraphQL `reviewThreads` payload; lane-role mapping comes from the recorded
lane roster in the evidence.

## Alternatives Considered

- GitHub-side enforcement (branch protection / app permissions): rejected —
  outside SpecRail's contract-pack scope and not portable across repos.
- Forbidding all agent resolution (humans only): rejected — reviewer lanes
  verifying their own findings and resolving them is the useful workflow;
  removing it just moves toil to humans.
- Heuristic detection from GitHub audit log only: rejected — evidence roster
  mapping is deterministic and testable offline.

## Risks

- Security: none; local evidence validation.
- Compatibility: evidence producers must record lane rosters; older fixtures
  updated in-PR.
- Performance: negligible.
- Maintenance: lane-role vocabulary must stay consistent with GH-59 evidence;
  coordinate field names.

## Test Plan

- [ ] Unit tests: resolver-role matrix (reviewer/human pass; implementer/
      unknown fail; outdated-unresolved fail).
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: replay one audited session's thread list through
      the check and confirm it is blocked.

## Rollback Plan

Revert schema/check field additions and skill sections in two independent
commits; no persisted-state migration.
