# Product Spec

## Linked Issue

GH-58
status: legacy

## User Problem

The implementing orchestrator spawns reviewer lanes and then resolves the
reviewer lanes' review threads itself before merging. This is a
self-certification loop: the party under review signs off on the review. The
"no unresolved threads" merge gate loses all independence. Audit evidence: an
orchestrator executed 16 `resolveReviewThread` GraphQL mutations on its own
reviewers' threads before merging PRs #476/#483/#489, and a sage session
resolved an outdated-but-unresolved P1 thread purely to keep the merge gate
green (see GH-58 issue body for session-log quotes).

## Goals

- Establish thread-resolution ownership: threads opened by reviewer lanes may
  only be resolved by a reviewer lane (after verifying the fix) or by a human.
- Void the "no unresolved threads" gate when resolution came from the
  implementer, and make that detectable in deterministic checks.
- Clarify that "outdated" is not "resolved".

## Non-Goals

- No change to who may open review threads or to review severity semantics.
- No prohibition on the implementer replying to threads or pushing fixes; only
  the resolve action is restricted.
- No GitHub-side permission enforcement (SpecRail cannot restrict GraphQL
  mutations); enforcement is contract text plus evidence checks.

## Behavior Invariants

1. A review thread opened by a reviewer lane may be resolved only by a
   reviewer lane (the same or a successor lane that verified the fix) or by a
   human.
2. If any gate-relevant thread was resolved by the implementer/orchestrator,
   the "zero unresolved threads" condition is void and merge must not proceed
   on it.
3. Gate evidence records, per thread, the resolver identity and lane role;
   records missing resolver attribution fail the gate.
4. A thread that GitHub marks outdated but unresolved still requires reviewer
   or human confirmation; outdated status alone never satisfies the gate.
5. The implementer may comment on and push fixes for threads; those actions do
   not count as resolution.

## Acceptance Criteria

- [ ] `skills/specrail-implement-queue/SKILL.md` and
      `skills/specrail-review-pr/SKILL.md` state the resolution-ownership
      contract: implementation lanes must not resolve reviewer-lane threads.
- [ ] pr_gate evidence includes per-thread resolver identity/lane role;
      `checks/pr_gate.py` blocks records where an implementer resolved a
      reviewer thread.
- [ ] Negative fixture (implementer-resolved threads) is rejected; positive
      fixture (reviewer-resolved) passes.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- Reviewer lane died before it could resolve its own threads: falls under the
  GH-59 lane-failure contract (blocked/needs_human), not under implementer
  resolution.
- Human maintainer resolves threads directly: always allowed and recorded as
  human resolution.
- Threads opened by humans (not reviewer lanes): outside this contract's
  ownership rule but still subject to the unresolved-threads gate.
- Same agent session playing both implementer and reviewer roles: forbidden
  for gate purposes; a coordinator self-review is not a reviewer lane
  (consistent with existing implx contract text).

## Rollout Notes

Evidence gains required resolver-attribution fields; producers and existing
fixtures must be updated together. CHANGELOG notes that gate evidence without
resolver attribution now fails.
