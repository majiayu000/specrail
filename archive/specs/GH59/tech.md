# Tech Spec

## Linked Issue

GH-59

## Product Spec

`specs/GH59/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Requires reviewer lanes; no failure protocol | Lane-failure contract text |
| implx | `skills/implx/SKILL.md` | States coordinator self-review does not satisfy merge review | Baseline to strengthen with failure path |
| runtime gate | `checks/runtime_ledger_gate.py` | Validates checkpoint merge-readiness evidence | Enforcement for item states |
| pr gate | `checks/pr_gate.py` | Validates gate evidence | Enforcement for review-source field |
| schemas | `schemas/runtime_checkpoint.schema.json`, `schemas/pr_review_gate.schema.json` | No review-source or lane-failure fields | Structural contract |

## Proposed Design

1. Evidence model: per merge candidate add `review_source`
   (`independent_lane` | `self_review`) and `lane_failures[]`
   (lane id, failure kind: usage_limit | crash | zero_output | closed,
   observed marker). Checkpoint items gain state `blocked` with
   `blocked_reason: reviewer_lane_failure` and optional
   `self_review_authorization` (verbatim scope + conversation marker).
2. `checks/runtime_ledger_gate.py`: an item recorded as merged with
   `review_source: self_review` and no `self_review_authorization` is a
   blocking violation. An item with lane failures and no state downgrade and
   no successful retry lane is a violation.
3. `checks/pr_gate.py`: gate evidence missing `review_source` fails; the
   `self_review` value alone never satisfies the independent-review
   requirement.
4. Skill text (`specrail-implement-queue`): failure protocol — detect lane
   death; mark item blocked/needs_human; report in handoff; allowed recovery
   = new independent lane; forbidden = silent self-review substitution;
   authorization scope recording.
5. Fixtures: blocked-and-waiting pass; retried-with-new-lane pass;
   self-review-merged-unauthorized fail; unreported-failure fail.

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | checkpoint item state + runtime_ledger_gate | blocked fixture passes; unreported fixture fails |
| P2 | `self_review_authorization` requirement | unauthorized fixture fails |
| P3 | retry path in skill text + evidence | retry fixture passes |
| P4 | `review_source` in pr_gate check | missing-field fixture fails |
| P5 | skill contract text | doc review + check_workflow |

## Data Flow

Orchestrator observes lane result -> writes lane_failures + item state into
runtime checkpoint -> gate checks read checkpoint/gate JSON locally. No new
network calls; authorization is recorded as quoted user text plus a
conversation marker, verified by humans during review.

## Alternatives Considered

- Auto-retry N times before blocking: rejected as core contract — retry
  policy is runtime-specific; the contract only defines the blocked terminal
  and the sanctioned retry path.
- Treating self-review as acceptable when diff is "small": rejected — size
  heuristics are exactly the rationalization the audit caught.
- Verifying authorization cryptographically: rejected — out of scope;
  human-auditable quoted text is the SpecRail pattern.

## Risks

- Security: none.
- Compatibility: checkpoint schema gains fields; older checkpoints without
  `review_source` should be handled per the schema-versioning convention
  already used by runtime_ledger_gate.
- Performance: negligible.
- Maintenance: failure-kind vocabulary may grow; use an open enum with
  explicit `other` plus free-text detail.

## Test Plan

- [ ] Unit tests: gate matrix over (review_source, authorization, merged,
      lane_failures) combinations.
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: encode the audited #485/#489 scenario as a fixture
      and confirm it is blocked.

## Rollback Plan

Revert schema fields and gate rules in separate commits; skill text reverts
independently. Checkpoints written with the new fields remain valid under the
old schema if fields were additive-optional there.
