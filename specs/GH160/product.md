# Product Spec

## Linked Issue

GH-160

## User Problem

SpecRail declares soft, hard, and critical context-watermark ratios, but the
runtime checkpoint records only the configured ratios. It does not record the
context actually observed for a turn, and `runtime_ledger_gate.py` therefore
cannot distinguish a healthy session from one continuing at 219K+ tokens. In a
24-hour production drain this allowed sessions to run for 2,600–3,400 turns at
a 219K median context while every context-budget check still appeared valid.

## Goals

- Collect per-turn context usage from Codex `token_count` telemetry without
  exposing raw session content.
- Record the latest and maximum observed context watermarks in the checkpoint
  and make the gate recompute their ratios against the declared window.
- Require the first checkpoint at or above the soft stop to converge the
  current tranche by ending it or handing it to a fresh session.
- Preserve the existing compaction and hard-dimension budget enforcement from
  GH-137 and the turn-batching discipline from GH-159.
- Expose a tranche p50 context metric so production drain runs can compare the
  target of less than 130K tokens without turning that operational KPI into a
  fabricated local pass.

## Non-Goals

- No additional parallel gate or second checkpoint format; this extends the
  existing `context_budget` object.
- No recursive discovery or direct gate reads of Codex session JSONL.
- No change to model context-window configuration, compaction thresholds,
  billing, or Codex token accounting.
- No claim that unit tests alone prove the post-rollout production p50 target;
  that comparison requires a real drain sample after deployment.
- No changes to issues or PRs other than GH-160 and its two heavy-tier PRs.

## Behavior Invariants

1. B-001 When a tranche-window `token_count` event contains
   `info.last_token_usage.input_tokens` and `info.model_context_window`, the
   read-only telemetry collector shall emit a valid context observation using
   those values; it shall not add the cached-input subset a second time or
   derive current context from cumulative `total_token_usage`.
2. B-002 When several valid context observations exist in one tranche window,
   telemetry shall emit the latest observed tokens, the maximum observed
   tokens, the observation count, and the median observed tokens; event order
   and the existing `tranche_start_offset` define the window.
3. B-003 Missing, null, boolean, non-integer, negative, or inconsistent token
   fields shall be skipped and counted as invalid context observations. If no
   valid context observation exists, telemetry shall omit all observed-context
   values rather than report a trusted zero.
4. B-004 The checkpoint `context_budget` shall record observation provenance
   and values supplied by telemetry. The ledger gate shall recompute ratios as
   `observed_tokens / window_tokens`; a caller-supplied ratio that differs from
   the recomputed value shall be rejected rather than trusted.
5. B-005 When the latest or maximum observed context ratio is at or above
   `soft_stop_ratio`, the next checkpoint shall record one convergence action
   from the closed set `{end_tranche, handoff}` with a timestamp, triggering
   observation, and next action. A checkpoint that remains `planning` or
   `running`, or lacks this evidence, shall be blocked.
6. B-006 A soft-stop convergence action shall be internally consistent:
   `handoff` requires checkpoint `status: handoff`; `end_tranche` requires a
   terminal checkpoint status (`handoff`, `blocked`, or `complete`). Its
   triggering token count shall equal the gate-observed high watermark, so a
   stale action cannot authorize continued growth.
7. B-007 Below the soft stop, convergence evidence is optional and existing
   version 1–3 checkpoints without context observations retain their prior
   decision. Once trusted context observations are declared, malformed or
   partial evidence fails closed.
8. B-008 At or above the hard stop, the only valid convergence action is
   `handoff`; at or above the critical stop, the action shall additionally
   state that only checkpoint and resume instructions remain. Neither state may
   be downgraded to an allowed warning or overridden by an unrelated budget
   override.
9. B-009 The collector and gate remain read-only, make no network calls, do not
   return raw event content, and only inspect the explicitly supplied session
   path and tranche window.
10. B-010 The queue skill and checkpoint templates shall require context
    telemetry collection before spawning a new lane or starting another broad
    action when the runtime exposes `token_count`; reaching soft stop ends the
    current tranche even when a goal remains active.
11. B-011 Context telemetry shall be additive to GH-137: compaction,
    wall-clock, tool-call, review-round, full-test, item-cap, and per-dimension
    override behavior shall remain unchanged.
12. B-012 A production comparison may report the collector's tranche p50 and
    queue-runner token totals, but the GH-160 implementation is not considered
    to have proven the `<130K` operational target until a real post-rollout
    drain sample is attached to the issue or a follow-up artifact.

## Acceptance Criteria

- [ ] Telemetry fixtures prove valid `token_count` extraction, latest/max/p50
  aggregation, offset isolation, and omission on invalid or absent data.
- [ ] Runtime-ledger fixtures prove soft, hard, and critical convergence rules,
  stale-action rejection, ratio recomputation, and backward compatibility.
- [ ] `context_budget` schema and both checkpoint templates expose the new
  observation and convergence fields without introducing a separate gate.
- [ ] The queue skill gives an executable collection/checkpoint/convergence
  protocol and stays within its file-size ceiling.
- [ ] Targeted tests, the full Python test suite, and
  `python3 checks/check_workflow.py --repo .` pass.
- [ ] A real post-rollout drain can compare tranche p50 context (target `<130K`)
  and token/PR; absence of that later sample remains explicit rather than being
  silently reported as success.

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-003 B-007 |
| Error / failure paths | covered: B-003 B-004 B-006 |
| Authorization / permission | covered: B-008; unrelated overrides cannot authorize continued high-context execution |
| Concurrency / race | covered: B-002 B-006; ordered tranche observations and matching trigger evidence prevent stale-action reuse |
| Retry / idempotency | covered: B-002 B-009; collection and gate evaluation are read-only and deterministic for one file snapshot |
| Illegal state transitions | covered: B-005 B-006 B-008 |
| Compatibility / migration | covered: B-007 B-011 |
| Degradation / fallback | covered: B-003 B-007; unavailable telemetry is explicit and never fabricated as zero |
| Evidence / audit integrity | covered: B-004 B-006 B-012 |
| Cancellation / interruption | covered: B-005 B-008 B-010 |

## Rollout Notes

This is a heavy runtime-ledger contract change. Merge the spec PR first, then
implement from the merged packet in a separate PR. The first production drain
after merge supplies the operational p50/token-per-PR comparison; it is an
observational rollout check, not a reason to weaken deterministic merge gates.
