---
name: specrail-review-pr
description: Use when performing an advisory SpecRail PR review. Checks linked issue/spec evidence, route gates, verification evidence, review-thread state, human-gate preservation, and implementation quality without granting final approval or merging. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Review PR

Use this skill for the `review_pr` route.

## Steps

1. Read the PR, linked issue, product spec, tech spec, task plan, and local diff.
2. Confirm the PR has current evidence for linked work, verification, CI, review
   state, and review threads when available.
3. Run the review route gate. It is mandatory when `checks/route_gate.py`
   exists; see Gate Availability when it does not.

```sh
python3 checks/route_gate.py --repo . --route review_pr --issue <issue-number> --pr <pr-number> --state impl_pr_open --json
```

4. Inspect for behavioral regressions, missing acceptance coverage, test gaps,
   silent degradation, security risk, and human-gate bypasses.
5. Lead with findings ordered by severity and cite exact files or lines.
6. When producing a review artifact, use a top-level body with `## Summary` and
   `## Verdict`, keep inline comments bound to real diff `path` / `line` /
   `side` values, and only add `start_line` / `start_side` together for an
   inclusive diff range. Suggested changes must be non-empty and appear only on
   RIGHT-side comments, either through a `suggestion` field, a fenced
   `suggestion` block, or both. Record `review_execution: local` for the
   terminal artifact produced by the local CLI/native reviewer lane. A GitHub
   hosted `@codex review` may be supplemental, but if recorded separately it
   uses `review_execution: hosted` and never replaces the local primary
   artifact.
7. Validate the review artifact against the diff. This is mandatory whenever a
   review artifact was produced in step 6 and `checks/review_json_gate.py`
   exists; an unvalidated artifact must not be published.

```sh
python3 checks/review_json_gate.py --repo . --review artifacts/review/pr-<pr-number>.json --diff <patch> --json
```

8. If merge readiness is requested, route to
   `skills/specrail-pr-gate/SKILL.md`.

## Gate Availability

The `review_pr` route depends on the repository's gate scripts. Decide before
step 3, and never let a missing or failing gate pass as a completed check.

| Condition | Required action |
|---|---|
| `checks/route_gate.py` exists | Run it. Treat a non-`allowed` decision per Rejection Persistence And Retry. |
| `checks/route_gate.py` is absent | Stop the `review_pr` route. Report that the repository is not SpecRail-instrumented and that a generic code review should be used instead. Do not run the gate command speculatively. |
| The gate command errors (missing file, missing interpreter, non-zero exit that is not a gate decision) | Treat as absent, not as `allowed`. Report the error verbatim. |

If a human explicitly asks to continue without a gate, the review may proceed
only as an explicitly degraded pass:

- Record `gate_status: "unavailable"` and put the quoted human authorization in
  `gate_authorization` in the review result JSON.
- State in `## Summary` that no SpecRail gate validated this review and include
  the stable marker `SpecRail gate status: unavailable`.
- Do not describe the result as SpecRail-gated, verified, or merge-ready.

## Review Rounds And Modes

<!-- specrail-bounded-review-contract-v1:start -->
Bounded review contract (`manifest.version: 2`,
`round_policy: {name: "bounded_diff_v1", cap: 3}`):

- `rounds[]` is the source of truth. Each entry is the closed set
  `{artifact_id, review_round, review_mode, base_head_sha, head_sha, diff_sha256, escalation_authorization_id}`;
  the loader derives continuous rounds `1..N` from the artifact set.
- Round 1 may use `full`. Every `review_round >= 2` must use `review_mode:
  resumed | diff_only`, never `full`; `base_head_sha` must equal the previous
  round's `head_sha`, and the supplied bytes and `diff_sha256` must match the
  exact `git diff --no-ext-diff --binary <base_head_sha>..<head_sha> --` output.
- `prior_findings[]` is compact typed carry only:
  `{finding_id, source_artifact_id, status, evidence_pointer}` with
  `evidence_pointer.kind: thread | comment | artifact | commit`; do not replay
  historical finding prose. Carry every still-unresolved historical finding.
- Before every `review_round >= 4`, stop. Continue exactly once only with an
  external, role-mapped maintainer authorization whose `decision` is
  `continue_once` and whose id, PR, prior/target heads, and round match exactly.
- The over-cap `round_cap_escalation.unresolved_findings[]` must equal the full
  union of historical unresolved findings and current critical, important, or
  otherwise actionable findings; no finding may disappear or be invented.
- `auth_mode: auto` merge authorization and `human_full_review_request` do not
  authorize an over-cap review round and cannot replace that exact cap evidence.
<!-- specrail-bounded-review-contract-v1:end -->

## Thread Resolution Ownership

Reviewer lanes may resolve review threads only after re-checking that the
finding is fixed or no longer applies. A reviewer lane may resolve its own
thread, a successor reviewer lane may resolve after re-review, and a human
maintainer may resolve directly.

When a local reviewer uses a shared repository GitHub credential, record the
credential login through `--resolver-role-map`; do not rename the local
artifact `producer_identity` to impersonate that login. For hosted-review roots,
successor lane lineage must terminate at the exact hosted `original_author`,
and the resolving lane must provide a trusted terminal re-review artifact.
Every successor resolution requires an explicit resolver mapping. When one
GitHub login represents multiple lanes, use a thread-specific mapping instead
of duplicate global login entries. A hosted root omitted from the local roster
must be declared as `external_root` with the exact author and
`review_execution: hosted`; an untyped missing predecessor is not proof.

Implementation lanes and orchestrators must not call `resolveReviewThread` for
reviewer-lane findings. They may reply with context and push fixes, but the
resolution action stays with the reviewer or human.

## Boundaries

- Treat the review as advisory.
- Do not grant final approval.
- Do not present a review as gated when the gate was absent, skipped, or errored.
- Do not merge or mark human gates complete.
- Do not resolve reviewer-lane threads from an implementation or coordinator
  role.
- Do not disclose private security details publicly.

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
