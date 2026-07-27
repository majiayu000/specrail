---
name: implx
description: "Use only for explicit implx requests. Plain implx drains the actionable issue/PR queue in review mode with SpecRail gates and GH-143 tiered merge authorization: green fastlane/standard PRs with independent tier substantiation merge as standard_auto; heavy or sensitive items keep per-PR human authorization. `implx auto` is the explicit run-scoped auto mode."
---

# Implx

Recognize the shorthand, record mode, run the bounded startup, then delegate
to focused SpecRail skills. Queue policy lives in
`skills/specrail-implement-queue/SKILL.md`.

## Tiered Read Set

The measured bootstrap set is `AGENTS.md`, `AGENT_USAGE.md`, `workflow.yaml`,
`states.yaml`, `labels.yaml`, and this file. Do not call phase-loaded files
startup evidence.

Single-issue shortcut: after qualification load
`skills/specrail-implement/SKILL.md`; on entering review load the canonical
`skills/specrail-review-pr/SKILL.md` and, when native review dispatch applies,
`integrations/threads.md`; before PR evidence/gating load
`skills/specrail-pr-gate/SKILL.md`. The queue skill stays excluded.

Queue startup adds `skills/specrail-implement-queue/SKILL.md` and
`templates/queue_plan.yaml`. Load review, threads, implement, and PR-gate
contracts only at their phases; load `skills/specrail-workflow/SKILL.md` only
for route ambiguity.

## Startup And Queue Mode

1. From the bootstrap config select locale, human gates, and route-gate
   requirements.
2. Fetch current remote state before mapping a GitHub queue; list open
   issues, open PRs, current branch, dirty files, worktrees; map existing
   PRs before creating replacement PRs.
3. Record queue scope. Plain `implx`, `use implx`, `用 implx` (and explicit
   equivalents like `implx drain full queue`, `用 implx 做完整队列`) mean
   `queue_mode: full_queue_drain`. Use `queue_mode: bounded_tranche` only
   when the prompt explicitly limits scope (one issue, one PR, the current
   tranche, plan-only, status-only, review-only).

Single-issue short circuit: use it only when the prompt names exactly one
issue, its non-legacy product/tech/tasks packet is `complete`, its
done-when is decidable, and the surface is plausibly `fastlane`/`standard`.
Skip only the full-queue coverage map, queue-planning YAML, and tranche
budget. Still map existing PRs, collect duplicate-work evidence, pass the
`implement` route, verify against the packet, produce and validate an
exact-head local review artifact/manifest, collect current PR evidence with
`--review-manifest`, and run the serial PR gate plus applicable merge
  authorization through the phase-loaded implement, review/threads, and
  PR-gate contracts. `exception_allowed` is not a complete
packet and never qualifies. Fall back to the queue skill on multi-issue
coupling, ownership conflict, heavy risk, packet/head drift, or any
missing qualification.

## Authorization Mode

Record the mode at startup and pass it downstream. The repository's
persisted `automation_policy.auth_mode` is a `review` safety baseline; it
never selects or authorizes auto mode.

`auth_mode: review` — the DEFAULT for plain `implx` and its variants:
- Tiered merge authorization (GH-143): a `fastlane`/`standard` PR with full
  green evidence (CI rollup passing, all review threads resolved, pr_gate
  `allowed`, independent reviewer-lane verdict `clean`/`non_blocking`) AND
  independent tier substantiation (gate-verifiable CI tier-check artifact,
  or a reviewer-lane `tier_attestation` in a schema-valid artifact whose
  own `review_source` is `independent_lane`) merges without a per-PR
  question; record `authorization_tier: standard_auto` and
  `merge_authorization.source: tier_policy_gh143` on the checkpoint item.
  A `review_source: self_review` item never qualifies.
- `heavy` tier and enforcement-sensitive surfaces (gate code, enforcement,
  contracts, authorization semantics, schemas/migrations, security) keep
  per-PR explicit human merge authorization in the current conversation
  (`authorization_tier: heavy_manual`). Missing, unevidenced, or disputed
  `pr_tier` fails closed to `heavy`; only the reviewer/merge-reviewer lane
  or a human sets or clears a tier dispute. Tier authorization never fills
  an evidence gap — any non-green evidence means wait or route to a human.
