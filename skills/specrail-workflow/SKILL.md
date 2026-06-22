---
name: specrail-workflow
description: Use when working in a repository that adopts SpecRail for issue-first, spec-first, AI-assisted development. Handles triage, product specs, tech specs, PR bodies, review summaries, and handoffs with locale-aware human-facing text, including Chinese (`zh-CN`) when the user writes Chinese or the repository presentation config requests it.
---

# SpecRail Workflow

Use this skill as the entrypoint for SpecRail-governed repository work.

## Startup

1. Search before creating a new issue, spec, template, policy, schema, or workflow.
2. Read applicable `AGENTS.md`.
3. Read `workflow.yaml`, `states.yaml`, `labels.yaml`, and relevant templates.
4. Identify the route:
   - `triage_issue`
   - `write_spec`
   - `implement`
   - `review_pr`
   - `fix_ci`
   - `draft_release_note`

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
- file paths such as `specs/GH1/product.md`
- command names and CLI flags
- JSON keys and schema field names

## Spec Creation

For feature work that needs a spec:

1. Confirm or create a linked GitHub issue when the user asks for GitHub workflow.
2. Use `specs/GH<issue-number>/product.md` and `specs/GH<issue-number>/tech.md`.
3. Prefer templates in `templates/<locale>/`; fall back to root `templates/`.
4. Keep behavior in product spec and implementation plan in tech spec.
5. Run:

```sh
python3 checks/check_workflow.py --repo . --spec-dir specs/GH<issue-number>
```

## Agent Boundaries

Agents may draft, review, diagnose, and propose labels.

Agents must not:

- provide final approval
- merge without explicit user authorization
- force push without explicit user authorization
- publish secrets or private security details
- change repository permissions
- bypass human gates

## Output

When reporting completion, include:

- issue or PR link, if created
- spec paths
- selected locale
- stable IDs kept in English
- verification commands and results
