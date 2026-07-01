# Product Spec

## Linked Issue

GH-34

## 用户问题

SpecRail queue work can span long parent sessions, optional threads lanes,
review gates, CI waits, and handoffs. Without a bounded runtime checkpoint, an
agent can lose tranche scope during compaction, flood parent context with raw
logs, or report queue state from stale transcripts instead of current GitHub and
SpecRail evidence.

## 目标

- Add local runtime checkpoint guidance for long queue tranches.
- Provide a deterministic gate for validating checkpoint shape and merge-ready
  evidence before handoff or resume.
- Document output-firewall behavior so large command output is written to
  artifacts instead of parent context.
- Keep GitHub issues, PRs, labels, reviews, branches, and SpecRail spec packets
  as canonical workflow truth.
- Clarify Codex Goal use without making Goal a replacement for SpecRail
  artifacts or runtime checkpoints.

## 非目标

- Do not add automatic merge, final approval, or issue closure authority.
- Do not make runtime checkpoints a replacement for GitHub or SpecRail state.
- Do not require native threads support.
- Do not read raw Codex session JSONL or old parent transcripts as live queue
  truth.
- Do not add a scheduled automation system.

## Behavior Invariants

1. Long queue work is bounded to a named tranche with explicit scope and
   next_action.
2. Runtime checkpoints are local handoff aids only; canonical workflow truth
   remains GitHub and SpecRail artifacts.
3. Merge-ready checkpoint items require truth_level A, PR number, head SHA,
   green CI evidence, clean review-thread evidence, passed PR gate evidence,
   clean merge state, and explicit merge authorization.
4. Large command output is written to artifacts; parent-visible output is limited
   to exit code, short tails, targeted greps, summaries, and artifact paths.
5. Invalid checkpoint structure, empty required top-level fields, invalid status,
   stale PR gate head SHA, missing review-thread evidence, or missing merge
   authorization blocks the runtime checkpoint gate.

## 验收标准

- [ ] `checks/runtime_ledger_gate.py` validates runtime checkpoint JSON and
      returns `blocked` for invalid checkpoint evidence.
- [ ] `schemas/runtime_checkpoint.schema.json` documents the checkpoint shape.
- [ ] `templates/tranche_checkpoint.md` and
      `templates/zh-CN/tranche_checkpoint.md` provide handoff templates.
- [ ] `AGENTS.md`, `AGENT_USAGE.md`, `README.md`, `integrations/threads.md`,
      `skills/implx/SKILL.md`, and `skills/specrail-implement-queue/SKILL.md`
      document long-run queue guardrails.
- [ ] `skills-lock.json` pins changed skill hashes.
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` passes.
- [ ] `python3 -m pytest -q` passes.

## 边界情况

- Checkpoint has required keys but blank `tranche_id`, `repo`, `scope`, or
  `resume_prompt`: block.
- Checkpoint has a status outside `planning`, `running`, `blocked`, `handoff`,
  or `complete`: block.
- A merge-ready item has stale PR gate head SHA: block.
- CI is green but review-thread evidence is missing: block.
- No native threads capability is available: continue single-agent SpecRail flow
  and record the fallback.

## 发布说明

Adds optional runtime checkpoint guardrails for long SpecRail queue work. This
is a local handoff and verification aid; it does not change merge authority or
replace canonical GitHub and SpecRail workflow state.
