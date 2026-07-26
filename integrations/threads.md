# Threads Integration

SpecRail can work with a threads-style orchestration skill, but it must not
depend on one. SpecRail owns the repository workflow contract. A threads skill
owns execution orchestration when work needs parallel lanes, queue gates,
review gates, or closure audits.

## Principle

- SpecRail is the policy and artifact layer.
- Threads is the optional execution layer.
- SpecRail checks run before thread dispatch and again before completion.
- Missing thread support falls back to the normal single-agent SpecRail flow
  only after the fallback and reason are recorded.
- Stable machine-facing IDs stay unchanged across integrations and locales.
- Large logs and raw tool output are artifacts, not parent-thread state.

## When To Use Threads

Use an available threads skill after SpecRail preflight when the task involves:

- a GitHub issue or pull request queue
- multiple independent implementation lanes
- read-only planner or reviewer lanes
- review thread, CI, or merge-readiness closure
- long-running work that needs a durable handoff

Do not use threads for a small single-file change, ordinary spec drafting, or
any task where all writable files overlap.

## Execution Order

1. Run SpecRail preflight.
   - Load `AGENTS.md`, `workflow.yaml`, `states.yaml`, `labels.yaml`, relevant
     templates, and `skills/specrail-workflow/SKILL.md`.
   - Select the locale.
   - Identify the route, required artifacts, human gates, and verification
     commands.
2. If the task needs queue or parallel orchestration, load the threads skill.
3. Run the threads capability and queue gates.
   - Confirm whether native subagents are available.
   - Record `thread_dispatch_gate` before implementation, review, push, or
     merge work.
   - Fetch remote truth for GitHub queues.
   - Map issues to existing PRs before opening new work.
   - Build a lane map with disjoint writable files.
4. Execute lanes.
   - Spawn every lane with a minimal context pack (task, diff or branch ref,
     spec paths, compact carry) — never a fork of the coordinator's full
     conversation history (`fork_turns: all` or equivalent), for any lane role.
   - Planners and reviewers are read-only.
   - Workers own explicit writable paths.
   - The coordinator owns shared verification and final synthesis.
   - Large command output goes to artifact files; parent context receives only
     exit code, short tail, targeted grep, and artifact paths.
5. Run SpecRail verification.
   - Validate the pack.
   - Validate the spec packet when a spec changed.
   - Preserve human-facing locale rules.
6. Run threads closure audit when GitHub queue or PR state changed.
   - Run it once per tranche, at tranche end, covering every PR and issue the
     tranche touched in one batch — not as a full re-check after each
     individual merge. A mid-tranche re-check is justified only when the
     agent's own action produced an unexpected merge-state outcome.
   - Re-check PR heads, CI, review threads, merge state, and issue closure.
   - Separate remote truth from local worktree state.

For GitHub PR merge work, native thread dispatch is mandatory when native
subagents are available. A PR must have at least one independent read-only
`reviewer` or `merge_reviewer` native lane before merge readiness can be
reported. The coordinator lane is not a native reviewer, even when it performs
the final synthesis. Exception: a `fastlane`-tier, non-enforcement-sensitive
PR may use coordinator self-review only when current-head GitHub tier evidence
passes `basis: fastlane_policy` per
`skills/specrail-implement-queue/SKILL.md`; this resolves the "do not use
threads for a small single-file change" rule without trusting checkpoint
self-declaration. The exact-head local artifact/manifest and all other gates
remain mandatory.

## Handoff Contract

Agents should record this block when both systems are active:

```yaml
specrail_threads_handoff:
  specrail:
    route:
    current_state:
    selected_locale:
    required_artifacts:
    human_gates:
    verification_commands:
  threads:
    mode:
    truth_level:
    queue_ledger:
    issue_to_pr_map:
    lanes:
    merge_policy:
    stop_conditions:
  checkpoint:
    path:  # holds thread_dispatch_gate, context_budget, output_firewall
    runtime_gate:
```

The block is a handoff artifact, not a schema-stable API. A future evaluator can
turn it into a validated artifact after repeated real use.

## Approved-Spec Implementation Queue

When the route is `implement` and several approved specs are ready, use
`skills/specrail-implement-queue/SKILL.md` before dispatching threads.

The queue skill owns the SpecRail side of the plan:

- issue to spec mapping
- existing PR detection
- partial versus final PR closing semantics
- acceptance criteria coverage
- required deterministic checks
- human gates and merge authorization

Threads owns the orchestration side:

