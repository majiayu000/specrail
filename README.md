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
tools/                 # optional local installation helpers
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
checks/runtime_ledger_gate.py
checks/closure_audit.py
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

Validate every `specs/GH<number>` packet:

```sh
python3 checks/check_workflow.py --repo . --all-specs
```

The all-specs scan uses `workflow.yaml`'s `artifacts.spec_packet` template, so
adopted repositories may keep packets under paths such as `docs/specs/GH1`.

Evaluate whether an agent may take the next workflow action from local evidence:

```sh
python3 checks/route_gate.py --repo . --route write_spec --issue 123 --state ready_to_spec --json
python3 checks/route_gate.py --repo . --route implement --issue 123 --state ready_to_implement --json
```

Collect read-only GitHub issue evidence before running the route gate:

```sh
python3 checks/github_issue_evidence.py --repo . --github-repo OWNER/REPO --issue 123 --json > issue-evidence.json
python3 checks/route_gate.py --repo . --route write_spec --issue 123 --evidence issue-evidence.json --json
```

`checks/github_issue_evidence.py` is read-only. It uses `gh issue view` for issue
state and labels. For a trusted `ready_to_implement` issue in a repository with
a sensitive registry, it first queries the GitHub default-base identity, checks
that identity against the local `origin` ref and symbolic `origin/HEAD`, and
classifies the approved tech manifest from that exact base. A non-sensitive
plan stops there. A sensitive plan additionally queries the current approval
label and latest matching label event through GraphQL, then uses the REST
associated-PR endpoint to prove each approved spec source came from exactly one
merged default-branch PR.

The adapter does not write labels, comments, issues, or PRs. Body hints remain
untrusted. Missing or non-symbolic `origin/HEAD`, default-base drift, an empty
completed planned-path list, incomplete latest approval actor/timestamp, missing
merged-spec provenance, or approved-spec content drift fails closed. Ordinary,
classified non-sensitive, and classified sensitive outputs conform to
`schemas/issue_evidence.schema.json`. Artifact paths are rendered from the
selected repo's `workflow.yaml`.

Evaluate whether PR merge evidence is complete before a maintainer merges:

```sh
python3 checks/github_pr_evidence.py --github-repo OWNER/REPO --pr 123 --json > pr-evidence.json
python3 checks/pr_gate.py --repo . --evidence pr-evidence.json --json
```

`checks/github_pr_evidence.py` is a read-only collector for GitHub CLI output.
`checks/pr_gate.py` owns the offline merge-readiness decision.

After a merge, audit that the allowed gate query, merge dispatch, and confirmed
remote merge all refer to the final head and satisfy `gate < dispatch <= merged`:

```sh
python3 checks/closure_audit.py --repo . --evidence closure-evidence.json --json
```

The closure audit is offline and advisory-only. It performs no GitHub writes,
returns `0` for a compliant chain, `1` for a schema-valid violation, and `2`
for malformed input. Violations include a stable `required_follow_up` payload
that a consumer may persist or route without granting the audit write access.

Validate an optional local runtime checkpoint for long agent runs:

```sh
python3 checks/runtime_ledger_gate.py --checkpoint .specrail/runtime/current.json --json
```

