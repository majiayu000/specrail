# Changelog

## Unreleased

### Changed

- Queue review now performs one full review across the selected PR set, one
  repair, and one diff-only re-review. Heavy or explicitly requested hosted
  feedback uses one fixed 15-minute collection window, and the queue stops for
  a cost report when the first three PRs all fail to become merge-ready.
- Verification is risk-weighted: fastlane work keeps focused tests,
  repository-required CI, one independent exact-head review, and clean merge
  state without structured review manifests, hosted review, GraphQL thread
  collection, PR-gate artifacts, or runtime checkpoints. Standard and heavy
  work retain progressively stronger gates.
- Runtime checkpoints are now closed milestone resume cursors rather than a
  second workflow database. The former budget, Goal, telemetry, CI, review,
  thread, merge, authorization, PR-gate, branch, and worktree mirrors and
  their legacy schemas, fixtures, and validators were removed. The incompatible
  cursor format is version 4, and interrupted milestones may hand off in the
  explicit `paused` state.

### Added

- Local-primary review provenance (GH-162): terminal review artifacts now
  distinguish `review_execution: local | hosted`; offline PR and runtime
  ledger gates reject hosted reviews as primary evidence while keeping GitHub
  `@codex review` available as explicitly supplemental review.

- Spec depth audit tool (GH-93): read-only `tools/spec_depth_audit.py` measures
  per-spec invariant count, EARS conditional ratio, boundary-category coverage,
  and tech.md path:line anchors; supports `--repo` and repeatable `--spec-dir`
  for out-of-repo A/B comparison. Docstring records the 2026-07-13 baseline
  (60% of legacy specs at exactly 5 invariants, 28/30 with zero anchors). No
  gate integration; depth gating remains a Phase 2 item.
- Configured spec packet paths (GH-91): all-spec discovery, GitHub issue
  evidence, and route-gate verification commands now honor the artifact
  templates in `workflow.yaml`; invalid or repository-escaping packet
  templates fail closed instead of silently falling back to `specs/`. Pack
  validation now scopes schema/template checks to SpecRail-owned assets so
  consumer repository files can coexist in the same directories.
- Two-mode implx authorization: plain `implx` defaults to `review` mode, while
  explicit `implx auto` selects auto mode. `automation_policy.auth_mode` and
  the `auth_modes` block declare per-mode waived human gates and mode-scoped
  forbidden actions; `merge`/`final_approval` are forbidden in `review` mode.
  The persisted workflow value must remain `review`; repository configuration
  cannot authorize auto mode. `check_workflow.py` validates that baseline, both
  mode definitions, and that waived gates reference declared
  `required_human_gates`. Workflow pack version bumped to 0.3.0.
- Verified partial issue-reference evidence (GH-88): the read-only PR adapter
  accepts an explicit `--issue`, validates a standalone `Refs #N` against the
  live open issue, preserves coexisting closing references, and emits a
  structured relation that the offline PR gate checks without granting closure
  or final-completion semantics.
- Deep spec authoring method (GH-86): `specrail-write-product-spec` gains a
  length heuristic (with `complexity: trivial` opt-out), a 10-category
  boundary checklist ("covered: B-xxx or N/A + reason"), a worked example at
  target density, and stable append-only `B-xxx` invariant IDs;
  `specrail-write-tech-spec` gains verified `path:line` anchor discipline and
  a full-coverage Product-to-Test mapping rule (no orphan invariants, no
  TBD); `specrail-plan-tasks` requires every product invariant in the task
  coverage union. All six locale templates are updated to match; task lines
  carry `Covers: B-xxx`. No new gate logic (depth gating is a separate
  follow-up).
- Worktree-safe merge path (GH-63): merges run from a neutral cwd with an
  API fallback for locally checked-out branches; merge records require
  `merge_path` and remote confirmation before an outcome may be reported.
- Spec/impl mix guidance (GH-62): queue artifacts record `pr_kind`; more than
  3 consecutive spec-only PRs block without an explicitly confirmed spec-only
  phase.
- Reviewer lane resume and re-review cap (GH-61): review results record
  `review_round`/`review_mode`; full reviews past round 2 require a quoted
  human request, `diff_only` requires the prior `base_head_sha`, and
  resumed/diff-only rounds require a `prior_findings` checklist.
- Reviewer-lane failure evidence (GH-59): PR evidence must downgrade to
  blocked/needs_human or retry with a new independent lane; unauthorized
  self-review remains blocked.
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
- PR gates record review source and reviewer-lane failures, blocking silent
  self-review substitution unless fresh scoped authorization is present.

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
