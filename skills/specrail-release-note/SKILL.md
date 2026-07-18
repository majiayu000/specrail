---
name: specrail-release-note
description: Use when drafting a SpecRail release note after a linked PR has merged. Summarizes user-visible changes, verification, linked issues, risks, and rollout notes while preserving release and security human gates. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Release Note

Use this skill for the `draft_release_note` route.

## Steps

1. Confirm the PR is merged and identify the linked issue, commits, specs, and
   verification evidence.
2. Run the release-note route gate when available:

```sh
python3 checks/route_gate.py --repo . --route draft_release_note --issue <issue-number> --pr <pr-number> --state merged --json
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

## Rejection Persistence And Retry

When a gate command in this skill (`checks/route_gate.py`,
`checks/review_json_gate.py`, or `checks/pr_gate.py`) rejects with a decision
other than `allowed`, the caller persists the gate's JSON output to
`.specrail/runtime/rejections/<gate>-<issue|pr>.json` (create the directory if
missing). This write is orchestrator behavior; the gate itself stays
read-only. Use the `rejection_items[]` list to fix every defect in a single
round instead of guessing one item per retry.

On the next retry of the same gate for the same issue or PR, pass
`--prior-rejection .specrail/runtime/rejections/<gate>-<issue|pr>.json`. If
the new output contains a `repeat_rejection` section, the same item was
rejected verbatim twice: stop retrying and report the contract violation to a
human instead of starting another round.
