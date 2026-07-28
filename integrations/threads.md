# Native Threads Integration

Use native threads only when the user requests subagents/threads or the selected
skill explicitly delegates disjoint lanes.

## Ownership

- Assign each writable lane disjoint files or a dedicated worktree.
- Planner and reviewer lanes are read-only.
- The coordinator owns shared verification and final reconciliation.
- Do not fork the full coordinator history; send the exact task, branch/diff,
  linked Issue/spec paths, constraints, and done-when.

## Review

One reviewer lane per PR is the default. The canonical compact review contract
lives in `skills/specrail-review-pr/SKILL.md`; do not copy it here.

- Follow the canonical profile policy: fastlane self-review; standard/heavy
  independent review with hosted-thread collection. Noncanonical overrides
  block.
- Round 1 is full; round 2 exists only after an unresolved round-1 P0/P1 and is
  diff-only after its fix.
- A third round needs a human decision.

Wait once for the lane's bounded result. On failure, report it and decide
whether another independent lane is justified; do not manufacture evidence.

## Handoff

Return the lane ID, exact head/diff reviewed, findings, verification performed,
and unresolved blockers. Thread state is not durable workflow truth; refresh
GitHub before continuing.

Threads never grant approval, merge, issue closure, release, permission, or
security-disclosure authority.
