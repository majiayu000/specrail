---
name: specrail-pr-gate
description: Use before reporting a SpecRail PR as merge-ready. Collects read-only PR evidence, runs the offline PR gate, checks linked work, current head SHA, CI, review decision, review threads, merge state, and human merge authorization without merging.
---

# SpecRail PR Gate

Use this skill before saying a PR is merge-ready.

## Steps

1. Collect current PR evidence. Prefer the read-only adapter when available:

```sh
python3 checks/github_pr_evidence.py --github-repo <owner/repo> --pr <pr-number> --json > <evidence.json>
```

2. Run the offline gate:

```sh
python3 checks/pr_gate.py --repo . --evidence <evidence.json> --json
```

3. Confirm evidence includes linked issue, current PR head SHA, gate-query
   completion timestamp, gate-query head SHA, CI/check rollup, review decision,
   review-thread resolution, merge state, and human merge authorization.
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
- `merge_dispatched_at` and `merge_head_sha` when auditing a merge record after
  dispatch.

If the PR head changes, new review activity appears, CI changes, or merge is
deferred long enough that the evidence may be stale, collect fresh PR evidence
and rerun `pr_gate.py` before merging.

## Boundaries

- Do not merge from this skill.
- Do not dispatch gate queries and merge in parallel.
- Do not treat green CI alone as merge readiness.
- Do not ignore unresolved review threads.
- Do not replace maintainer final review or human merge authorization.
