# Tech Spec

## Linked Issue

GH-160

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":160,"complete":true,"paths":["checks/session_telemetry.py","checks/runtime_context_budget.py","checks/runtime_ledger_gate.py","schemas/runtime_checkpoint.schema.json","tests/test_session_telemetry.py","tests/test_runtime_context_budget.py","skills/specrail-implement-queue/SKILL.md","skills-lock.json","templates/tranche_checkpoint.md","templates/zh-CN/tranche_checkpoint.md"],"spec_refs":["specs/GH160/product.md","specs/GH160/tech.md","specs/GH160/tasks.md"]}
-->

## Product Spec

See `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Session telemetry event scan | `checks/session_telemetry.py:61`, `checks/session_telemetry.py:113`, `checks/session_telemetry.py:165` | The collector recognizes compaction/tool events and emits compaction, tool-call, and wall-clock counters for an explicit tranche window; it does not inspect `token_count` events. | B-001..B-003 and B-009 extend this single read-only adapter. |
| Runtime checkpoint gate | `checks/runtime_ledger_gate.py:526`, `checks/runtime_ledger_gate.py:549` | Versions 1–3 are accepted, but `context_budget` validation only checks a positive window and ordered ratios. | B-004..B-008 need deterministic watermark/convergence enforcement. The file is already 795 lines, so new logic belongs in a focused helper. |
| Runtime checkpoint schema | `schemas/runtime_checkpoint.schema.json:334` | `context_budget` requires only `window_tokens` and three thresholds and permits undeclared additional fields. | The new optional observation/convergence structure needs a machine-readable shape without breaking old checkpoints. |
| Queue context protocol | `skills/specrail-implement-queue/SKILL.md:321`, `skills/specrail-implement-queue/SKILL.md:405` | Soft/hard/critical actions are prose; telemetry is required only after compaction and emits counters, not context watermark evidence. | B-005 B-008 B-010 turn the prose threshold into a checkpoint gate and collection sequence. |
| Checkpoint templates | `templates/tranche_checkpoint.md:76`, `templates/zh-CN/tranche_checkpoint.md:65` | Templates declare threshold ratios but no observed context or convergence action. | Operators need the exact evidence fields required by B-004..B-006. |
| Existing telemetry and ledger tests | `tests/test_session_telemetry.py:28`, `tests/test_runtime_ledger_gate.py:502` | GH-137 covers compaction and hard budget dimensions; the ledger test file is already large. | Extend collector tests in place and add a focused context-budget gate test module while preserving GH-137 regressions. |

## Proposed Design

### Token telemetry extraction

Extend `checks/session_telemetry.py` with a small parser for Codex
`token_count` events. A valid observation comes only from:

- event type `token_count` (payload or top-level form);
- `info.last_token_usage.input_tokens` as current-turn context usage (the
  cached-input field is a subset and is not added again); and
- `info.model_context_window` as the runtime-declared denominator.

The parser deliberately ignores cumulative `info.total_token_usage` for
watermark enforcement. It accepts only non-boolean non-negative integer token
counts and a positive integer window. It aggregates the ordered valid samples
within `tranche_start_offset` into:

- `observed_context_tokens` (latest sample),
- `max_observed_context_tokens`,
- `observed_context_tokens_p50` (integer median),
- `context_observation_count`,
- `observed_model_context_window`, and
- `context_observed_at` when the event has a valid timestamp.

If there is no valid sample, these keys are absent. Existing telemetry fields
and unavailable-file behavior remain unchanged. The collector returns only
numeric summaries and provenance, never raw event data.

### Context-budget gate helper

Add `checks/runtime_context_budget.py` and call it from the existing
`context_budget` validation point in `checks/runtime_ledger_gate.py`. Keeping
the rules in a helper prevents the already-795-line gate from crossing the
800-line hard ceiling.

For checkpoints that declare no context observation, the helper returns
without changing the version 1–3 result (B-007). If any new observation field
is present, it validates the complete set:

```text
observation_source: runtime | session_log
observed_context_tokens: non-negative integer
max_observed_context_tokens: non-negative integer >= observed_context_tokens
observed_context_ratio: number
max_observed_context_ratio: number
context_observed_at: ISO8601 string
```

The gate recomputes both ratios using checkpoint `window_tokens` and rejects a
declared ratio outside a small floating-point tolerance. This keeps the
checkpoint auditable while preventing ratio self-reporting from bypassing the
threshold.

When the recomputed maximum or latest ratio reaches `soft_stop_ratio`, require
`convergence_action`:

```json
{
  "action": "end_tranche | handoff",
  "recorded_at": "ISO8601",
  "trigger_observed_context_tokens": 150000,
  "next_action": "non-empty handoff/resume instruction",
  "critical_only_checkpoint_and_resume": false
}
```

The trigger must equal `max_observed_context_tokens`. `handoff` requires the
top-level checkpoint status `handoff`; `end_tranche` requires one of
`handoff`, `blocked`, or `complete`. At hard stop only `handoff` is accepted.
At critical stop `critical_only_checkpoint_and_resume` must be true. These are
gate errors, not warnings, and budget overrides do not suppress them.

### Schema, templates, and workflow text

Extend `schemas/runtime_checkpoint.schema.json` with optional typed fields in
`context_budget`; legacy checkpoints remain schema-valid. Update both tranche
templates with null placeholders and an example convergence action. Replace
and tighten the queue skill's existing context-budget prose so the net file
size does not exceed 800 lines:

1. collect telemetry before spawning a new lane or broad action when runtime
   `token_count` is available;
2. copy the numeric context summaries into the checkpoint and compute/store the
   ratios;
3. run `runtime_ledger_gate.py`;
4. at soft stop, end the tranche or hand off; hard/critical rules are stricter;
5. a persistent goal never permits the current session to continue past the
   context watermark.

Regenerate `skills-lock.json` with the repository's deterministic lock helper
after changing the skill.

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | token-count parser | `test_collect_uses_last_token_usage_for_context` |
| B-002 | telemetry aggregation | `test_collect_reports_latest_max_and_p50_context` and existing offset test extended with token events |
| B-003 | telemetry validation/omission | `test_collect_omits_context_when_token_observations_are_invalid` |
| B-004 | `runtime_context_budget.validate_context_budget` | `test_context_ratio_is_recomputed_and_mismatch_blocks` |
| B-005 | soft-stop convergence gate | `test_soft_stop_requires_terminal_convergence_action` |
| B-006 | action/status/trigger consistency | `test_convergence_action_must_match_status_and_high_watermark` |
| B-007 | compatibility branch | `test_legacy_checkpoint_without_context_observation_is_unchanged` plus full existing suite |
| B-008 | hard/critical branches | `test_hard_stop_requires_handoff` and `test_critical_stop_restricts_remaining_work` |
| B-009 | collector purity | existing `test_telemetry_collect_is_read_only` plus assertions that no raw event object is returned |
| B-010 | queue skill and templates | workflow check plus targeted text/schema assertions in `tests/test_runtime_context_budget.py` |
| B-011 | GH-137 regression | `python3 -m pytest -q tests/test_session_telemetry.py tests/test_runtime_ledger_gate.py tests/test_runtime_context_budget.py` |
| B-012 | p50 output and explicit rollout status | telemetry p50 unit test; PR description records that production comparison is pending post-rollout unless a real sample exists |

## Data Flow

```text
explicit session JSONL path + tranche offset
  -> session_telemetry numeric summaries
  -> context_budget checkpoint fields
  -> runtime_context_budget recomputes ratios
  -> runtime_ledger_gate allowed / blocked
  -> soft-stop terminal checkpoint and resume handoff
