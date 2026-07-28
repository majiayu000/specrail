# Agent Usage

SpecRail is primarily for code agents, not for human project management. Humans
own policy and final gates; agents use this repository to decide how to triage,
write specs, prepare PRs, review, and report handoffs without inventing process.

## What The Agent Should Load

Fastlane startup reads only `AGENTS.md`, `workflow.yaml`, and
`skills/implx/SKILL.md`. Standard/heavy load the focused route skill and only
the artifacts that profile requires. Templates, states, labels, and the skill
lock are loaded on demand instead of on every invocation.

If the consumer repository has no `AGENTS.md`, ask the maintainer to add a short
entrypoint or proceed from `AGENT_USAGE.md` only for the current task while
reporting that the repo is missing its agent entrypoint. Do not treat a missing
`AGENTS.md` as permission to skip repository policy.

The skill is an execution guide. The YAML files and templates are the workflow
contract. The agent should not treat the skill as final authority when it
conflicts with repository policy or human instructions.

Optional integration documents under `integrations/` are loaded only when the
task needs that execution model. They do not replace the core SpecRail contract.

For setup, installation, update, verification, or adoption requests, load
`skills/specrail-install/SKILL.md` first. Treat it as the agent-facing setup
entrypoint; command-line installers are deterministic helpers, not the primary
interface a human must memorize.

## Autonomous SpecRail Mode

Agents should switch complex work into SpecRail mode even when a repository has
not adopted the full pack. Good triggers include product-facing changes,
architecture changes, cross-module work, public API changes, workflow-policy
changes, PR merge-readiness checks, CI diagnosis with unclear ownership, or
ambiguous requests whose done-when is not yet testable.

SpecRail mode means search first, select a route and verification profile,
preserve human gates, and run deterministic verification. Heavy work requires
durable product/tech/task artifacts; fastlane and standard do not create
spec-only work by default.

If a repository has not adopted the pack, use that repository's existing
specs/plan/docs location to carry the route, spec, task plan, and verification
evidence. Do not silently copy the SpecRail pack into a repository, install
local skills, create remote issues or PRs, add labels, approve, merge, or bypass
maintainers unless the user explicitly asks for that action.

For small mechanical fixes, test-only changes, doc-only corrections, or
approved-spec work, direct implementation is still appropriate.

## Optional Local Skill Installation

Repository adoption does not require installing SpecRail skills into `$HOME`.
Agents must not run a local skill install with `--apply` unless a human
explicitly requests local Codex skill installation.

When local installation is explicitly requested, preview first:

```sh
python3 tools/install_codex_skills.py --repo .
```

Apply only after that explicit request:

```sh
python3 tools/install_codex_skills.py --repo . --apply
```

The installer validates `skills-lock.json`, writes only the locked skill
directories, and targets `$CODEX_HOME/skills` or `~/.codex/skills`. A running
agent session may need to restart before the installed skills are discoverable.
Check an existing installation without writing:

```sh
python3 tools/install_codex_skills.py --repo . --check-installed
```

Any missing or drifted skill is reported in one pass. Reinstall explicitly with
`--apply`, then restart Codex.

## Basic Agent Flow

1. Search existing issues and PRs before creating new work.
2. Identify the route:
   - `triage_issue`
   - `write_spec`
   - `implement`
   - `review_pr`
   - `fix_ci`
   - `draft_release_note`
3. Select `fastlane`, `standard`, or `heavy`. Auth, payments, secrets,
   permissions, migrations, and configured sensitive paths are always heavy.
4. Require a full product/tech/tasks packet for heavy. Fastlane and standard
   use a linked Issue plus the smallest testable plan.
5. Confirm the current state from durable repo state when possible.
6. Create or update the required artifact. For spec artifacts, use the
   configured `artifacts.product_spec`, `artifacts.tech_spec`, and
   `artifacts.task_plan` paths from `workflow.yaml`:
   - issue
   - configured product, tech, and task spec paths
   - PR body
   - review result
   - handoff
7. Run the local evaluator before taking the route action:

```sh
python3 checks/github_issue_evidence.py --repo . --github-repo OWNER/REPO --issue <issue-number> --json > issue-evidence.json
python3 checks/github_duplicate_evidence.py --github-repo OWNER/REPO --issue <issue-number> --json > duplicate-work-evidence.json
python3 checks/route_gate.py --repo . --route write_spec --issue <issue-number> \
  --evidence issue-evidence.json --mode required --json
python3 checks/route_gate.py --repo . --route implement --issue <issue-number> \
  --profile <fastlane|standard|heavy> --evidence issue-evidence.json \
  --duplicate-evidence duplicate-work-evidence.json --mode required --json
```

The duplicate-work adapter is read-only. It collects open PR and remote branch
evidence; duplicate results are advisory and should steer the agent to existing
ownership rather than create replacement work.
Continue only when the route decision is `allowed`.

8. Run deterministic checks before claiming completion:

```sh
python3 checks/check_workflow.py --repo .
python3 checks/check_workflow.py --repo . --all-specs
```

`--all-specs` discovers packets from `workflow.yaml`'s
`artifacts.spec_packet` template. The issue evidence adapter and route gate
render their spec paths from the same artifact configuration. For a single
packet, run the exact configured command returned by `route_gate.py` in
`verification_commands`.

9. Before reporting a PR as merge-ready, collect PR evidence and run:

