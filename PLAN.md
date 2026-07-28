# Plan

SpecRail is an agent-first workflow contract. It is not trying to be another
human-facing project-management guide. The central question is:

```text
What should a code agent do next, and what evidence proves it may do that?
```

## Current Position

SpecRail v0.4 is a portable, profile-based workflow pack:

- `fastlane`, `standard`, and `heavy` verification profiles
- eight Issue states backed by GitHub truth
- compact route, review, and PR gates
- 18 core checkers and 8 durable schemas
- deterministic validation and localized templates

The default flow intentionally avoids a second runtime state machine. Only
heavy work requires a full durable spec packet. Repeated real use should decide
whether any advisory check deserves promotion.

## Design Principles

1. Repository configuration owns policy. Code interprets policy.
2. Agents can draft and diagnose, but humans own final gates.
3. Missing evidence is never silent success.
4. Stable machine IDs stay in English across locales.
5. Human-facing text follows the selected locale.
6. Deterministic checks come before LLM automation.
7. Automation starts in dry-run or advisory mode.
8. Verification depth follows risk; only heavy work requires a full spec packet.
9. Adoption, installation, remote writes, approval, and merge require explicit
   human authorization.

## Why The Skill Exists

Templates define output shape. They do not tell an agent when to search, which
state transition is allowed, how to choose locale, or which values must not be
translated.

`skills/specrail-workflow/SKILL.md` exists to make those operating rules explicit
for Codex-style agents. It is not perfect or final. It is a v0.4 execution guide
that should be tested against real tasks and then tightened.

## Roadmap

### Phase 1: Manual Contract

- Keep templates and schemas small.
- Use `AGENT_USAGE.md` and `skills/specrail-workflow/SKILL.md` for agent runs.
- Validate the pack with `checks/check_workflow.py`.
- Record failures as changes to templates, docs, checks, or skill instructions.

### Phase 2: Configurable Evaluator

Implement and harden an offline evaluator that reads repo config and evidence,
then returns:

- `allowed`
- `warn`
- `needs_human`
- `blocked`

The first local route gate lives at `checks/route_gate.py`. It is intentionally
read-only and local-evidence based. Next hardening steps are richer artifact
validation, localized display messages, and GitHub evidence adapters. JSON keys
and stable IDs must stay language-independent.

### Phase 3: Evidence Adapters

Add adapters that collect evidence from GitHub:

- issue labels
- linked PRs
- CI status
- compact current-head review
- changed-file sensitivity

Adapters should produce evidence JSON. They should not own policy.

The merge-readiness evaluator is `checks/pr_gate.py`. It consumes local evidence
JSON and checks linked work, current head, CI, compact review, merge state,
profile, sensitive classification, and heavy authorization.

The post-merge closure evaluator is `checks/closure_audit.py`. It emits an
advisory result only. It performs no GitHub writes and never creates follow-up
issues.

The issue evidence adapter is `checks/github_issue_evidence.py`. It uses
`gh issue view` to collect issue state, labels, title, URL, and state trust
metadata for `checks/route_gate.py`. Label state is trusted; requester-editable
body hints never grant readiness. The adapter remains read-only.

The PR evidence adapter is `checks/github_pr_evidence.py`. It uses `gh pr view`
to collect current merge-readiness evidence and prints JSON for
`checks/pr_gate.py`. It does not write labels, comments, reviews, branches, or
merges.

The review artifact gate is `checks/review_json_gate.py`. It validates advisory
compact review JSON against a unified diff, enforces at most one full plus one
diff-only pass, blocks current P0/P1, and keeps P2/P3 as follow-ups.

### Phase 4: Agent Installation

Make SpecRail easy to give to agents:

- copy pack into a repo
- use `skills/specrail-install/SKILL.md` as the agent-facing setup entrypoint
- reference `skills/specrail-workflow` from the repo
- optionally run `tools/install_codex_skills.py` for explicit local Codex skill
  installation
- keep repo-distributed route skills pinned in `skills-lock.json`
- optionally set `presentation.default_locale: zh-CN`
- run deterministic checks before and after agent work
- use `--check-installed` to diagnose local skill drift without writing
- use optional `integrations/threads.md` only when threads are explicitly
  requested or delegated

### Phase 5: Automation

Only after manual validation on real tasks:

- comment-only checks
- label suggestions
- PR gate comments
- stale workflow reports

Do not add automatic merge, final approval, or public security-disclosure
automation.

## Success Criteria

SpecRail becomes useful when an agent can join a new repo, read the pack, and
produce issue/spec/PR artifacts that maintainers can review without first
explaining the workflow in chat.

SpecRail becomes trustworthy when repeated real runs produce fewer process
mistakes, not just nicer templates.

## Optional Integrations

Integrations are advisory execution designs, not required dependencies.
They let SpecRail describe how an agent should combine the core contract with a
separate orchestration skill.

The first integration is `integrations/threads.md`. It keeps the boundary
explicit:

- SpecRail owns policy, artifacts, locale, human gates, and deterministic checks.
- Threads owns temporary disjoint lane assignment and bounded results.
- Thread state never replaces current GitHub evidence.
