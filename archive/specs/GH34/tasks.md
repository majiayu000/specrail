# Task Plan

## Linked Issue

GH-34

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP34-T001` Owner: checks | Done when: `checks/runtime_ledger_gate.py` validates runtime checkpoint JSON and blocks invalid merge-ready evidence | Verify: `python3 -m pytest -q tests/test_runtime_ledger_gate.py`
- [ ] `SP34-T002` Owner: checks | Done when: top-level checkpoint fields `tranche_id`, `repo`, `scope`, `status`, and `resume_prompt` are validated by the CLI gate, not only by schema prose | Verify: invalid checkpoint reproduction returns `blocked`
- [ ] `SP34-T003` Owner: schema | Done when: `schemas/runtime_checkpoint.schema.json` documents required checkpoint fields and item evidence | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP34-T004` Owner: docs | Done when: README, AGENT_USAGE, integrations/threads, and AGENTS document runtime checkpoints, context budget, output firewall, and canonical truth boundaries | Verify: inspection and workflow validation pass
- [ ] `SP34-T005` Owner: skills | Done when: `implx`, `specrail-implement-queue`, and `specrail-workflow` preserve the same long-run boundaries | Verify: `skills-lock.json` hash validation passes
- [ ] `SP34-T006` Owner: coordinator | Done when: PR #32 links GH-34 and validation evidence is current | Verify: PR body, CI, and local checks

## 并行拆分

- Checks lane: `checks/runtime_ledger_gate.py`,
  `tests/test_runtime_ledger_gate.py`.
- Docs/templates lane: `README.md`, `AGENT_USAGE.md`, `AGENTS.md`,
  `integrations/threads.md`, `templates/*tranche_checkpoint.md`.
- Skills lane: `skills/implx/SKILL.md`,
  `skills/specrail-implement-queue/SKILL.md`,
  `skills/specrail-workflow/SKILL.md`, `skills-lock.json`.

These lanes overlap at verification time only; one coordinator owns final
validation and PR body updates.

## 验证

- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 -m pytest -q`
- `git diff --check`
- Invalid-checkpoint regression returns `blocked`
- `python3 checks/pr_gate.py --repo . --evidence <evidence.json> --json`

## Handoff Notes

Use `Fixes #34` only after the runtime checkpoint gate, schema/templates,
long-run queue guidance, refreshed skill hashes, and validation evidence are in
PR #32.
