# Product Spec

## Linked Issue

GH-61

## User Problem

Every fix → re-review round spawns a brand-new reviewer lane that replays the
coordinator's full history. Audited sessions show PR #115 receiving 4 full
reviewer lanes in ~45 minutes and PR #489 receiving 5 review rounds in one
evening, the 5th dying with zero output; session files grew from 4.4MB to
7.7MB in a day and per-PR token cost was roughly 4x what a bounded flow needs
(see GH-61 issue body for rollout file paths). Later rounds are both the most
expensive and the least reliable. Related: #55 covers duplicate PR creation;
this issue covers duplicate full re-review — the same duplicate-work family
at the review stage.

## Goals

- Re-review of a new head should resume the prior reviewer lane with a
  findings checklist instead of forking full history.
- Where resume is unavailable, cap independent full re-review rounds
  (default: 2) and switch to diff-only review afterwards.
- Keep reviewer lanes bounded, matching the <2M-token lanes that behaved
  correctly in the audit.

## Non-Goals

- No change to review quality requirements or severity classification.
- No prohibition of a genuinely fresh independent review when a human asks
  for one.
- No runtime implementation of lane resume (that is platform capability);
  SpecRail defines the contract and the evidence.

## Behavior Invariants

1. Each review round records a round number and a review mode:
   `full` | `resumed` | `diff_only`.
2. Round 1 may be `full`. A re-review after fixes prefers `resumed` (same
   lane, carrying a findings checklist: prior finding → fixed/not fixed).
3. If resume is unavailable, at most 2 `full` rounds are allowed per PR;
   round 3 and later must be `diff_only` (scope: diff since the last reviewed
   head plus the findings checklist).
4. Reviewer lanes never receive the coordinator's full history; the review
   input is the PR diff, the spec packet, and the findings checklist.
5. Review evidence showing a third (or later) `full` round without a recorded
   human request is a contract violation.

## Acceptance Criteria

- [ ] `skills/specrail-implement-queue/SKILL.md` (threads orchestration) and
      `skills/specrail-review-pr/SKILL.md` state the resume/cap/diff-only
      contract and the bounded-lane input rule.
- [ ] Review evidence structure records round number and review mode;
      `checks/review_json_gate.py` (or pr_gate) rejects an over-cap `full`
      round.
- [ ] Fixture: round-3 `full` review is rejected; `resumed` and `diff_only`
      rounds pass.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- The fix rewrote most of the PR (diff-only would effectively be full):
  diff-only vs full is defined by input scope, not diff size; a large diff
  reviewed without coordinator history is still compliant.
- Prior lane produced a wrong or empty findings checklist: the next round may
  regenerate the checklist from the recorded review threads; that does not
  reset the full-round cap.
- Human explicitly requests a fresh full review: allowed at any round; record
  the request in the evidence.
- Different reviewers for different concern areas (security vs logic) in the
  same round: they share one round number.

## Rollout Notes

Additive evidence fields (round, mode). Runtimes without lane resume simply
never emit `resumed`; the cap + diff-only path is the portable floor.
CHANGELOG notes the new violation class.
