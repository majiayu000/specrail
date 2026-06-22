# SpecRail

Agent-facing workflow pack for issue-first, spec-first, AI-assisted repository operations.

SpecRail is not a bot and not an agent runtime. It is a portable process
library: state machines, templates, schemas, review gates, and deterministic
checks that a repository can adopt before adding automation.

SpecRail's primary consumer is a code agent such as Codex, Claude Code, or a
repo-local automation agent. Humans maintain the policy, review final decisions,
and own gates such as readiness labels, security decisions, approval, merge, and
release.

## Goals

- Make repository work explicit as a state machine.
- Keep GitHub issues and pull requests as durable state.
- Require specs for ambiguous or product-facing changes.
- Let agents produce review and triage artifacts without final authority.
- Keep human maintainers as the final review and merge gate.

## Non-Goals

- No automatic merge.
- No security disclosure handling in public issues.
- No cloud control plane.
- No direct dependency on VibeGuard hooks or runtime.
- No assumption that every repository uses AI agents.

## MVP Contents

```text
workflow.yaml          # workflow metadata and adoption policy
states.yaml            # canonical issue/spec/PR state machine
labels.yaml            # recommended label taxonomy
templates/             # issue, spec, and PR templates
locales/               # localized human-facing evaluator messages
skills/                # agent workflow entrypoints, including Codex-compatible skills
schemas/               # machine-readable artifact contracts
review/                # agent-first and human-final review guides
policies/              # security and maintainer escalation policy
checks/check_workflow.py
.github/workflows/workflow-check.yml
```

## Adoption Path

1. Read [`AGENT_USAGE.md`](AGENT_USAGE.md) to understand how an agent should consume the pack.
2. Copy this pack into a repository or install it as a submodule/package.
3. Run `python3 checks/check_workflow.py --repo .`.
4. Add the GitHub Action from `.github/workflows/workflow-check.yml`.
5. Start with dry-run checks only.
6. Add label/comment automation only after maintainers trust the signal.

## Plan

See [`PLAN.md`](PLAN.md) for the agent-first product direction, current limits,
and the roadmap from templates to deterministic evaluator to automation.

## Core Principle

Agents may suggest, draft, review, and diagnose. Humans own readiness labels,
security decisions, final approval, merge, and release.
