# AGENTS.md

SpecRail is a lightweight, non-enforcing workflow kit. Repository-native
instructions, tests, CI, and maintainer decisions remain authoritative.

## Working rules

- Search existing Issues, PRs, branches, docs, and code before creating work.
- State the goal, scope, constraints, and done-when before a non-trivial edit.
- Continue existing work on its original branch and PR.
- Keep changes limited to the requested issue and expose every discovered
  blocker instead of hiding the rest behind one sample.
- Use the repository's own build, test, lint, and type-check commands.
- Review the current diff and current remote state before reporting completion.
- Require explicit caller authorization for external writes such as pushing,
  commenting, closing, publishing, or merging.
- Never force-push, submit secrets, or publish security details.

## Historical material

`archive/` is retained for provenance only. Its contents are read-only history,
not current instructions, inputs, validation rules, or implementation plans.

## Language

Match the user's language for human-facing text. Keep stable identifiers,
paths, commands, and machine-facing keys in English.
