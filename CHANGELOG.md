# Changelog

## Unreleased

### Added

- Two-mode implx authorization: `automation_policy.auth_mode` (`auto` default,
  `review` opt-in) with an `auth_modes` block declaring per-mode waived human
  gates and mode-scoped forbidden actions; `merge`/`final_approval` are now
  forbidden only in `review` mode. `check_workflow.py` validates the mode
  value, both mode definitions, and that waived gates reference declared
  `required_human_gates`. Workflow pack version bumped to 0.3.0.
- Worktree-safe merge path (GH-63): merges run from a neutral cwd with an
  API fallback for locally checked-out branches; merge records require
  `merge_path` and remote confirmation before an outcome may be reported.
- Spec/impl mix gate (GH-62): checkpoint items record `pr_kind`; more than 3
  consecutive spec-only PRs block without a quoted `spec_only_declaration`,
  and `tranche_mix` counters are cross-checked against item records.
- Reviewer lane resume and re-review cap (GH-61): review results record
  `review_round`/`review_mode`; full reviews past round 2 require a quoted
  human request, `diff_only` requires the prior `base_head_sha`, and
  resumed/diff-only rounds require a `prior_findings` checklist.
- Bounded tranche hard stop (GH-60): checkpoint_version 2 drain checkpoints
  must declare a `budget` (compaction and/or item-cap basis); over-budget
  continuation without a recorded `budget_override` is blocked and
  `stop_reason: budget_exhausted` with a resume prompt is a passing terminal.
- Reviewer-lane failure gate (GH-59): checkpoint items record `lane_failures`
  and must downgrade to blocked/needs_human or retry with a new independent
  lane; `review_source` is required merge evidence and unauthorized
  self-review merges are blocked.
- Read-only GitHub issue evidence adapter for `route_gate.py`.
- Advisory review JSON gate with diff-line validation.
- All-spec packet validation via `checks/check_workflow.py --all-specs`.
- Trusted issue state metadata with `state_source` and `state_trusted`.
- Review artifact validation for body headings, multi-line ranges, and
  suggestion blocks.
- Stronger product and tech spec templates based on behavior invariants,
  codebase context, and product-to-test mapping.
- Focused SpecRail route skills pinned by `skills-lock.json`.
- SpecRail implementation queue skill for approved-spec issue queues with
  optional threads orchestration.
- `implx` shortcut skill for SpecRail-backed implementation queues.
- Dry-run-first local Codex skill installer for explicitly requested installs.
- Autonomous SpecRail mode guidance for complex unadopted repos.
- Agent-facing `specrail-install` skill for setup, install, update, and adoption
  routing.
- Deterministic gate fixture corpus under `examples/fixtures/`.
- Runtime checkpoint schema instance validation and a documented contract
  authority split between schema structure and gate behavior.
- PR gate evidence now records serial gate-query completion/head SHA fields and
  rejects stale or post-merge gate ordering evidence.
- PR gate review-thread evidence now requires resolver attribution and rejects
  implementer/orchestrator-resolved reviewer threads.
- PR and runtime gates now record review source and reviewer-lane failures,
  blocking silent self-review substitution unless fresh scoped authorization is
  present.

## v0.2.1 - 2026-06-26

### Added

- Adoption matrix documentation and machine-readable fixture for the current
  `rclean`, `litellm-rs`, and `Claude-Code-Monitor` / `claude-hub` pilot
  evidence.
- Evaluator checks that validate required adoption pilot IDs and SpecRail-local
  evidence paths.

## v0.2.0 - 2026-06-25

### Added

- Local workflow evaluator and evaluation result schema for checking
  issue/spec/PR artifact quality against the SpecRail contract.
- rclean pilot example showing a repository smoke test of the SpecRail flow.
- Offline PR merge gate evaluator for head SHA, CI, review threads, merge state,
  linked issue, and human merge authorization evidence.
- Read-only GitHub PR evidence adapter that converts `gh` PR metadata and
  review-thread GraphQL output into `checks/pr_gate.py` evidence JSON.

## v0.1.0 - 2026-06-23

Initial public release of SpecRail as a portable workflow pack for
agent-assisted repository operations.

### Added

- Issue/spec/PR state machine and label taxonomy.
- Product and tech spec templates.
- Agent-first and human-final review guides.
- Security disclosure and maintainer escalation policies.
- JSON schemas for flow manifests, issue triage, spec packets, PR review gates,
  and workflow runs.
- Deterministic pack validator.
- English and zh-CN human-facing templates.
- Codex-compatible `specrail-workflow` skill.
