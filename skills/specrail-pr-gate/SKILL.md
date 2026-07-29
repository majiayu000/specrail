---
name: specrail-pr-gate
description: Run the read-only compact SpecRail PR gate before reporting merge readiness. Checks current head, linked Issue, CI, review, merge state, profile, sensitive classification, and heavy human authorization without merging.
---

# SpecRail PR Gate

Use after implementation and compact review. The gate is advisory and never
approves or merges.

## Collect

```sh
python3 checks/github_pr_evidence.py --github-repo OWNER/REPO --pr <pr> \
  --issue <issue> --profile <fastlane|standard|heavy> \
  --gate-invocation-id <current-id> --review <review.json> \
  --hosted-snapshot-template --json > hosted-snapshot.json
# Trusted host/coordinator confirms the template and injects its digest.
python3 checks/github_pr_evidence.py --github-repo OWNER/REPO --pr <pr> \
  --issue <issue> --profile <fastlane|standard|heavy> \
  --gate-invocation-id <current-id> --review <review.json> \
  --review-attestation <host-attestation.json> \
  --json > pr-evidence.json
```

For standard/heavy `independent_lane` review, only a trusted host or coordinator
may inject `--review-attestation`; the implementation or review agent must not
mint, edit, copy, persist, or reuse it. The resulting `review_attestation`
is top-level PR evidence outside raw current and prior review artifacts. It
binds `lane_id`, `reviewer_actor`, current artifact ID, current head, and current
gate invocation; round 2 also binds the prior artifact ID and prior head.
`review_sha256` is the SHA-256 of the complete canonical raw review JSON, so
finding, verdict, and embedded-prior changes invalidate the attestation.
Hash exactly the file passed to `--review`; do not add or predict hosted
findings before hashing. The collector preserves raw `review` unchanged and
stores current server-canonical threads in the separate top-level
`hosted_findings` layer. The PR gate verifies the raw attestation first and
only then combines both layers in memory. Fastlane `self_review` omits this
input.

For standard/heavy, the same ephemeral attestation must contain
`hosted_snapshot_sha256`: SHA-256 of canonical JSON containing exactly
`head_sha`, `invocation_id`, `hosted_findings`, and
`prior_review_boundary`. The first command only acquires a read-only template.
A trusted host/coordinator confirms it and injects the digest; the second
command recollects and requires an exact match. Implementation and review
agents must not mint or edit the digest.

For heavy work, a trusted host or coordinator may inject
`--authorization <authorization.json>` only from a current real-human
conversation. An agent must never mint, edit, copy, persist, or reuse it. The
authorization is ephemeral and binds actor, timestamp, current head, and the
same invocation ID.

When hosted checks are structurally unavailable for a non-default base, only
the trusted host/coordinator may inject `--checks-unavailable`. The declaration
is closed to `hosted_ci_not_triggered_for_base`, exact base refs, workflow
trigger evidence, non-empty local verification, and `verified: true`. Pending,
failed, or merely absent current-head CI cannot use this degraded path.
Its declared base refs must exactly match the collector's top-level
`base_ref` and `default_base_ref`.

## Gate

```sh
python3 checks/pr_gate.py --repo . --evidence pr-evidence.json --json
```

The evidence must agree on repository, PR, linked Issue, current/query head,
changed files, CI head and conclusion, review head/profile, clean merge state,
and sensitive classification. Every profile requires an exact current-head
checkout; sensitive changes must also be heavy. Old runtime, tier,
content-binding, or review-manifest fields are unsupported and require fresh
GitHub evidence.

For round 2, embedded prior findings with local origin remain complete review
evidence. Only findings explicitly claiming hosted origin may be reconciled
against authenticated server history; a current, non-outdated hosted P0/P1
still blocks.

- `allowed`: deterministic evidence is green; human merge boundary remains.
- `needs_human`: review cap or heavy authorization is missing.
- `blocked`: current evidence is invalid or a P0/P1/security/CI condition blocks.

Collect evidence completely before any merge dispatch. Never place collection,
gate, and merge in one parallel batch. Report the evidence path, head SHA,
profile, decision, blockers, and verification commands.

The gate result is `advisory_only`; the merge executor must independently obey
the authorization in the current human conversation.