```

No gate performs file discovery, network calls, or checkpoint mutation.

## Alternatives Considered

- Reuse cumulative `total_token_usage`: rejected because it measures lifetime
  spend, not the per-turn context height that triggers the issue.
- Keep the rule only in SKILL.md: rejected because the production audit shows
  prose watermarks were not enforced.
- Add a new parallel context gate: rejected by issue scope and W-17; the
  existing runtime ledger remains the single decision point.
- Require new fields on all checkpoint versions: rejected because older
  checkpoints lack runtime observations and must preserve prior decisions.
- Add the rules directly to `runtime_ledger_gate.py`: rejected because the file
  is already at the 800-line ceiling.

## Risks

- Security: the collector reads an explicitly supplied local session file but
  returns only aggregate numbers; raw content must never enter checkpoint or
  logs.
- Compatibility: new schema fields are optional until an observation is
  declared; partial declarations fail closed.
- Runtime drift: event shapes may change. Unknown or malformed shapes are
  skipped and never become a trusted zero; tests pin the currently exposed
  Codex 0.144.6 field names.
- Performance: aggregation is linear in the already-scoped tranche window and
  adds constant-size output.
- Maintenance: rules are isolated in a focused helper and the queue skill must
  remain at or below 800 lines after editing.

## Test Plan

- [ ] Unit: token observation parsing, validation, aggregation, and offset.
- [ ] Unit: soft/hard/critical gate decisions and compatibility.
- [ ] Schema/workflow: `python3 checks/check_workflow.py --repo .`.
- [ ] Spec depth: `python3 tools/spec_depth_audit.py --spec-dir specs/GH160 --gate`.
- [ ] Full regression: `python3 -m pytest -q`.
- [ ] Operational rollout: after merge, run one real bounded drain and attach
  p50 context plus token/PR comparison to GH-160; do not fabricate this result
  in local fixtures.

## Rollback Plan

Revert the helper import/call, collector context aggregation, schema/template
fields, and queue-skill protocol together. Existing checkpoint versions and
GH-137 budget fields remain valid throughout; no data migration or destructive
cleanup is required.
