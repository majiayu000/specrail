# Changelog

## Unreleased

### Breaking changes

- SpecRail workflow 0.4 replaces the governance-heavy queue with three
  verification profiles (`fastlane`, `standard`, `heavy`), eight Issue states,
  one compact review contract, and one compact PR gate (GH-208).
- Old runtime checkpoint, Goal, lease, attempt-ledger, telemetry, tier,
  content-binding, and multi-round review artifacts are unsupported. Resume
  from current GitHub truth; an optional five-field cursor is non-gating.
- Core assets are capped at 18 checkers, 8 schemas, a 200-line queue skill, a
  60-line implx entrypoint, and a three-file/12 KiB fastlane startup set.

### Added

- Read-only `--check-installed` skill doctor reports every missing or drifted
  installed `SKILL.md` in one pass and gives explicit reinstall/restart
  guidance (GH-208).

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
