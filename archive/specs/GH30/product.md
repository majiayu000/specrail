# Product Spec

## Linked Issue

GH-30
status: legacy

## Problem

Agents can already use `specrail-implement-queue` for approved-spec queues, but
some maintainers want a shorter operational trigger. In practice, they say
`implx` or `use implx` and expect the agent to run the whole SpecRail queue
workflow: issue and PR mapping, optional threads lanes, per-issue
implementation, PR gates, merge authorization, and closure audit.

Without a repo-distributed shortcut, that expectation depends on local memory or
personal prompts instead of a reusable SpecRail artifact.

## Goals

- Add an `implx` repo-distributed skill as a shortcut entrypoint.
- Keep `implx` thin: it should route to existing SpecRail and threads workflow
  assets instead of duplicating their full instructions.
- Preserve SpecRail's human-gate boundaries, especially final approval and merge
  authorization.
- Keep the shortcut generic for any SpecRail-adopting repository.

## Non-Goals

- Do not replace `specrail-implement-queue`.
- Do not require a local threads installation.
- Do not add automatic merge, final approval, force-push, or issue-close
  authority.
- Do not hardcode Sage, issue ranges, excluded product areas, local paths, or
  user-specific banned strings.
- Do not add scripts or automation beyond skill routing guidance.

## Behavior Invariants

1. `implx` starts from fresh repository, GitHub issue, PR, spec, and remote
   truth.
2. `implx` routes approved-spec queues to `specrail-implement-queue`.
3. `implx` uses threads only as an orchestration layer when queue gates, lane
   maps, independent reviewers, merge gates, or closure audits are needed.
4. `implx` never bypasses SpecRail route gates, PR gates, review-thread checks,
   or human merge authorization.
5. `implx` falls back to normal single-agent SpecRail flow when no native
   threads capability is available, and reports that fallback explicitly.

## Acceptance Criteria

- [ ] `skills/implx/SKILL.md` exists with trigger metadata for `implx`,
      `use implx`, and Chinese equivalents such as `用 implx`.
- [ ] `skills/implx/SKILL.md` routes to `specrail-implement-queue`,
      `integrations/threads.md`, per-issue implementation, PR gates, and closure
      audit without copying all detailed instructions.
- [ ] `skills/specrail-workflow/SKILL.md` mentions `implx` as an explicit
      shortcut route.
- [ ] `skills-lock.json` pins the new skill and updated skill hashes.
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` passes.
- [ ] Existing tests continue to pass.

## Edge Cases

- A repository has no approved `specs/GH<issue>/` packets: stop at SpecRail
  planning/spec work instead of implementing.
- Open PRs already cover some issues: map and review those PRs before creating
  replacements.
- The user says `implx` but does not authorize merge: prepare PRs and merge
  readiness evidence, then stop before merge.
- Native threads tools are unavailable: continue single-agent and report
  `no native threads launched`.

## Release Note

Add `implx`, a short SpecRail shortcut skill for approved-spec issue and PR
queues that routes through existing queue, threads, implementation, gate, and
closure-audit workflows.
