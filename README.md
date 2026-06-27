# SpecRail

[![workflow-check](https://github.com/majiayu000/specrail/actions/workflows/workflow-check.yml/badge.svg)](https://github.com/majiayu000/specrail/actions/workflows/workflow-check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/majiayu000/specrail?include_prereleases&label=release)](https://github.com/majiayu000/specrail/releases)

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
LICENSE                # MIT license
CHANGELOG.md           # release notes
workflow.yaml          # workflow metadata and adoption policy
states.yaml            # canonical issue/spec/PR state machine
labels.yaml            # recommended label taxonomy
docs/                  # adoption matrix and user-facing workflow docs
templates/             # issue, spec, and PR templates
locales/               # localized human-facing evaluator messages
integrations/          # optional adapters to agent orchestration workflows
skills/                # agent workflow entrypoints, including Codex-compatible skills
skills-lock.json       # repo-distributed skill lockfile
schemas/               # machine-readable artifact contracts
examples/adoptions/    # machine-readable adoption evidence fixtures
examples/fixtures/     # deterministic gate benchmark fixtures
review/                # agent-first and human-final review guides
policies/              # security and maintainer escalation policy
checks/check_workflow.py
checks/route_gate.py
checks/github_issue_evidence.py
checks/github_pr_evidence.py
checks/review_json_gate.py
.github/workflows/workflow-check.yml
```

## Quick Start

Validate the pack locally:

```sh
git clone https://github.com/majiayu000/specrail.git
cd specrail
python3 checks/check_workflow.py --repo .
```

Validate a spec packet:

```sh
python3 checks/check_workflow.py --repo . --spec-dir specs/GH1
```

Evaluate whether an agent may take the next workflow action from local evidence:

```sh
python3 checks/route_gate.py --repo . --route write_spec --issue 123 --state ready_to_spec --json
python3 checks/route_gate.py --repo . --route implement --issue 123 --state ready_to_implement --json
```

Collect read-only GitHub issue evidence before running the route gate:

```sh
python3 checks/github_issue_evidence.py --github-repo OWNER/REPO --issue 123 --json > issue-evidence.json
python3 checks/route_gate.py --repo . --route write_spec --issue 123 --evidence issue-evidence.json --json
```

`checks/github_issue_evidence.py` only reshapes `gh issue view` output into
local route evidence. It does not write labels, comments, issues, or PRs.

Evaluate whether PR merge evidence is complete before a maintainer merges:

```sh
python3 checks/github_pr_evidence.py --github-repo OWNER/REPO --pr 123 --json > pr-evidence.json
python3 checks/pr_gate.py --repo . --evidence pr-evidence.json --json
```

`checks/github_pr_evidence.py` is a read-only collector for GitHub CLI output.
`checks/pr_gate.py` owns the offline merge-readiness decision.

Validate an advisory review artifact against a unified diff:

```sh
python3 checks/review_json_gate.py --repo . --review artifacts/review/pr-123.json --diff pr.diff --json
```

Review artifacts are advisory evidence only. They do not grant final approval or
merge authority.

Evaluate a spec packet and adoption smoke evidence:

```sh
python3 evaluate.py --repo . --spec-dir specs/GH1 --format json
```

Inspect the recorded real-repo adoption signals:

- [`docs/ADOPTION_MATRIX.md`](docs/ADOPTION_MATRIX.md)
- [`examples/adoptions/matrix.json`](examples/adoptions/matrix.json)

The matrix currently records `rclean`, `litellm-rs`, and
`Claude-Code-Monitor` / `claude-hub` as pilot evidence at different maturity
levels. `evaluate.py` validates the required matrix records and local
SpecRail evidence paths.

Gate benchmark fixtures live in `examples/fixtures/`. They are deterministic
test inputs for route, PR, and review gates, not claims about current GitHub
state or adoption level.

Use the pack as a repository workflow contract:

```sh
cp -R templates schemas review policies checks skills examples docs .github /path/to/your-repo/
cp AGENT_USAGE.md SPEC.md CHANGELOG.md workflow.yaml states.yaml labels.yaml /path/to/your-repo/
cp skills-lock.json /path/to/your-repo/
```

Keep the consumer repository's own `README.md` and `LICENSE` unless the
maintainer explicitly wants to replace them.

Then ask your agent to read:

```text
AGENTS.md
workflow.yaml
states.yaml
labels.yaml
AGENT_USAGE.md
skills/specrail-workflow/SKILL.md
skills-lock.json
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

## Release

Current release notes live in [`CHANGELOG.md`](CHANGELOG.md). SpecRail v0.2.1
adds adoption matrix evidence for real pilot repositories and hardens evaluator
and CI coverage while remaining intentionally advisory: deterministic checks
first, automation later.

## Core Principle

Agents may suggest, draft, review, and diagnose. Humans own readiness labels,
security decisions, final approval, merge, and release.
