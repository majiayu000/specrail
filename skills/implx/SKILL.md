---
name: implx
description: Use when the user says "implx", "use implx", "用 implx", "implx drain full queue", "implx resume full queue", or asks for the short SpecRail queue shortcut to process or drain a repository's approved-spec issue/PR queue with SpecRail implementation queue planning, optional threads orchestration, per-issue implementation PRs, review-thread and CI gates, merge authorization, and closure audit.
---

# Implx

Use this skill as a short operational entrypoint. It only recognizes the
`implx` shorthand, records the queue mode, performs the minimum startup checks,
and delegates execution policy to the focused SpecRail skills.

Do not duplicate the implementation-queue contract here. The authoritative
queue planning, spec coverage gate, context budget, runtime checkpoint, threads
orchestration, PR gate, and closure-audit rules live in
`skills/specrail-implement-queue/SKILL.md`.

## Startup

1. Run the normal SpecRail startup before remote writes:
   - read the repository `AGENTS.md`
   - read `AGENT_USAGE.md`, `workflow.yaml`, `states.yaml`, `labels.yaml`, and
     `skills/specrail-workflow/SKILL.md` when present
   - select the human-facing locale
   - identify human gates and route-gate requirements
2. Fetch current remote state before mapping a GitHub queue.
3. List open issues, open PRs, current branch, dirty files, and worktrees.
4. Map existing PRs before creating replacement PRs.
5. Record whether the prompt authorizes a bounded tranche or a full queue drain.

## Queue Mode

Use `queue_mode: bounded_tranche` unless the user explicitly asks to drain or
resume the full actionable queue.

These prompts set `queue_mode: full_queue_drain`:

- `implx drain full queue`
- `implx resume full queue`
- `用 implx 完成所有 actionable issues 和 PRs`
- `用 implx 做完整队列`

Pass the selected mode to `skills/specrail-implement-queue/SKILL.md`:

```yaml
implx_context:
  overall_objective:
  queue_mode: bounded_tranche | full_queue_drain
  user_authorization:
  current_branch:
  dirty_files:
  open_issues:
  open_prs:
```

## Delegate

After startup, load `skills/specrail-implement-queue/SKILL.md` for any issue or
PR queue. That skill owns:

- spec coverage classification
- implementation candidate selection
- one-issue-per-PR planning
- partial versus final closing semantics
- context-budget and runtime-checkpoint behavior
- optional threads orchestration
- verification, PR-gate evidence, and closure audit

For one small scoped issue, follow that skill's instruction to route to
`skills/specrail-implement/SKILL.md`.

## Threads

If the queue needs native parallel lanes, reviewer lanes, CI waits,
review-thread checks, merge gates, or closure audit, load
`integrations/threads.md` and then follow the orchestration rules in
`skills/specrail-implement-queue/SKILL.md`.

If no native threads capability is available, continue with the single-agent
SpecRail flow and report that fallback.

## Boundaries

- Do not grant final approval.
- Do not merge without current PR-gate evidence and explicit authorization.
- Do not treat green CI as merge readiness without review-thread and merge-state
  truth.
- Do not close an issue from a partial implementation.
- Do not replace an existing maintainer-writable PR unless it is stale, unsafe,
  unwritable, or a human approves replacement.
- Do not use old Codex session logs as queue state.

## Handoff

Report the compact handoff produced by the focused queue skill. Include this
`implx` wrapper context when useful:

```yaml
implx_handoff:
  route: implement_queue
  overall_objective:
  queue_mode:
  delegated_skill: skills/specrail-implement-queue/SKILL.md
  queue_truth:
    open_issues:
    open_prs:
    current_branch:
    dirty_files:
  focused_handoff:
```