- native subagent availability
- queue ledger
- lane map and writable ownership
- read-only planner and reviewer lanes
- native reviewer or merge-reviewer evidence when merge work is in scope
- CI polling and review-thread checks
- closure audit after PR or issue state changes
- parent context budget and output firewall enforcement

The queue plan block is defined once, in
`skills/specrail-implement-queue/SKILL.md` (`specrail_implementation_queue`);
do not maintain a second field layout here. When threads orchestration is
active, extend that block with one `orchestration` section:

```yaml
# appended to the specrail_implementation_queue block from the queue skill
orchestration:
  threads_mode:
  lanes:
  fallback_reason:
```

`thread_dispatch_gate` (with its `native_thread_evidence`) is recorded exactly
once, in the runtime checkpoint; every other artifact — this handoff, the
`implx` wrapper handoff, reports — references the checkpoint instead of
copying the fields. The same goes for `context_budget` and `output_firewall`.

This handoff must not grant approval or merge authority. It only preserves the
evidence each system needs.

## Field Mapping

| SpecRail field | Threads field | Notes |
| --- | --- | --- |
| `route` | `intent_contract.goal` | The route defines the kind of workflow action. |
| `required_artifacts` | `queue_ledger.acceptance_evidence` | Threads records evidence for each queue item. |
| `human_gates` | `merge_policy`, `stop_conditions` | Threads must not bypass SpecRail gates. |
| `verification_commands` | `verification_owner` | One owner runs shared checks for a tranche. |
| `selected_locale` | final report language | Human-facing reports follow SpecRail locale rules. |
| runtime checkpoint | `queue_ledger`, `threads_run_log` | Checkpoints are local handoff artifacts; run logs are observational. |

## Long-Run Guardrails

For long queues, use these defaults unless the user or runtime provides a
stricter budget:

- soft stop at 50% of the active context window
- hard stop at 65%
- critical stop at 75%

At hard stop, write or update the runtime checkpoint and hand off to a fresh
parent thread. At critical stop, do not spawn lanes or read large outputs; write
checkpoint and resume instructions only.

Do not load raw Codex session JSONL or old parent transcripts as live queue
state. Use SpecRail artifacts, runtime checkpoints, repo-local compact run logs,
and fresh GitHub truth.

Large output commands must use an artifact-first pattern:

```bash
cargo test --all-features --locked > artifacts/logs/<tranche>/cargo-test.log 2>&1
tail -n 150 artifacts/logs/<tranche>/cargo-test.log
```

Avoid broad searches under `.codex`, `.claude`, `target`, `node_modules`,
session JSONL, or log files.

## Bounded Review Contract

The canonical bounded review contract (`manifest.version: 2`,
`bounded_diff_v1`) lives in `skills/specrail-review-pr/SKILL.md`;
do not copy it here — load that Skill before any review lane.

For re-review after fixes, resume or message the existing reviewer lane. If it
cannot resume, dispatch the next bounded `diff_only` lane with compact carry;
never replay full history. See `skills/specrail-review-pr/SKILL.md`.

One reviewer lane per PR is the default; do not stack mechanical-audit,
cross-review, adversarial, and final-re-review lanes on one PR unless the item
is `heavy` tier, a human asked for it, or a recorded lane failure forces a
retry. An artifact formatting/metadata defect is repaired by regenerating the
artifact from the existing review output — it does not open a new review
round or re-collect evidence for an unchanged head.

## Fallback

If no threads skill or native subagent capability is available, the agent should
continue with the normal SpecRail flow and say that no native threads were
launched. If the user explicitly requested threads, the agent may provide a
prompt pack and lane map instead of pretending parallel execution happened.

If native subagents are available and the work includes PR review or merge, do
not use single-agent fallback unless the user explicitly forbids spawning or the
checkpoint records a concrete `no_spawn_reason` that makes native dispatch
unsafe. Such a fallback cannot be reported as full threads execution.

## Non-Goals

- Do not vendor a local threads skill into SpecRail.
- Do not make threads required for adoption.
- Do not let threads override SpecRail policy, locale, or human gates.
- Do not add automatic merge or final approval.
- Do not require GitHub for repositories that use SpecRail without GitHub.

## Minimal Agent Rule

For agents such as Codex:

```text
Run SpecRail first. If the task is a queue, parallel-lane, review-thread,
merge-gate, or closure-audit problem and a threads skill is available, use
threads after SpecRail preflight. SpecRail owns policy; threads owns
orchestration. Return to SpecRail verification before reporting completion.
```
