---
name: specrail-diagnose-ci
description: Diagnose or fix CI failures using fresh logs, local reproduction, one root-cause hypothesis at a time, and repository-native verification.
---

# Diagnose CI

1. Collect the failing workflow, job, step, command, logs, PR head SHA, and base
   branch.
2. Reproduce the failure locally when the command is available.
3. Form one root-cause hypothesis and test it before editing.
4. If a fix is requested, change the smallest responsible production surface.
5. Rerun the failed command and relevant repository-native tests.
6. Report fresh results and any remote status that remains unknown.

Do not weaken tests, hide failures, or claim green CI from stale evidence.
