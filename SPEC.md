# SpecRail v0.4 Specification

## Problem

AI-assisted implementation is cheap, but a workflow that mirrors GitHub into
local ledgers, authorization tiers, and repeated review artifacts creates more
issues and PRs than it resolves. SpecRail provides a small deterministic
contract whose verification depth follows risk.

## Scope

This pack defines:

- `fastlane`, `standard`, and `heavy` verification profiles
- eight Issue states and outcome labels
- optional product/tech/task spec packets
- compact review and PR gates
- deterministic workflow checks
- human-final approval, merge, security, and release boundaries

## Non-Goals

- Building a hosted control plane or a durable local runtime.
- Replacing GitHub Issues, pull requests, reviews, branches, or CI.
- Granting agents final approval, force-push, merge, permission, or public
  security-disclosure authority.
- Migrating old runtime checkpoint, Goal, tier, or review-round artifacts.

## Verification Profiles

- `fastlane`: small mechanical, documentation, or test fixes. Requires a linked
  Issue, focused diff, project tests, one review, and a human merge boundary.
- `standard`: ordinary feature/fix work. Requires a linked Issue, a testable
  plan, project tests, one full review, and at most one diff-only review after
  P0/P1 fixes.
- `heavy`: architecture, public contracts, migrations, auth, payments, secrets,
  permissions, or configured sensitive paths. Requires a complete durable spec
  packet, independent review, security evidence bound to an exact
  maintainer-supplied approved revision, and explicit current-invocation human
  merge authorization. The collector cannot mint the approved revision; any
  product/tech/tasks drift fails closed.

Sensitive classification always selects `heavy`.
The canonical profile configuration fixes `requires_independent_review`:
fastlane is false; standard and heavy are true. Noncanonical overrides fail
workflow validation.

## Workflow Model

```text
new_issue -> needs_info | ready_to_spec | ready_to_implement | parked
needs_info -> ready_to_spec | ready_to_implement | parked
ready_to_spec -> ready_to_implement | parked
ready_to_implement -> in_progress | parked
in_progress -> review | parked
review -> in_progress | done | parked
parked -> ready_to_spec | ready_to_implement
done -> terminal
```

`duplicate`, `abandoned`, and `security_private` are outcome labels, not Issue
states. CI, review, and merge readiness are PR evidence.

## Review And PR Gates

Review contract v3 permits one full round and, only after P0/P1 fixes, one
diff-only round bound to the prior full artifact. Round 2 carries every prior
unresolved P0/P1 finding forward. Current unresolved P0/P1 blocks; P2/P3 remain
follow-ups on the current Issue/PR; outdated hosted findings do not block
current head.

The PR gate evaluates linked work, exact current head, changed files, CI,
compact review, clean merge state, profile, sensitive classification, and
current heavy authorization. Its result is advisory and never approves or
merges.

## Durable Truth And Resume

GitHub Issues, labels, pull requests, reviews, branches, and CI are durable
truth. An optional local handoff cursor may contain only `completed`, `pending`,
`blocked`, `artifact_refs`, and `resume_action`. It has no schema, does not
participate in any gate, and must be refreshed from GitHub on resume.

## Verification

- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 -m pytest -q`
- `python3 checks/skill_size_gate.py --repo . --json`
- `python3 tools/install_codex_skills.py --repo . --check-installed` for a
  read-only local installation integrity check

Core pack limits are 18 `checks/*.py` modules, 8 JSON schemas, 200 lines for the
queue skill, 60 lines for implx, and three files/12 KiB for fastlane startup.
