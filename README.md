# SpecRail

Standard workflow pack for issue-first, spec-first, AI-assisted repository operations.

SpecRail is not a bot and not an agent runtime. It is a portable process
library: state machines, templates, schemas, review gates, and deterministic
checks that a repository can adopt before adding automation.

Spec-first rails for agent-assisted repository workflows.

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
schemas/               # machine-readable artifact contracts
review/                # agent-first and human-final review guides
policies/              # security and maintainer escalation policy
checks/check_workflow.py
.github/workflows/workflow-check.yml
```

## Adoption Path

1. Copy this pack into a repository or install it as a submodule/package.
2. Run `python3 checks/check_workflow.py --repo .`.
3. Add the GitHub Action from `.github/workflows/workflow-check.yml`.
4. Start with dry-run checks only.
5. Add label/comment automation only after maintainers trust the signal.

## Core Principle

Agents may suggest, draft, review, and diagnose. Humans own readiness labels,
security decisions, final approval, merge, and release.
