# Changelog

## Unreleased

### Added

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