```sh
python3 checks/github_pr_evidence.py \
  --github-repo OWNER/REPO \
  --pr <pr-number> \
  --profile <profile> \
  --gate-invocation-id <id> \
  --review <review.json> \
  --review-attestation <host-attestation.json> \
  --json > pr-evidence.json
python3 checks/pr_gate.py --repo . --evidence pr-evidence.json --json
```

The review JSON uses compact contract v3. Its `review_source` follows the
canonical profile policy: fastlane self-review; standard/heavy independent.
For standard/heavy, the trusted host/coordinator supplies the separate
head-and-invocation-bound `--review-attestation`; agents must not mint or edit
it. The raw current and embedded prior review JSON never contains the
attestation; round 2's single current attestation also binds the prior artifact
ID and head. Its `review_sha256` binds the complete canonical raw review JSON,
including the embedded prior review. Fastlane self-review omits the flag.
Round 1 is
full and binds the exact PR base-to-head diff with `base_head_sha` and
`diff_sha256`; round 2 is diff-only after P0/P1 fixes. P2/P3 are
non-blocking follow-ups, and outdated hosted findings do not block current
head. A round-2 artifact is valid only after an unresolved round-1 P0/P1; it
must embed the bound round-1 artifact as `prior_review` and carry every prior
unresolved P0/P1 finding forward.

For a partial implementation slice whose body contains a standalone
`Refs #<issue-number>` directive, bind the intended issue explicitly:

```sh
python3 checks/github_pr_evidence.py \
  --github-repo OWNER/REPO \
  --pr <pr-number> \
  --issue <issue-number> \
  --profile <profile> \
  --gate-invocation-id <id> \
  --review <review.json> \
  --review-attestation <host-attestation.json> \
  --json > pr-evidence.json
```

The adapter verifies that target against the live same-repository issue and
requires it to remain open. Other bounded closing references may coexist and
are retained in `issue_reference.closing_issue_numbers`; they do not redirect
the explicitly selected `linked_issue`. A verified `partial` relation satisfies
only the PR gate's linked-work requirement. It does not prove final-slice
completion and does not authorize issue closure.

The GitHub adapter is read-only and only reshapes `gh` output. The offline PR
gate checks linked work, current/query head, changed files, CI, compact review,
merge state, profile, sensitive classification, and current heavy
authorization. It never merges or writes remote state.

An optional handoff cursor may store only `completed`, `pending`, `blocked`,
`artifact_refs`, and `resume_action`. It has no schema or gate and never
replaces current GitHub truth.

Issue evidence includes `state_source` and `state_trusted`. Label-derived state
is trusted readiness evidence. Body-hint state is useful context, but it is not
a maintainer readiness label and human-gated routes must not treat it as direct
permission.

10. Before treating an agent review artifact as publishable evidence, validate
    it against the diff:

```sh
python3 checks/review_json_gate.py --repo . \
  --review artifacts/review/pr-<pr-number>.json --diff <patch> \
  --review-attestation <host-attestation.json> \
  --gate-invocation-id <current-id> --json
```

The review gate validates advisory review JSON and optional finding locations.
It does not approve, merge, or publish GitHub reviews. Review artifact bodies
must include `## Summary` and `## Verdict`. Each v3 finding uses `id`,
`severity`, `status`, and `summary`; optional `path` and `line` must be supplied
together, and optional `fix_paths` scopes a round-2 fix. The live GitHub
collector alone adds hosted `origin` and `outdated` provenance.

If `write_spec` is selected and no GitHub issue number is available, the agent
should search for an existing issue first. If none exists and GitHub workflow is
in scope, create or request a linked issue before writing the numbered spec
packet. A missing issue number is not permission to skip spec creation.

## Optional Threads Integration

Load `integrations/threads.md` only when the user requests subagents/threads or
a selected skill explicitly delegates disjoint lanes. Thread state is not
workflow evidence. SpecRail owns policy and human gates; threads only provide
temporary lane orchestration. If threads are unavailable, use the normal
single-agent flow without creating fallback artifacts.

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
- an optional threads integration design
- a Codex-compatible `specrail-workflow` router skill and focused route skills
- a Codex-compatible `specrail-install` setup skill for agent-facing installs
- `skills-lock.json` for repo-distributed SpecRail skills
- a deterministic pack validator
- a read-only GitHub issue evidence adapter
- a read-only GitHub PR evidence adapter
- a read-only duplicate-work evidence adapter and offline implementation
  duplicate-work gate
- an advisory review JSON gate
- an optional five-field, non-gating handoff cursor
- a local evaluator that returns `allowed`, `warn`, `needs_human`, or `blocked`
- an adoption matrix and fixture for real repo pilot evidence:
  `docs/ADOPTION_MATRIX.md` and `examples/adoptions/matrix.json`
- gate benchmark fixtures under `examples/fixtures/`

This is enough for an agent to follow the process more consistently than raw
README instructions.

## What Does Not Exist Yet

SpecRail does not yet provide:

- automatic issue label checks
- automatic template rendering commands
- automatic merge or final approval

Until those exist, agents should treat `checks/route_gate.py` as a local gate and
must report what they verified rather than claiming live GitHub workflow state
from assumptions.

## Human Gates

Agents may draft, propose, review, and diagnose. Agents must not:

- provide final approval
- merge without explicit authorization
- publish private security details
- change repository permissions
- bypass readiness labels or other human gates
