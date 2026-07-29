---
name: specrail-workflow
description: Route an explicitly requested SpecRail task to the smallest focused skill for triage, specification, planning, implementation, review, CI diagnosis, release notes, or implementation comparison.
---

# Workflow router

1. Read the target repository instructions.
2. Search existing Issues, PRs, branches, docs, and code.
3. Identify the current phase:
   - triage;
   - write product or technical requirements;
   - plan tasks;
   - implement;
   - compare implementation with requirements;
   - review PR;
   - diagnose CI;
   - draft release note;
   - process an explicitly requested queue.
4. Load only the focused skill for that phase.
5. Use repository-native verification and current GitHub state.

SpecRail skills organize the work; they do not override repository policy or
grant external-action authority.
