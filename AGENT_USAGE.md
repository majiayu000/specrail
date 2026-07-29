# Agent usage

Use SpecRail skills as task-specific playbooks, not as permission or verdict
engines.

## Start

1. Read the target repository's `AGENTS.md`.
2. Inspect current GitHub Issues, PRs, reviews, branches, and CI.
3. Search before creating a new artifact.
4. Confirm goal, context, constraints, and done-when for non-trivial work.
5. Select only the focused skill needed for the current phase.

## Execute

- Triage: classify the request and identify missing information.
- Specify: write behavior, boundaries, technical choices, and verification.
- Implement: work on the original branch and PR when one exists.
- Review: inspect the current diff and report concrete findings with locations.
- Diagnose CI: reproduce the failing command, identify root cause, fix, rerun.
- Finish: run native verification, address threads, and report current status.

SpecRail adds no extra preflight or merge decision. Repository-native tests,
CI, review rules, and the caller's authorization determine what may happen.

## Queue work

For an explicitly requested queue, inventory the entire queue first. Process
existing PRs before creating replacement work. Keep a bounded list containing
the issue or PR, owner, branch, done-when, verification, blocker, and next
action. `integrations/threads.md` describes optional parallel ownership.

## External actions

Pushing, commenting, closing, publishing, and merging are external writes.
Perform them only when the caller has authorized the action and scope. Never
force-push or publish secrets.