- Route `needs_spec`/`needs_tasks` to spec-writing skills but wait for
  human confirmation before implementing from a freshly drafted spec.

`auth_mode: auto` — selected only by a current user message that explicitly
says `implx auto` / `implx 自动`:
- The invocation itself IS the standing merge authorization for this run:
  merge whenever ALL evidence is current and green per the queue skill (CI
  rollup, PR gate, resolved threads, clean merge state, reviewer-lane
  evidence); use closing keywords for final slices; close merged-but-open
  issues in the closure audit; never ask per-PR merge questions.
- `needs_spec`/`needs_tasks` issues are actionable: auto-draft via the
  focused skills, then implement. Run-scoped standing authorizations (exact
  conditions in the queue skill): readiness labels for complete-coverage
  issues, scoped coordinator self-review after two recorded distinct lane
  failures on one PR, same-owner repositories explicitly referenced by
  queue issues, and next-minor deprecation-window defaults.
- Items genuinely needing a human decision (duplicate ownership, waivers,
  probe/time-window gates, destructive actions, conflicting feedback,
  architecture rewrites, cross-owner repos, evidence-starved specs) never
  block the queue: skip, keep draining, report once in `human_decisions`
  with a recommendation each.
- Budget exhaustion without degradation follows the queue skill's
  Same-Session Tranche Rollover; hand off to a fresh session only on
  compaction budget, context soft stop, user interrupt, or an
  empty/fully-blocked queue. With Codex goal capability, create the drain
  goal per the queue skill's Goal Use; compaction then re-anchors from the
  checkpoint instead of ending the run.

In both modes, never force-push, delete unmerged branches, replace a
maintainer-writable PR without cause, publish releases, or act outside the
repository without explicit instruction (auto: same-owner repos referenced
by queue issues are in scope; cross-owner always needs a human). Auto never
weakens the Bounded Tranche Hard Stop, reviewer-lane, or self-review rules:
`full_queue_drain` executes as bounded tranches per the queue skill.

## Review Contract And Threads

The canonical `manifest.version: 2` / `bounded_diff_v1` contract lives in
`skills/specrail-review-pr/SKILL.md`; do not copy it here; load it at review entry.

For GitHub queues, reviewer lanes, merge gates, and closure audit make
native thread dispatch required whenever native subagent capability is
available: load `integrations/threads.md`, follow the queue skill's
orchestration rules, and record `thread_dispatch_gate` in the runtime
checkpoint before implementation, review, or merge work. A coordinator
self-review is not a native thread and satisfies merge review only for PRs
whose current-head GitHub evidence passes the closed
`basis: fastlane_policy` path in the queue skill; checkpoint
self-declaration is not tier evidence. Primary reviewer evidence must be
produced locally (`review_execution: local` on the exact-head terminal
artifact) via `codex review --base <base>` or a native
reviewer/merge-reviewer lane; hosted `@codex review` comments are
supplemental only and never populate the primary artifact. If no native
threads capability exists, record the fallback and report it. Wait for CI
and long checks with single blocking calls per the queue skill's Waiting
Discipline — never a model-driven poll loop.

## Delegate, Boundaries, Handoff

After startup, load `skills/specrail-implement-queue/SKILL.md` for any
issue/PR queue and pass `implx_context` (overall_objective, queue_mode,
auth_mode, user_authorization, current_branch, dirty_files, open_issues,
open_prs). Report the compact handoff produced by the queue skill
(`implx_handoff`: route, modes, delegated skill, queue truth,
`human_decisions`, focused handoff, checkpoint reference for
`thread_dispatch_gate` — never copy its fields). Boundaries: green CI alone
is not merge readiness; hosted review is never the primary reviewer lane;
never close an issue from a partial implementation; never replace a
maintainer-writable PR unless stale, unsafe, unwritable, or human-approved;
never use old Codex session logs as queue state.
