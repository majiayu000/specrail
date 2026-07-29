---
name: specrail-implement-queue
description: Use only when implx delegates a GitHub issue or PR queue or the user names this skill. Drain actionable work from current GitHub truth while preserving original branches, bounded ownership, native verification, and caller-authorized delivery.
---

# Implement queue

## Startup

1. Read repository instructions and current GitHub Issues, PRs, reviews, CI,
   branches, and worktrees.
2. Search for duplicate or already-owned work.
3. Inventory the full queue, then select a bounded tranche.
4. Record issue/PR, owner, original branch, done-when, verification, blocker,
   and next action.

## Order

1. Finish existing non-draft PRs.
2. Resume issues that already have a remote branch.
3. Start unowned actionable issues.
4. Re-audit the full queue after every tranche.

For each item, use the focused implementation, review, or CI skill. Run only
repository-native verification. Push, comment, resolve threads, close, and
merge only within the caller's explicit authorization. Never force-push.

An item is complete only when its done-when conditions are met and current
GitHub state confirms the requested delivery action.
