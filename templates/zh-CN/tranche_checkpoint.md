# Milestone Checkpoint

这是长时间 agent run 的可选恢复游标。仅在 milestone 开始、完成，或 run
交接、阻塞、结束时更新。GitHub 与 SpecRail artifact 仍是工作流真相。

不要把可变 GitHub 状态复制进 checkpoint：不得记录 head SHA、CI 状态、
review 结果、review thread、merge state、authorization、PR gate、branch、
worktree、budget 或 agent telemetry。

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
