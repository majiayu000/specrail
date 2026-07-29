# Tech Spec

## Linked Issue

GH-62

## Product Spec

`specs/GH62/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Owns spec coverage + candidate selection; no ratio rule | Ratio gate contract |
| checkpoint schema | `schemas/runtime_checkpoint.schema.json` | No per-tranche PR-type counters | Structural contract |
| runtime gate | `checks/runtime_ledger_gate.py` | Validates checkpoint items | Enforcement point |
| checkpoint template | `templates/tranche_checkpoint.md` | Human handoff format | Count lines |
| implx | `skills/implx/SKILL.md` | Delegates queue policy | Cross-reference only |

## Proposed Design

1. Checkpoint additions: `tranche_mix` object with `spec_pr_count`,
   `impl_pr_count`, `consecutive_spec_only`, `spec_only_declaration`
   (optional: quoted user confirmation + scope + marker). Each item record
   gains `pr_kind` (`spec` | `impl` | `mixed_impl`).
2. `checks/runtime_ledger_gate.py`: recompute the streak from ordered item
   records; if any point exceeds 3 consecutive `spec` PRs without an active
   `spec_only_declaration`, report a blocking violation. Also cross-check
   that `tranche_mix` counters match the item records (no self-reported
   inflation).
3. Skill text: `specrail-implement-queue` gains a "Spec/impl mix gate"
   section: streak rule, declaration flow (ask before exceeding the cap,
   record quoted confirmation), reporting rule (never present spec count as
   implementation progress), and the `mixed_impl` classification rule
   (production code present → counts as impl).
4. `templates/tranche_checkpoint.md` gains mix-count and declaration lines.
5. Fixtures: undeclared 4-streak (fail), declared spec-only tranche (pass),
   counter/item mismatch (fail), interleaved tranche (pass).

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `tranche_mix` fields + template | schema instance test |
| P2 | streak recomputation in gate | undeclared 4-streak fixture fails |
| P3 | declaration record requirement | declared fixture passes |
| P4 | counter/item cross-check | mismatch fixture fails |
| P5 | streak semantics in gate | blocked-items fixture keeps streak |

## Data Flow

Orchestrator classifies each created PR (`pr_kind`) and appends it to the
checkpoint item list; counters derive from items. Gate reads checkpoint JSON
locally and recomputes; no network calls. Declaration is quoted user text
verified by humans, presence/scope verified by the gate.

## Alternatives Considered

- Percentage-based ratio (e.g. >=25% impl per tranche): rejected — ratios
  are gameable by tranche sizing; a consecutive-streak cap is simpler and
  matches the audited failure shape (a long uninterrupted spec run).
- Blocking spec PR creation outright after the cap: rejected — sometimes the
  queue really is spec-only; the declaration path keeps that honest instead
  of impossible.
- Enforcing in `checks/pr_gate.py` per PR: rejected — the signal is
  tranche-level sequence, which lives in the runtime checkpoint.

## Risks

- Security: none.
- Compatibility: additive checkpoint fields; older checkpoints exempt via
  contract-version keying.
- Performance: negligible.
- Maintenance: `pr_kind` classification of mixed PRs needs a crisp rule
  (production code present → impl); documented in one place, the skill.

## Test Plan

- [ ] Unit tests: streak recomputation matrix (streaks, declarations,
      resets, mismatch detection).
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: encode the audited #395–#418 tranche shape as a
      fixture and confirm it fails without a declaration.

## Rollback Plan

Revert gate rule, then schema/template fields, then skill text in separate
commits. No persisted-state migration.