Runtime checkpoints are handoff aids for bounded agent tranches. They do not
replace GitHub issues, pull requests, labels, reviews, branches, or SpecRail
spec packets as durable workflow state. For checkpoint contracts, the schema is
the structure authority and `checks/runtime_ledger_gate.py` is the behavior
authority; see [`SPEC.md`](SPEC.md#runtime-checkpoint-contract-authority).

Validate an advisory review artifact against a unified diff:

```sh
python3 checks/review_json_gate.py --repo . --review artifacts/review/pr-123.json --diff pr.diff --json
```

Review artifacts are advisory evidence only. They do not grant final approval or
merge authority. Their body must include `## Summary` and `## Verdict`; inline
comments may use validated multi-line ranges and RIGHT-side suggestion blocks.

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

For long issue or PR queues, agents may also keep an optional local runtime
checkpoint based on [`templates/tranche_checkpoint.md`](templates/tranche_checkpoint.md).
The checkpoint is for context-budget and handoff control only; the canonical
workflow truth remains the repository and GitHub artifacts above.

Gate benchmark fixtures live in `examples/fixtures/`. They are deterministic
test inputs for route, PR, and review gates, not claims about current GitHub
state or adoption level.

## Autonomous SpecRail Mode

An agent should switch complex work into SpecRail mode before broad
implementation, even if the repository has not adopted the full pack. Typical
triggers are product-facing changes, architecture changes, cross-module work,
public API changes, workflow-policy changes, PR merge-readiness checks, CI
diagnosis with unclear ownership, or ambiguous requests whose done-when is not
yet testable.

SpecRail mode means the work uses the actual SpecRail structure: search first,
choose a route, produce or request durable product/tech/task artifacts, preserve
human gates, and run deterministic verification. If the repository has not
adopted the pack, use its existing specs/plan/docs location to carry that
structure. Do not silently copy this pack into a repository, install local
skills, create remote issues or PRs, add labels, approve, merge, or bypass
maintainers. Those actions require an explicit user request.

## Agent-First Setup

For setup, installation, update, verification, or adoption, ask the agent to use
`skills/specrail-install/SKILL.md`. The skill is the agent-facing entrypoint and
decides whether to run a doctor check, install local Codex skills, update global
guidance, or plan repository adoption. The CLI commands below are deterministic
helpers used by the skill, not the primary interface humans need to memorize.

## Optional Local Codex Skill Install

Local installation is optional. It is only for users who explicitly want this
checkout's SpecRail skills available from the local Codex skill directory. It is
not required for adopting SpecRail in a repository.

Preview the install plan without writing files:

```sh
python3 tools/install_codex_skills.py --repo .
```

Apply the install after reviewing the plan:

```sh
python3 tools/install_codex_skills.py --repo . --apply
```

The installer validates `skills-lock.json`, syncs only the locked skill
directories, writes to `$CODEX_HOME/skills` when `CODEX_HOME` is set or
`~/.codex/skills` otherwise, and refuses unsafe targets that would overwrite the
source skills. A new Codex session may be needed before newly installed skills
are visible.

## Repository Adoption

Use the pack as a repository workflow contract. For a normal repository, copy
the pack files into the target repo and keep that repo's product docs intact:

```sh
cp -R templates schemas review policies checks skills tools examples docs .github /path/to/your-repo/
cp AGENT_USAGE.md SPEC.md CHANGELOG.md workflow.yaml states.yaml labels.yaml /path/to/your-repo/
cp skills-lock.json /path/to/your-repo/
```

Keep the consumer repository's own `README.md` and `LICENSE` unless the
maintainer explicitly wants to replace them.

The workflow checker validates the copied SpecRail schema and template set by
explicit ownership. Consumer-owned files may coexist under `schemas/` and
`templates/` without being treated as SpecRail assets.

If the consumer repository does not already have an `AGENTS.md`, add a short
entrypoint that points agents at the copied SpecRail contract:

```md
# AGENTS.md

Read `AGENT_USAGE.md`, `workflow.yaml`, `states.yaml`, `labels.yaml`, and
`skills/specrail-workflow/SKILL.md` before creating issues, specs, PRs, reviews,
or handoffs. Keep automation in dry-run/advisory mode unless a maintainer
explicitly authorizes otherwise.
```

If the consumer repository already has an `AGENTS.md`, merge the SpecRail
entrypoint into the existing instructions instead of replacing local policy.

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
2. Choose an adoption mode:
   - copy files into the repo when you want the simplest local contract
   - use a submodule when you want to track SpecRail separately
   - use a package or generated overlay only after the copied workflow is stable
3. Add or merge the `AGENTS.md` entrypoint above.
4. Run `python3 checks/check_workflow.py --repo .`.
5. Run `python3 checks/check_workflow.py --repo . --all-specs` after adding spec packets.
6. Add the GitHub Action from `.github/workflows/workflow-check.yml`.
7. Start with dry-run checks only.
8. Add label/comment automation only after maintainers trust the signal.

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
