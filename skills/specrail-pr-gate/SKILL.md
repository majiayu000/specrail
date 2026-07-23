---
name: specrail-pr-gate
description: Use before reporting a SpecRail PR as merge-ready. Collects read-only PR evidence, runs the offline PR gate, checks linked work, current head SHA, CI, review decision, review threads, merge state, and human merge authorization without merging. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail PR Gate

Use this skill before saying a PR is merge-ready.

## Steps

1. Collect current PR evidence. Prefer the read-only adapter when available:

```sh
python3 checks/github_pr_evidence.py --github-repo <owner/repo> --pr <pr-number> --review-source independent_lane --json > <evidence.json>
```

For a partial slice with a standalone `Refs #<issue-number>` directive, pass
the expected issue explicitly:

```sh
python3 checks/github_pr_evidence.py --github-repo <owner/repo> --pr <pr-number> --issue <issue-number> --review-source independent_lane --json > <evidence.json>
```

The expected issue must exist in the same repository and remain open. Other
closing references may coexist; the adapter records all of them without
redirecting the explicit target. A verified `partial` relation satisfies only
linked-work evidence and never authorizes final completion or issue closure.

2. Run the offline gate:

```sh
python3 checks/pr_gate.py --repo . --evidence <evidence.json> --json
```

3. Confirm evidence includes linked issue and, for new adapter output, a
   self-consistent `issue_reference`; also confirm current PR head SHA, gate-query
   completion timestamp, gate-query head SHA, CI/check rollup, review decision,
   review source, lane failures, review-thread resolution, merge state, and the
   merge authorization: either human merge authorization
   (`human_authorization.actor`/`source`) or a GH-143 tier-scoped
   authorization (`authorization_tier: standard_auto` with `pr_tier`
   fastlane/standard, `pr_tier_evidence` with changed-line count and touched
   paths, a non-sensitive classification, AND a reference to independent
   substantiation: a `ci_tier_check` artifact reference or a
   `tier_attestation_ref` backed by `review_evidence` with `review_source`
   `independent_lane`). Heavy or sensitive PRs, missing tier evidence, or a
   missing substantiation reference keep the human-authorization requirement
   (`needs_human`); self-reported tier evidence alone is never sufficient.
   The runtime ledger gate additionally loads and verifies the artifacts
   themselves: the review artifact must validate against
   `schemas/review_result.schema.json`, the `tier_attestation` counts only
   when the artifact's own `review_source` is `independent_lane` and the
   item is not `self_review`, and a `self_review` item can never qualify for
   standard_auto.

   For enforcement-sensitive evidence, also confirm the route-specific approval
   contract. `sensitive_route: approved_spec` requires `approved_spec` evidence.
   `sensitive_route: spec_revision` is limited to the linked issue's registered
   spec packet and requires a closed `spec_approval` object binding the trusted
   `spec_approved` lifecycle state, an exact-head maintainer GitHub approval, the
   normalized artifact paths, and their content digest. Mixed, partial, stale-head,
   or route-mismatched approval evidence is blocked; `spec_review` is never an
   approval state.

   When handing a sensitive item to the runtime ledger, preserve the selected
   `sensitive_route`. The `approved_spec` route references
   `approved_spec_evidence`; the `spec_revision` route references the same local,
   machine-readable `spec_approval_evidence` used for exact-head validation.
4. Interpret decisions precisely:
   - `allowed`: evidence satisfies the local merge-readiness policy.
   - `needs_human`: deterministic evidence passed, but a human gate is missing.
   - `blocked`: do not merge.
5. Report the evidence file path, decision, blockers, and stale or missing data.

## Serial Gate Ordering

The PR gate query must complete before any merge command, API call, or merge
lane is dispatched. Do not issue the GraphQL review-thread query, PR evidence
collection, `pr_gate.py`, and merge command in the same parallel tool batch or
parallel threads lane.

Required evidence:

