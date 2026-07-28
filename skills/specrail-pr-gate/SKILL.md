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
  --json > pr-evidence.json
```

For heavy work, pass `--authorization <authorization.json>`. It must bind actor,
timestamp, current head, and the same invocation ID.

## Gate

```sh
python3 checks/pr_gate.py --repo . --evidence pr-evidence.json --json
```

The evidence must agree on repository, PR, linked Issue, current/query head,
changed files, CI head and conclusion, review head/profile, clean merge state,
and sensitive classification. Sensitive changes must be heavy and use an exact
current-head checkout. Old runtime, tier, content-binding, or review-manifest
fields are unsupported and require fresh GitHub evidence.

- `allowed`: deterministic evidence is green; human merge boundary remains.
- `needs_human`: review cap or heavy authorization is missing.
- `blocked`: current evidence is invalid or a P0/P1/security/CI condition blocks.

Collect evidence completely before any merge dispatch. Never place collection,
gate, and merge in one parallel batch. Report the evidence path, head SHA,
profile, decision, blockers, and verification commands.
