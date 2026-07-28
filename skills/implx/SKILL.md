---
name: implx
description: Use only for explicit implx requests. Plain implx drains the actionable SpecRail issue/PR queue in review mode; `implx auto` selects the explicitly authorized run-scoped auto mode without weakening security, review, CI, or merge evidence.
---

# Implx

Implx is the one-line router for `skills/specrail-implement-queue/SKILL.md`.

## Profile Read Set

Fastlane startup reads exactly `AGENTS.md`, `workflow.yaml`, and this file
(maximum 12 KiB). Load phase skills only when entering that phase. A full queue
then loads the queue skill; review loads
`skills/specrail-review-pr/SKILL.md`; implementation loads
`skills/specrail-implement/SKILL.md`; PR gating loads
`skills/specrail-pr-gate/SKILL.md`. Load
`skills/specrail-workflow/SKILL.md` only for route ambiguity.

## Mode

- Plain `implx`, `use implx`, or `用 implx`: full actionable queue in `review`
  mode unless the user explicitly limits scope.
- `implx auto`: same queue with run-scoped automation explicitly authorized by
  that invocation.
- One named issue: use the focused implementation skill when ownership,
  profile, and done-when are already clear.

Do not infer auto mode from repository configuration. The canonical review
contract is in `skills/specrail-review-pr/SKILL.md`; do not copy it here.

## Execution

1. Refresh GitHub issues, PRs, branches, and CI; map existing ownership.
2. Delegate the bounded queue to
   `skills/specrail-implement-queue/SKILL.md`.
3. Use `fastlane`, `standard`, or `heavy`; sensitive paths always become heavy.
4. Keep duplicate/closure results advisory. Current CI, P0/P1, security, and
   explicit heavy merge authorization remain blocking.
5. Never force-push, expose security details, or treat an advisory gate as final
   approval. External writes must remain inside the user's exact authorization.

If work must hand off, store only the optional five-field resume cursor defined
by the queue skill, then refresh GitHub on resume.
