# Tech Spec

## Linked Issue

GH-37

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Change |
| --- | --- | --- | --- |
| Runtime checkpoint gate | `checks/runtime_ledger_gate.py` | `full_queue_drain` validates checkpoint shape and complete-state remainder, but an item with `spec_status: needs_spec` can still be marked `running` | Add a planning-state allowlist for `needs_spec` / `needs_tasks` |
| Fixtures | `examples/fixtures/runtime-full-queue-*.json` | Existing fixtures do not capture handoff vs false-complete spec coverage behavior | Add handoff-allowed and false-complete-blocked fixtures |
| Tests | `tests/test_runtime_ledger_gate.py` | Runtime gate tests cover merge-ready evidence and checkpoint shape, but not full-queue spec coverage transitions | Add regression tests for missing spec, umbrella coverage, waiting CI, and remaining needs_spec |

## 设计方案

Add a `SPEC_PLANNING_STATES` allowlist in `checks/runtime_ledger_gate.py`.
During `full_queue_drain` item validation, if an issue/PR item has
`spec_status` equal to `needs_spec` or `needs_tasks`, the gate must require the
item `state` to be one of the planning or blocked/deferred states. This keeps
the checkpoint from representing pre-spec work as active implementation.

Keep the existing `remaining_queue` complete-state validation. Add fixtures that
show the intended distinction:

- `runtime-full-queue-handoff-needs-spec.json`: `status: handoff` with remaining
  `needs_spec` work is valid.
- `runtime-full-queue-false-complete-needs-spec.json`: `status: complete` with
  remaining `needs_spec` work is blocked.

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 full-queue items require `spec_status` | existing `full_queue_drain` item validation | `test_full_queue_blocks_implementation_without_spec` |
| P2 `needs_spec` / `needs_tasks` route to planning states | `SPEC_PLANNING_STATES` check | `test_full_queue_blocks_implementation_without_spec` |
| P3 umbrella coverage remains allowed | `spec_status: umbrella_covered` path | `test_full_queue_allows_umbrella_spec_coverage` |
| P4 complete checkpoint cannot leave waiting work | `remaining_queue` complete-state validation | `test_full_queue_blocks_complete_when_pr_is_still_waiting_ci` |
| P5 handoff can preserve remaining spec work | handoff fixture | `test_full_queue_handoff_needs_spec_fixture_is_allowed` |
| P6 false complete is blocked | false-complete fixture | `test_full_queue_false_complete_needs_spec_fixture_is_blocked` |

## 数据流

Input is a local runtime checkpoint JSON file passed to
`checks/runtime_ledger_gate.py`. The evaluator reads the JSON, validates
top-level checkpoint fields, validates `full_queue_drain` fields, evaluates
each item and remaining queue item, then returns a decision object. It performs
no network calls and writes no files.

## 备选方案

- Only add tests without tightening evaluator behavior: rejected because the
  current guard would still permit `needs_spec` work to appear as `running`.
- Treat all `needs_spec` / `needs_tasks` remainders as blocked even for
  handoff: rejected because handoff is a valid bounded stop state for long
  queues.
- Require live GitHub lookup from the runtime checkpoint gate: rejected because
  the gate is intentionally offline.

## 风险

- Security: No credential or command execution path is added.
- Compatibility: Checkpoints that currently mark `needs_spec` or `needs_tasks`
  items as `running` will become invalid; this is intentional fail-closed
  behavior.
- Performance: Validation remains local JSON inspection.
- Maintenance: Fixture examples and evaluator state allowlist must stay aligned
  with queue skill terminology.

## 测试计划

- [ ] `python3 -m py_compile checks/runtime_ledger_gate.py tests/test_runtime_ledger_gate.py`
- [ ] `python3 -m json.tool examples/fixtures/runtime-full-queue-handoff-needs-spec.json >/dev/null`
- [ ] `python3 -m json.tool examples/fixtures/runtime-full-queue-false-complete-needs-spec.json >/dev/null`
- [ ] `python3 checks/runtime_ledger_gate.py --checkpoint examples/fixtures/runtime-full-queue-handoff-needs-spec.json`
- [ ] `python3 checks/runtime_ledger_gate.py --checkpoint examples/fixtures/runtime-full-queue-false-complete-needs-spec.json; test $? -ne 0`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `python3 -m pytest -q`

## 回滚方案

Remove the `SPEC_PLANNING_STATES` validation, the two runtime fixture files,
the added runtime ledger tests, and `specs/GH37`. Existing runtime checkpoint
validation will return to the GH-34 behavior.
