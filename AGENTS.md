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

## Long Queue Guardrails

- For approved-spec issue/PR queues, route through `skills/implx/SKILL.md` and
  `skills/specrail-implement-queue/SKILL.md`; use `integrations/threads.md`
  when native threads, reviewer lanes, CI waits, or closure audit are needed.
- Keep long runs bounded to a named tranche. For handoff or compaction, write a
  runtime checkpoint and validate it with `checks/runtime_ledger_gate.py`.
- Large command output belongs in artifacts, not parent context. Parent-visible
  evidence should be command status, short summaries, bounded tails, and paths.
- Do not read raw Codex session JSONL or old parent transcripts as live queue
  state unless the user explicitly asks for forensic analysis.
- Codex Goal may bound the current thread, but it does not replace SpecRail
  artifacts, GitHub truth, or runtime checkpoints.

## Validation

Run before completion after changing workflow assets:

```sh
python3 checks/check_workflow.py --repo .
```