- `gate_query_completed_at`: when the current gate query finished.
- `gate_query_head_sha`: the head SHA observed by that gate query.
- `review_source`: `independent_lane` for a real reviewer/merge-reviewer lane,
  or `self_review` when a lane failure was reported and self-review was
  explicitly authorized.
- `review_execution`: `local` for the primary exact-head reviewer artifact.
  `hosted` reviews, including GitHub `@codex review`, are supplemental only and
  cannot satisfy the primary review gate.
- `lane_failures`: an array, empty when no reviewer lane failed.
- `merge_dispatched_at` and `merge_head_sha` when auditing a merge record after
  dispatch.

If `review_source` is `self_review`, evidence must include
`self_review_authorization` with actor, source, and scope from the current
conversation after the lane failure was reported. General queue-drain or merge
authorization does not satisfy this self-review exception.

GitHub exposes `resolvedBy` for review threads, but not the SpecRail lane role.
When resolved threads exist, pass lane-roster evidence through
`--resolver-role-map` so resolver logins can be mapped to `resolver_role`.
The adapter records `resolver_role_source: explicit_map` for this bridge.
`resolvedBy` is the GitHub credential login and need not equal the local review
artifact's `producer_identity`; the gate instead requires the mapped lane,
current/reusable terminal re-review artifact, and manifest producer to agree.
Every successor resolver requires this explicit mapping, even when its
`resolvedBy` login happens to equal the local producer identity. Global
resolver-login mappings must be unique case-insensitively; use
`thread_resolver_roles` to disambiguate a shared login across lanes.
For a hosted root reviewer followed by local successor lanes, the manifest
lineage must end at the exact GraphQL `original_author`; missing or mismatched
external roots fail closed. If that root is intentionally external to the
manifest roster, the resolver mapping must include `external_root` with the
exact author and `review_execution: hosted`. A mapped root lane using a shared
credential still needs its current terminal artifact and exact lane producer.

If the PR head changes, new review activity appears, CI changes, or merge is
deferred long enough that the evidence may be stale, collect fresh PR evidence
and rerun `pr_gate.py` before merging.

An empty `checks` array blocks the gate. It stays blocked unless the evidence
carries a `checks_unavailable` declaration proving hosted CI cannot run for this
PR at all, which today means one case: the base ref is outside the repository's
`pull_request` trigger filter. The declaration is closed and fail-closed —
`reason: hosted_ci_not_triggered_for_base`, `base_ref` and `default_base_ref`
that match the evidence and differ from each other, `workflow_trigger_evidence`
quoting the trigger, a non-empty `local_verification` command list, and
`verified: true`. Any missing, unknown, or inconsistent field keeps the original
missing-`checks` outcome. On acceptance the gate emits a satisfied entry
prefixed `degraded:`; report it as a downgrade, never as passing CI. Prefer
fixing the repository's workflow trigger over declaring the downgrade.

## Boundaries

- Do not merge from this skill.
- Do not declare `checks_unavailable` for pending, failed, or not-yet-triggered
  CI; it covers only structurally impossible hosted checks.
- Do not dispatch gate queries and merge in parallel.
- Do not treat green CI alone as merge readiness.
- Do not substitute a hosted bot review for a local CLI/native reviewer lane.
- Do not ignore unresolved review threads.
- Do not replace maintainer final review or human merge authorization.

## Rejection Persistence And Retry

When a gate command in this skill (`checks/route_gate.py`,
`checks/review_json_gate.py`, or `checks/pr_gate.py`) rejects with a decision
other than `allowed`, the caller persists the gate's JSON output to
`.specrail/runtime/rejections/<gate>-<issue|pr>.json` (create the directory if
missing). This write is orchestrator behavior; the gate itself stays
read-only. Use the `rejection_items[]` list to fix every defect in a single
round instead of guessing one item per retry.

On the next retry of the same gate for the same issue or PR, pass
`--prior-rejection .specrail/runtime/rejections/<gate>-<issue|pr>.json`. If
the new output contains a `repeat_rejection` section, the same item was
rejected verbatim twice: stop retrying and report the contract violation to a
human instead of starting another round.
