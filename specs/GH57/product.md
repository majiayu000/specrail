# Product Spec

## Linked Issue

GH-57

## User Problem

The merge step and the merge-gate queries (GraphQL `reviewThreads`, pr_gate)
can be dispatched in parallel. When that happens the merge may succeed before
the gate result arrives, so a PR with unresolved review threads lands on main
and the substantive defects those threads describe ship silently. Audit
evidence: loom PR #474 was merged while 4 review threads were unresolved
because the review-thread query and the merge API call were issued in the same
parallel batch (see GH-57 issue body for session-log quotes). The merge gate
exists but its ordering is not part of the contract, so it can be bypassed by
accident.

## Goals

- Make gate-query-before-merge a serial ordering contract: merge may only be
  issued after a fresh, serially completed gate query returns zero unresolved
  threads and a passing pr_gate for the same head SHA.
- Make parallel dispatch of gate query and merge a detectable, blocking
  contract violation in the deterministic checks.
- Record enough ordering evidence (query completion, head SHA) that the gate
  can be audited after the fact.

## Non-Goals

- No change to what the gate checks (thread resolution semantics, CI truth);
  only when it must complete relative to merge.
- No runtime interception of GitHub API calls; enforcement stays in skill
  contract text plus deterministic evidence checks.
- No change to human merge-authorization requirements.

## Behavior Invariants

1. A merge action is only permitted after a gate query that (a) completed
   before the merge was dispatched, (b) returned zero unresolved review
   threads, (c) reported pr_gate pass, and (d) observed the same head SHA that
   the merge targets.
2. Dispatching a gate query and a merge in the same parallel tool batch or in
   concurrent lanes is a contract violation regardless of outcome.
3. If the PR head changes or new review activity occurs after the gate query,
   the query result is stale and must be re-run before merge.
4. pr_gate evidence records the gate-query completion marker and head SHA so
   the ordering is verifiable; evidence missing the ordering fields fails the
   gate.
5. A gate evidence record whose query timestamp/ordinal is later than the
   merge action is classified as a violation, not as a pass.

## Acceptance Criteria

- [ ] `skills/specrail-pr-gate/SKILL.md` and
      `skills/specrail-implement-queue/SKILL.md` state the serial ordering
      contract and explicitly forbid parallel gate-query + merge dispatch.
- [ ] The pr_gate evidence structure includes gate-query completion and head
      SHA fields; `checks/pr_gate.py` rejects records missing them.
- [ ] A negative fixture where gate evidence postdates the merge (or is absent)
      is rejected by the gate; a positive fixture with correct ordering passes.
- [ ] `python3 -m pytest -q tests/` and
      `python3 checks/check_workflow.py --repo . --all-specs` pass.

## Edge Cases

- Merge retried after a transient API failure: the original gate query remains
  valid only if head SHA and thread state are unchanged; otherwise re-query.
- Multiple PRs merged in one tranche: each merge needs its own fresh gate
  query; one query cannot cover several merges.
- Gate query succeeds but merge is deferred (waiting for authorization): the
  query must be re-validated if any review activity happened in between.

## Rollout Notes

Contract-text plus check change; no schema-breaking change to existing
checkpoint files is required, but pr_gate evidence gains required ordering
fields, so producers of pr_gate evidence must be updated together. CHANGELOG
should note the new required fields.
