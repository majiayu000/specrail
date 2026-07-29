# Task Plan

## Linked Issue

GH-37

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP37-T001` Owner: checks | Done when: `needs_spec` / `needs_tasks` items in `full_queue_drain` are restricted to planning or blocked/deferred states | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`
- [ ] `SP37-T002` Owner: fixtures | Done when: handoff and false-complete full-queue fixtures cover remaining `needs_spec` work | Verify: `python3 -m json.tool examples/fixtures/runtime-full-queue-handoff-needs-spec.json >/dev/null` and `python3 -m json.tool examples/fixtures/runtime-full-queue-false-complete-needs-spec.json >/dev/null`
- [ ] `SP37-T003` Owner: tests | Done when: runtime ledger tests cover missing spec, umbrella coverage, waiting CI, and remaining needs_spec cases | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`
- [ ] `SP37-T004` Owner: coordinator | Done when: PR #36 links GH-37 and fresh PR gate evidence includes `linked_issue: 37` | Verify: `python3 checks/pr_gate.py --repo . --evidence <evidence.json> --json`

## 并行拆分

- Checks lane: `checks/runtime_ledger_gate.py`,
  `tests/test_runtime_ledger_gate.py`.
- Fixture lane:
  `examples/fixtures/runtime-full-queue-handoff-needs-spec.json`,
  `examples/fixtures/runtime-full-queue-false-complete-needs-spec.json`.
- Coordinator lane: `specs/GH37/*` and PR #36 body.

These lanes overlap only at final verification.

## 验证

- `python3 -m py_compile checks/runtime_ledger_gate.py tests/test_runtime_ledger_gate.py`
- `python3 -m json.tool examples/fixtures/runtime-full-queue-handoff-needs-spec.json >/dev/null`
- `python3 -m json.tool examples/fixtures/runtime-full-queue-false-complete-needs-spec.json >/dev/null`
- `python3 checks/runtime_ledger_gate.py --checkpoint examples/fixtures/runtime-full-queue-handoff-needs-spec.json`
- `python3 checks/runtime_ledger_gate.py --checkpoint examples/fixtures/runtime-full-queue-false-complete-needs-spec.json; test $? -ne 0`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 -m pytest -q`

## Handoff Notes

Use `Fixes #37` in PR #36 only after the spec packet is present and current
verification evidence has passed.
