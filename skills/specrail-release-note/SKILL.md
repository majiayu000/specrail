---
name: specrail-release-note
description: Use when drafting a SpecRail release note after a linked PR has merged. Summarizes user-visible changes, verification, linked issues, risks, and rollout notes while preserving release and security human gates. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Release Note

Use this skill for the `draft_release_note` route.

## Steps

1. Confirm the PR is merged and identify the linked issue, commits, specs, and
   verification evidence.
2. If `workflow.yaml` is absent, report `not_adopted` and use repository-native
   checks. If it exists, the route gate is mandatory; a missing checker blocks:

```sh
python3 checks/route_gate.py --repo . --route draft_release_note --issue <issue-number> --pr <pr-number> --state done --json
```

3. Draft a concise release note in the selected locale.
4. Include user-visible change, linked work, verification, migration or rollback
   notes, and any known limitations.
5. Keep stable machine-facing IDs, paths, commands, and JSON keys in English.

## Boundaries

- Do not publish a release.
- Do not mark the release human gate complete.
- Do not include private security details in public notes.
- Do not claim closure for unverified issues or PRs.

Fix every reported rejection item before one bounded retry. Do not persist a
parallel retry ledger.
