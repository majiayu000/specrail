---
name: specrail-implement
description: Implement a linked issue from its current requirements and repository instructions, using the original branch and PR when present and repository-native verification.
---

# Implement

1. Read the Issue, current code, repository instructions, and available current
   requirement documents.
2. Search for an existing PR, remote branch, or overlapping implementation.
3. State scope and done-when; for non-trivial work, present a short plan before
   editing.
4. Reproduce bugs before fixing them.
5. Implement the smallest complete change on the original branch.
6. Add or update tests for changed behavior without weakening existing tests.
7. Run the repository's build, type-check, lint, and test commands appropriate
   to the change.
8. Review the current diff for scope, errors, security, and missing coverage.
9. Report exact results and remaining risks.

External writes require caller authorization. Never force-push or publish
security-sensitive details.
