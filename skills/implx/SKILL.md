---
name: implx
description: "Use when the user says \"implx\", \"use implx\", \"用 implx\", or asks for the one-line SpecRail queue shortcut. Plain implx means drain the full actionable issue/PR queue by default: run SpecRail preflight, create missing spec/task PR work before implementation, use threads for reviewer/merge-reviewer lanes when available, create per-issue implementation PRs, require CI/reviewThreads/pr_gate evidence, preserve human merge authorization, and perform closure audit."
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
5. Record queue scope. Plain `implx`, `use implx`, or `用 implx` means full
   actionable queue drain unless the prompt explicitly narrows the scope.

## Queue Mode

Use `queue_mode: full_queue_drain` for the plain shorthand:

- `implx`
- `use implx`
- `用 implx`

These explicit forms are equivalent:

- `implx drain full queue`
- `implx resume full queue`
- `用 implx 完成所有 actionable issues 和 PRs`
- `用 implx 做完整队列`

Use `queue_mode: bounded_tranche` only when the prompt explicitly limits scope,
for example one issue, one PR, the current tranche, plan-only, status-only, or
review-only work. Plain `implx` does not grant merge authorization; merge still
requires explicit authorization in the current conversation.

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

For GitHub issue or PR queues, reviewer lanes, merge gates, and closure audit
make native thread dispatch required whenever native subagent capability is
available. Record `thread_dispatch_gate` before implementation, review, or
merge work. A coordinator self-review is not a native thread and does not
satisfy merge review.

If no native threads capability is available, continue with the single-agent
SpecRail flow only after recording the fallback and reporting that no native
threads were launched.

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
  thread_dispatch_gate:
    native_subagents:
    spawn_requirement:
    native_thread_evidence:
```
