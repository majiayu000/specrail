# AGENTS.md

This repository defines reusable repository workflow contracts. Keep changes
small, explicit, and verifiable.

## Agent Entry

- Treat SpecRail as an agent-facing workflow contract, not a human project
  management guide.
- Read `AGENT_USAGE.md` before creating issues, specs, PRs, reviews, or
  handoffs.
- Use `PLAN.md` for current direction, known limits, and roadmap.
- When the user writes Chinese or the selected locale is `zh-CN`, write
  human-facing issue/spec/PR/handoff text in Chinese while keeping stable IDs,
  paths, commands, and JSON keys in English.

## Rules

- Search before adding a new workflow, schema, template, check, or policy.
- Prefer deterministic checks before LLM or agent automation.
- Do not grant agents final approval, merge, or security-disclosure authority.
- Keep templates generic; repository-specific behavior belongs in examples or
  consumer overlays.
- Preserve the dry-run default for all GitHub automation.

## Contract Size Discipline (GH-208)

- Hard line caps, enforced by `checks/skill_size_gate.py` in CI:
  `skills/specrail-implement-queue/SKILL.md` ≤ 200,
  `skills/implx/SKILL.md` ≤ 60, every other `skills/*/SKILL.md` ≤ 200.
  Fastlane startup reads at most three files and 12 KiB.
- One-in-one-out: when a contract file is at its cap, adding a new clause
  requires deleting or condensing an equal amount of existing text in the
  same PR. Never raise a cap to make room.
- Every new gate module in `checks/` must name its motivating incident
  (issue number) and expected interception scenario in its docstring. A
  gate with no real interception in 30 days and no security property is a
  candidate for downgrade to warning or deletion at the next audit
  (`docs/GATE_AUDIT_*.md`).

## Long Queue Guardrails

- For approved-spec issue/PR queues, route through `skills/implx/SKILL.md` and
  `skills/specrail-implement-queue/SKILL.md`; use `integrations/threads.md`
  when native threads, reviewer lanes, CI waits, or closure audit are needed.
- Keep long runs bounded to a named tranche. Optional handoff cursors contain
  only completed/pending/blocked IDs, artifact references, and a resume action;
  they never participate in gates.
- Large command output belongs in artifacts, not parent context. Parent-visible
  evidence should be command status, short summaries, bounded tails, and paths.
- Do not read raw Codex session JSONL or old parent transcripts as live queue
  state unless the user explicitly asks for forensic analysis.

## Validation

Run before completion after changing workflow assets:

```sh
python3 checks/check_workflow.py --repo .
```
