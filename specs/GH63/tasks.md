# Task Plan

## Linked Issue

GH-63

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] Write the "Safe merge path" protocol (neutral cwd + `--repo`, API
      fallback, remote confirmation, worktree prune) into
      `skills/specrail-implement-queue/SKILL.md`.
- [ ] Add `merge_path`, `remote_confirmed`, `merge_commit_sha`,
      `branch_deletion_outcome` to `schemas/pr_review_gate.schema.json`.
- [ ] Enforce remote-confirmation and merge-path requirements in
      `checks/pr_gate.py`.
- [ ] Add worktree-cleanup report line to
      `templates/tranche_checkpoint.md`.
- [ ] Add fixtures (2 pass, 2 fail) and unit tests; update CHANGELOG.

## Parallelization

- Lane A: `checks/pr_gate.py` + tests + fixtures.
- Lane B: schema file.
- Lane C: skill markdown + template + CHANGELOG.
Disjoint files; `merge_path` enum agreed first.

## Verification

- [ ] `python3 -m pytest -q tests/`
- [ ] `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] Unconfirmed-merge fixture demonstrably fails; api-fallback fixture
      passes.

## Handoff Notes

Related to #55 (branch naming / duplicate-work gate): branch lifecycle
discipline reduces how often worktrees own PR branches in the first place;
this spec handles the residual merge-stage case. Never delete another
session's worktree as part of the fallback — prune only reports/cleans
stale entries.
