---
name: specrail-review-pr
description: Advisory review for a SpecRail PR. Validate the current head against linked work, produce the compact v3 review artifact, and preserve human approval and merge boundaries.
---

# SpecRail Review PR

Review only the current PR head. Do not approve, merge, close, or publish
security findings.

## Inputs

- repository and PR number;
- current 40-character head SHA;
- selected profile;
- exact full diff for round 1 or exact fix diff for round 2;
- linked Issue and heavy spec packet when applicable.

Use the selected profile's canonical `requires_independent_review` policy:
fastlane uses self-review; standard and heavy use an independent reviewer lane.
For `independent_lane`, a trusted host or coordinator injects the closed
`review_attestation` after review, binding `lane_id`, `reviewer_actor`, current
head, and current gate invocation. The implementation or review agent must not
mint, edit, copy, persist, or reuse this attestation. `self_review` omits it.

## Contract

<!-- specrail-bounded-review-contract-v1:start -->
Compact review contract (`contract_version: 3`):

- Round 1 uses `mode: full` and binds the exact PR base-to-head diff with
  `base_head_sha` plus `diff_sha256`. Round 2 uses `mode: diff_only`, binds
  the exact fix diff with the same fields, embeds the bound round-1 artifact
  as `prior_review`, and is valid only when that prior review contains an
  unresolved P0/P1. It carries each prior unresolved P0/P1 finding forward and
  limits the fix diff to that finding's predeclared `path` or `fix_paths`.
  A round above the selected profile's canonical cap returns `needs_human`.
- Current unresolved `P0`/`P1` findings block. `P2`/`P3` findings are
  non-blocking follow-ups on the current Issue/PR and never create Issues
  automatically.
- A hosted finding with `outdated: true` does not block. A current-head
  unresolved `P0`/`P1` still blocks regardless of origin.
- `review_source` follows the selected profile's canonical
  `requires_independent_review` policy; noncanonical profile overrides block.
- The artifact is advisory and cannot grant final approval or merge authority.
<!-- specrail-bounded-review-contract-v1:end -->

Artifact fields are the closed set declared by
`schemas/review_result.schema.json`. `body` includes `## Summary` and
`## Verdict`. Findings use stable IDs, severity, status, and summary; path/line
must point into the supplied diff when present.

An empty hosted-check rollup is not a new review round. Prefer fixing workflow
triggers; only a trusted collector declaration for
`hosted_ci_not_triggered_for_base` may enter the PR gate's degraded path.

## Verify

```sh
python3 checks/review_json_gate.py --repo . \
  --review artifacts/review.json --diff artifacts/review.patch --json
```

Report every rejection in one response. If the gate returns `blocked`, correct
the artifact or implementation according to the evidence; do not add review
rounds. If it returns `needs_human`, stop and request a human decision.
