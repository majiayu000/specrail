# Active design

## Purpose

SpecRail provides reusable text workflows that help agents deliver
issue-linked changes consistently while leaving authority with the target
repository and its maintainers.

## Components

- `skills/specrail/`: the only default, explicitly invoked workflow router.
- `skills/specrail-heavy/`: optional explicit deep-work entrypoint.
- `skills/implx/`: optional explicit queue entrypoint.
- `templates/`: optional starting points for Issues, specs, task plans, and PRs.
- `tools/install_codex_skills.py`: dry-run-first local skill installer.
- `tools/queue-runner.sh`: optional runner for an explicitly authorized queue.
- `integrations/threads.md`: ownership rules for optional parallel work.

## Design constraints

1. Skills describe actions and evidence; they do not produce authoritative
   allow/block verdicts.
2. A target repository's own instructions and verification commands take
   precedence.
3. Existing branches and PRs are ownership facts and must be reused.
4. Human-facing text follows the user's language; stable identifiers remain in
   English.
5. External writes require caller authorization.
6. Historical artifacts under `archive/` never participate in active work.
7. Installation and activation are separate: `core` installs one entrypoint,
   and no entrypoint activates from an ordinary coding request.

## Non-goals

- Defining a second CI or merge policy.
- Replacing repository-native tests or review.
- Persisting attestations or synthetic approval evidence.
- Treating archived specs as current requirements.
- Registering every workflow phase as a top-level installed skill.
