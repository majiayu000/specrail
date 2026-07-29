# SpecRail

SpecRail is a small collection of reusable skills and templates for
issue-first, spec-aware development. It helps an agent organize work without
installing a repository-specific enforcement layer.

The active package contains:

- focused skills for triage, planning, implementation, review, CI diagnosis,
  release-note drafting, and queue execution;
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

## Install the skills

Preview:

```sh
python3 tools/install_codex_skills.py --repo .
```

Apply:

```sh
python3 tools/install_codex_skills.py --repo . --apply
```

Verify an installed copy:

```sh
python3 tools/install_codex_skills.py --repo . --check-installed
```

## Historical archive

Earlier project specs and the earlier changelog are preserved under
`archive/`. They are non-normative and are not consumed by active tools, CI, or
skills.
