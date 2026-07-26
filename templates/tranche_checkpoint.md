# Milestone Checkpoint

This optional local file is a resume cursor for long agent runs. Update it only
when a milestone starts or completes, or when the run hands off, blocks, or
finishes. GitHub and SpecRail artifacts remain the workflow truth.

Do not copy mutable GitHub state into the checkpoint: no head SHA, CI status,
review result, review threads, merge state, authorization, PR gate, branches,
worktrees, budgets, or agent telemetry.

```json
{
  "checkpoint_version": 1,
  "run_id": "YYYY-MM-DD-repo-purpose",
  "repo": "owner/repo or local/path",
  "scope": "the approved queue or tranche scope",
  "status": "running",
  "milestone": {
    "id": "initial-review",
    "state": "active",
    "completed_at": null
  },
  "completed": [
    {"kind": "pr", "number": 10}
  ],
  "pending": [
    {
      "kind": "pr",
      "number": 11,
      "next_action": "complete the initial review"
    }
  ],
  "blocked": [
    {
      "kind": "issue",
      "number": 12,
      "reason": "requires a maintainer decision"
    }
  ],
  "artifact_refs": [
    "artifacts/reviews/initial-review-summary.json"
  ],
  "resume": "Refresh GitHub truth, then continue PR #11.",
  "updated_at": "2026-07-26T12:00:00+08:00"
}
```
