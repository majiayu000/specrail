# Parallel agent integration

Use parallel agents only when the caller requests them or the active
repository instructions require them.

Before starting parallel work:

1. Inventory current Issues, PRs, branches, and worktrees.
2. Give every agent a concrete task and disjoint file ownership.
3. Record the original branch and PR for existing work.
4. Keep one coordinator responsible for shared status and external actions.

Agents must not edit the same writable file concurrently. Each lane runs the
target repository's native verification for its own changes and reports the
exact commands and results. The coordinator reviews the combined diff and
current GitHub state before any authorized push or merge.
