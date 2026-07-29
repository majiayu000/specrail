# Product Spec

## Linked Issue

GH-28
status: legacy

## Problem

SpecRail has focused route skills for single issue implementation and PR gates,
but it does not have a focused entrypoint for implementing a queue of already
approved specs. Agents currently have to assemble `specrail-implement`,
`specrail-pr-gate`, `specrail-check-impl-against-spec`, and optional threads
instructions by hand.

That gap makes it easy to miss issue-to-PR mapping, partial versus final closing
keywords, independent reviewer lanes, and closure audit evidence.

## Goals

- Add a generic SpecRail implementation queue skill.
- Preserve the boundary where SpecRail owns policy, artifacts, locale, human
  gates, and deterministic checks.
- Use threads only as an optional orchestration layer for queues, parallel lanes,
  review-thread checks, merge gates, and closure audit.
- Keep single-issue implementation routed to the existing `specrail-implement`
  skill.
- Keep the skill generic for any SpecRail-adopting repository.

## Non-Goals

- Do not vendor or require a local threads skill.
- Do not add automatic merge or final approval authority.
- Do not hardcode any consumer repo paths, issue numbers, product exclusions,
  banned typo strings, language defaults, or build tools.
- Do not replace existing focused route skills.

## Behavior Invariants

1. Queue implementation starts from fresh issue, PR, spec, and remote truth.
2. Existing PRs covering an issue are mapped before opening replacement PRs.
3. Each implementation PR is tied to exactly one issue unless the spec explicitly
   allows a combined slice.
4. Partial PRs use non-closing references; final issue-closing PRs use closing
   keywords only after every acceptance criterion is implemented and verified.
5. Threads may orchestrate lanes, but it cannot override SpecRail human gates.
6. Merge readiness requires current head, CI, review threads, merge state, and
   PR-gate evidence.

## Acceptance Criteria

- [ ] `skills/specrail-implement-queue/SKILL.md` exists with trigger metadata
      for approved-spec issue queues.
- [ ] `skills/specrail-workflow/SKILL.md` routes implementation queues to the
      new skill.
- [ ] `integrations/threads.md` documents the approved-spec implementation queue
      handoff.
- [ ] `skills-lock.json` pins the new skill.
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` passes.
- [ ] Existing tests continue to pass.

## Edge Cases

- A queue has open PRs already covering some issues: classify and continue with
  those PRs before opening competing work.
- A task needs several PRs for one issue: use `Refs #NN` until the final
  acceptance criteria are complete.
- No threads skill is available: continue with the single-agent SpecRail flow
  and report that no native threads were launched.
- CI is green but review threads are unresolved: do not report merge readiness.

## Release Note

Add a repo-distributed SpecRail skill for implementing approved-spec issue
queues while keeping threads as an optional orchestration integration.
