# SpecRail

SpecRail is a small collection of reusable skills and templates for
issue-first, spec-aware development. It helps an agent organize work without
installing a repository-specific enforcement layer.

The active package contains:

- one default `specrail` entrypoint for opt-in workflow routing;
- one explicit `specrail-heavy` entrypoint for deeper planning and verification;
- one explicit `implx` entrypoint for authorized queue execution;
- English and Chinese templates for Issues, specs, task plans, and PRs;
- an optional local skill installer;
- an optional queue runner for explicitly authorized unattended runs.

It does not ship workflow checkers, evidence schemas, policy evaluators, or CI
verdict scripts. Use each target repository's normal build, test, lint,
type-check, review, and GitHub status instead.

## Direct workflow

1. Search current Issues, PRs, branches, and code.
2. Reuse an existing branch and PR when work already exists.
3. Make goal, scope, constraints, and done-when explicit.
4. Plan non-trivial changes, then implement the smallest complete solution.
5. Run repository-native verification and inspect the current diff.
6. Address review threads on the original PR.
7. Push, comment, close, or merge only with the caller's authorization.

Ordinary coding requests do not activate SpecRail. The user must explicitly
say `SpecRail`, `SpecRail Heavy`, or `implx`.

## Install profiles

The user-level default target is `~/.agents/skills`. Every installed entrypoint
includes `agents/openai.yaml` with implicit invocation disabled; installation
alone does not activate SpecRail.

Preview the default `core` profile:

```sh
python3 tools/install_codex_skills.py --repo .
```

Install only the single `specrail` entrypoint:

```sh
python3 tools/install_codex_skills.py --repo . --profile core --apply
```

Install `specrail` plus the explicit Heavy entrypoint:

```sh
python3 tools/install_codex_skills.py --repo . --profile heavy --apply
```

Install all three explicit entrypoints, including `implx`:

```sh
python3 tools/install_codex_skills.py --repo . --profile all --apply
```

Switching profiles removes stale SpecRail-managed entrypoints and preserves
unrelated user skills. Verify the selected profile without writing:

```sh
python3 tools/install_codex_skills.py --repo . --profile core --check-installed
```

To migrate an older global installation, preview both the new install and old
directory cleanup:

```sh
python3 tools/install_codex_skills.py --repo . --profile core \
  --legacy-target-dir ~/.codex/skills \
  --legacy-archive-dir ~/.codex/specrail-skills-v1
```

After reviewing the exact paths, apply the same command with `--apply`. Only
known SpecRail-managed skill directories are moved out of the legacy target;
unrelated skills are preserved and the archived copies remain recoverable.

For a repository-scoped install, pass its official skill directory explicitly:

```sh
python3 tools/install_codex_skills.py --repo . --profile core \
  --target-dir /path/to/consumer/.agents/skills --apply
```

This does not modify the consumer's `AGENTS.md`, checks, or CI workflows.

## Historical archive

Earlier project specs and the earlier changelog are preserved under
`archive/`. They are non-normative and are not consumed by active tools, CI, or
skills.
