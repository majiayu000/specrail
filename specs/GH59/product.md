# Product Spec

## Linked Issue

GH-59

## User Problem

When a reviewer lane fails for platform reasons (usage limits, crashes, zero
output), the orchestrator silently downgrades "independent review" to "local
self-review by the orchestrator" and proceeds to merge without re-confirming
with the user. Independent review is the premise of the merge gate; a silent
substitute means merging with no gate at all. Audit evidence: three review
sub-threads died with "You've hit your usage limit"; the orchestrator replaced
them with local re-checks and merged #485/#489 on that basis (see GH-59 issue
body for session-log quotes).

## Goals

- Make reviewer-lane failure a blocking event: the affected item downgrades to
  blocked/needs_human and is reported honestly in the handoff/checkpoint.
- Require fresh, explicit, in-conversation user authorization before any merge
  that rests on self-review.
- Allow retry with another independent reviewer lane as the sanctioned
  recovery path.

## Non-Goals

- No attempt to prevent platform failures themselves or add retry/backoff
  machinery to the runtime.
- No change to what a successful review must contain.
- No new human gates for the case where an independent lane succeeded.

## Behavior Invariants

1. A reviewer-lane failure (usage limit, crash, zero output, closed before
   producing a review) downgrades the affected queue item to
   blocked/needs_human and is recorded in the runtime checkpoint/handoff.
2. Merge based on self-review requires explicit user authorization given in
   the current conversation after the failure was reported; prior queue-drain
   authorization does not cover it.
3. Retrying with a different independent reviewer lane is allowed and, on
   success, restores the normal gate path.
4. Gate evidence records the review source (`independent_lane` vs
   `self_review`) and any lane-failure events; a merged item whose evidence
   shows self-review without fresh authorization is a violation.
5. Reporting the failure and waiting is the default; silence about a lane
   failure is itself a contract violation.

## Acceptance Criteria

- [ ] `skills/specrail-implement-queue/SKILL.md` contains the lane-failure
      contract: failure → blocked/needs_human; self-review substitution
      forbidden without fresh explicit authorization.
- [ ] Runtime checkpoint / pr_gate evidence records review source and lane
      failure events; `checks/pr_gate.py` or
      `checks/runtime_ledger_gate.py` blocks the combination
      "self_review + no fresh authorization + merged".
- [ ] Negative fixture (lane failed, self-review, merged) is rejected;
      positive fixture (downgraded to blocked, waiting for human) passes.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- Partial review output before the lane died: treat as failed unless the lane
  produced a complete review verdict; partial findings may seed the retry
  lane.
- All available reviewer capacity exhausted (every retry hits the limit): the
  item stays blocked; the tranche continues with other items or checkpoints
  out (GH-60).
- User grants blanket "self-review is fine for this tranche" upfront: the
  authorization must still be re-confirmed per failure occurrence unless the
  user explicitly scoped it to the whole tranche; record the scope.
- Lane failure discovered only after merge (post-hoc audit): closure audit
  must flag the merged item as a violation, not rewrite history.

## Rollout Notes

Adds required fields to checkpoint/gate evidence; producers and fixtures
update together. CHANGELOG documents the new blocked/needs_human semantics so
downstream repos adopting SpecRail know lane failures now halt items.
