# Agent Usage

SpecRail is primarily for code agents, not for human project management. Humans
own policy and final gates; agents use this repository to decide how to triage,
write specs, prepare PRs, review, and report handoffs without inventing process.

## What The Agent Should Load

When a repository adopts SpecRail, the agent should read these files before
creating issues, specs, PRs, or reviews:

1. `AGENTS.md`
2. `workflow.yaml`
3. `states.yaml`
4. `labels.yaml`
5. the relevant template under `templates/` or `templates/<locale>/`
6. `skills/specrail-workflow/SKILL.md` when available

The skill is an execution guide. The YAML files and templates are the workflow
contract. The agent should not treat the skill as final authority when it
conflicts with repository policy or human instructions.

## Basic Agent Flow

1. Search existing issues and PRs before creating new work.
2. Identify the route:
   - `triage_issue`
   - `write_spec`
   - `implement`
   - `review_pr`
   - `fix_ci`
   - `draft_release_note`
3. Confirm the current state from durable repo state when possible.
4. Create or update the required artifact:
   - issue
   - `specs/GH<issue-number>/product.md`
   - `specs/GH<issue-number>/tech.md`
   - PR body
   - review result
   - handoff
5. Run deterministic checks before claiming completion:

```sh
python3 checks/check_workflow.py --repo .
python3 checks/check_workflow.py --repo . --spec-dir specs/GH<issue-number>
```

## Locale Behavior

Use human-facing text in the selected locale. If the user writes Chinese or the
selected locale is `zh-CN`, write these in Chinese:

- issue bodies
- product specs
- tech specs
- PR bodies
- review summaries
- handoffs
- error explanations

Do not translate stable machine-facing identifiers:

- action IDs such as `write_spec`
- state IDs such as `ready_to_spec`
- decision values such as `needs_human`
- artifact IDs such as `product_spec`
- paths such as `specs/GH1/product.md`
- commands and CLI flags
- JSON keys and schema field names

Use this locale selection order:

1. explicit user request
2. user's current language
3. `presentation.default_locale` in `workflow.yaml`
4. `presentation.fallback_locale`

## What Exists Today

SpecRail currently provides:

- state and label conventions
- issue/spec/PR templates
- `zh-CN` templates
- localized message files
- a Codex-compatible `specrail-workflow` skill
- a deterministic pack validator

This is enough for an agent to follow the process more consistently than raw
README instructions.

## What Does Not Exist Yet

SpecRail does not yet provide:

- a full evaluator that returns `allowed`, `warn`, `needs_human`, or `blocked`
- GitHub API evidence adapters
- automatic issue label checks
- automatic PR gate checks
- automatic template rendering commands
- automatic merge or final approval

Until those exist, agents should use SpecRail as a contract and must report what
they verified rather than claiming workflow state from assumptions.

## Human Gates

Agents may draft, propose, review, and diagnose. Agents must not:

- provide final approval
- merge without explicit authorization
- publish private security details
- change repository permissions
- bypass readiness labels or other human gates

