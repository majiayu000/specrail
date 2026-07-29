# Product Spec

## Linked Issue

GH-62
status: legacy

## User Problem

A drain tranche can flood the repo with spec-only PRs while doing almost no
implementation, and the user only finds out by challenging the agent. Audit
evidence: one loom tranche produced ~24 PRs (#395–#418) of which exactly one
(#418) was a real implementation; the imbalance surfaced only when the user
asked "你可以merge 有做impl吗?" (see GH-62 issue body for the session-log
quote). Nothing in the queue contract forces implementation/spec interleaving
or honest ratio reporting.

## Goals

- Gate the spec/impl mix inside a drain tranche: after N consecutive
  spec-only PRs (default N=3), the next item must be an implementation PR.
- Provide an explicit alternative: declare a "spec-only tranche" to the user
  and get confirmation before continuing past the cap.
- Make the per-tranche spec/impl counts part of the checkpoint/report so the
  ratio is always visible.

## Non-Goals

- No judgment that spec PRs are bad; SpecRail is spec-first by design. The
  gate targets undisclosed imbalance, not spec work.
- No global repository-level ratio quota across tranches.
- No reclassification of what counts as a spec packet (existing spec-packet
  definition stands).

## Behavior Invariants

1. Every tranche checkpoint/report records `spec_pr_count`, `impl_pr_count`,
   and the current consecutive spec-only streak.
2. After 3 consecutive spec-only PRs within a tranche, creating another
   spec-only PR is a violation unless a declared spec-only tranche is in
   effect.
3. A spec-only tranche declaration must be made to the user before (or at the
   moment) the cap would be exceeded, and the user's confirmation must be
   recorded (quoted text + scope) in the checkpoint.
4. Progress reporting must not present spec PR counts as implementation
   progress; the report separates the two counts.
5. Items that are blocked from implementation (e.g. waiting on human input)
   do not reset the streak by themselves; only an implementation PR or a
   recorded declaration does.

## Acceptance Criteria

- [ ] `skills/specrail-implement-queue/SKILL.md` contains the ratio gate:
      consecutive spec-only cap (default 3) + the spec-only-tranche
      declaration path.
- [ ] Runtime checkpoint / tranche report includes `spec_pr_count`,
      `impl_pr_count`, streak, and optional declaration record;
      `checks/runtime_ledger_gate.py` flags an over-cap undeclared tranche.
- [ ] Fixture: 4 consecutive spec-only PRs without declaration is rejected;
      a declared spec-only tranche with the same counts passes.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- Queue genuinely contains only ready_to_spec items (nothing is
  ready_to_implement): this is exactly the declared spec-only tranche case;
  the declaration states that fact and the gate passes.
- Mixed PR (spec files + implementation in one PR): counts as implementation
  for the ratio if it contains non-spec production changes; the
  one-issue-per-PR rule still applies.
- Tranche boundary resets: the streak counter is per tranche; a new tranche
  starts a new streak but inherits the obligation to report counts.
- User pre-authorizes spec-only work in the initial prompt: record it as the
  declaration; no second confirmation needed.

## Rollout Notes

Additive checkpoint fields. Existing tranche reports gain two count lines.
CHANGELOG notes the new violation class; `AGENT_USAGE.md` mentions the
declaration flow so users know why an agent may pause to ask.
