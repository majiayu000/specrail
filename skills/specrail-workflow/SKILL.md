---
name: specrail-workflow
description: Use as the router/startup skill when working in a repository that adopts SpecRail for issue-first, spec-first, AI-assisted development. Routes triage, spec writing, task planning, implementation, PR review, CI diagnosis, PR gates, release notes, and spec-vs-implementation checks to focused SpecRail skills while preserving locale and human-gate boundaries. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Workflow

Use this skill as the entrypoint for SpecRail-governed repository work. Load a
focused SpecRail skill after the route is known.

## Startup

1. Search before creating a new issue, spec, template, policy, schema, or workflow.
2. Read applicable `AGENTS.md`, then `AGENT_USAGE.md` and `PLAN.md` when present.
3. Check adoption first. If `workflow.yaml` is absent, report `not_adopted` and
   use repository-native policy without claiming a SpecRail gate result. If it
   exists, the repository is adopted: required SpecRail assets are mandatory
   and missing assets block. Resolve issue artifact paths from its
   `artifacts.*` templates and never assume a `specs/` root.
4. Identify the route:
   - `triage_issue`
   - `write_spec`
   - `implement`
   - `review_pr`
   - `fix_ci`
   - `draft_release_note`
5. In an adopted repository, run `checks/route_gate.py`; a missing checker
   blocks. Treat `allowed` as permission to proceed, `warn` as
   proceed-with-caution, `needs_human` as a maintainer gate, and `blocked` as a
   stop condition.
6. When GitHub issue evidence is needed and the repository includes the adapter,
   collect it read-only:

```sh
python3 checks/github_issue_evidence.py --github-repo <owner/repo> --issue <issue-number> --json > issue-evidence.json
```

## Route To Focused Skills

- Use `skills/specrail-triage-issue/SKILL.md` for issue classification, duplicate
  searches, label proposals, and triage handoffs.
- Use `skills/specrail-write-product-spec/SKILL.md` for
  the resolved `artifacts.product_spec` path.
- Use `skills/specrail-write-tech-spec/SKILL.md` for
  the resolved `artifacts.tech_spec` path.
- Use `skills/specrail-plan-tasks/SKILL.md` for
  the resolved `artifacts.task_plan` path.
- Use `skills/specrail-implement/SKILL.md` for code or workflow-asset changes
  after the implementation gate.
- Use `skills/specrail-implement-queue/SKILL.md` only when the user names
  implx or specrail-implement-queue. When multiple approved specs are ready
  but the user named neither, work issue by issue through
  `skills/specrail-implement/SKILL.md` (or mention that implx is available
  for coordinated queue drains); do not enter queue orchestration or its
  authorization mode uninvited.
- Use `skills/implx/SKILL.md` when the user explicitly asks for `implx`,
  `use implx`, or `用 implx` as the shortcut for SpecRail implementation queue
  work with optional threads orchestration and merge gates.
- Use `skills/specrail-check-impl-against-spec/SKILL.md` to compare a diff or PR
  with the linked product spec, tech spec, and task plan.
- Use `skills/specrail-review-pr/SKILL.md` for advisory PR review.
- Use `skills/specrail-diagnose-ci/SKILL.md` for CI failure investigation and
  focused fixes.
- Use `skills/specrail-pr-gate/SKILL.md` before reporting merge readiness.
- Use `skills/specrail-release-note/SKILL.md` after merge when drafting release
  notes.

For setup, installation, update, verification, or adoption requests, use
`skills/specrail-install/SKILL.md` before selecting an issue/spec workflow
route. Setup is not a `route_gate.py` action unless a repository explicitly
adds that policy.

Default to `write_spec` before `implement` for product-facing, architecture,
cross-module, public API, workflow-policy, or ambiguous behavior changes.
Choose direct `implement` only when the change is already covered by an
approved spec, is a small mechanical fix, is a test-only/doc-only correction, is
a focused CI fix, or the user explicitly asks to skip spec creation.

If a repository has not adopted SpecRail but the current work is complex enough
to need issue/spec/gate discipline, switch the work into SpecRail mode. Use the
actual route/spec/task/gate structure in the repository's existing
specs/plan/docs location instead of treating SpecRail as a loose checklist. Do
not copy SpecRail files, install local skills, create remote issues or PRs, add
labels, approve, merge, or bypass maintainers unless the user explicitly asks
for that action.

If `write_spec` is selected and no GitHub issue number is available, search for
an existing issue first. If none exists and GitHub workflow is in scope, create
or request a linked issue before writing the resolved `artifacts.product_spec`
and `artifacts.tech_spec` paths. Do not treat a missing issue number as
permission to skip the spec.

## Locale

Choose the language for human-facing text in this order:

1. Explicit user request.
2. User's current language.
3. `presentation.default_locale` in `workflow.yaml`.
4. `presentation.fallback_locale`.

When the user writes Chinese or the selected locale is `zh-CN`, write human-facing artifacts in Chinese:

- issue bodies
- `product.md`
- `tech.md`
- PR bodies
- review summaries
- handoffs
- error explanations

Do not translate stable machine-facing identifiers:

- action IDs such as `write_spec`
- state IDs such as `ready_to_spec`
- decision values such as `needs_human`
- artifact IDs such as `product_spec`
- default-pack file paths such as `specs/GH1/product.md`
- command names and CLI flags
- JSON keys and schema field names

## Optional Threads Integration

Read `integrations/threads.md` only when the user requests subagents/threads or
the selected route explicitly delegates disjoint lanes.

Keep the boundary clear:

- SpecRail owns policy, locale, required artifacts, human gates, and
  deterministic verification.
- Threads owns temporary lane assignment and returns bounded results.
- Optional five-field resume cursors are local handoff notes only; they do not
  replace GitHub or SpecRail artifacts as workflow truth or participate in gates.
- If threads are unavailable, continue with the single-agent flow without
  inventing fallback evidence.

## Agent Boundaries

Agents may draft, review, diagnose, and propose labels.

Agents must not:

- provide final approval
- merge without explicit user authorization
- force push without explicit user authorization
- publish secrets or private security details
- change repository permissions
- bypass human gates

Do not install repo-distributed SpecRail skills into `$HOME` unless a human
explicitly requests installation. Treat `skills-lock.json`, when present, as the
declared repo skill set. If local Codex skill installation is explicitly
requested, run `python3 tools/install_codex_skills.py --repo .` first and use
`--apply` only for the requested write.

## Output

When reporting completion, include:

- issue or PR link, if created
- spec paths
- selected locale
- stable IDs kept in English
- verification commands and results
- PR gate decision when merge readiness was evaluated
