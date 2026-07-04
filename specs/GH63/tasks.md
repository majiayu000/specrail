# Task Plan

## Linked Issue

GH-63

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP63-T001` Owner: queue_skill | Done when: `skills/specrail-implement-queue/SKILL.md` documents the safe merge path with neutral cwd, explicit `--repo`, API fallback, remote confirmation, and worktree prune reporting | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP63-T002` Owner: schema | Done when: `schemas/pr_review_gate.schema.json` includes `merge_path`, `remote_confirmed`, `merge_commit_sha`, and `branch_deletion_outcome` evidence fields | Verify: `python3 checks/check_workflow.py --repo . --spec-dir specs/GH63`
- [ ] `SP63-T003` Owner: pr_gate | Done when: `checks/pr_gate.py` enforces remote confirmation and merge-path evidence requirements | Verify: `python3 -m pytest -q tests/`
- [ ] `SP63-T004` Owner: checkpoint_template | Done when: `templates/tranche_checkpoint.md` includes a worktree-cleanup report line | Verify: inspection and workflow validation pass
- [ ] `SP63-T005` Owner: tests | Done when: pass and fail fixtures plus unit tests cover unconfirmed merge evidence and API fallback evidence | Verify: `python3 -m pytest -q tests/`
- [ ] `SP63-T006` Owner: changelog | Done when: `CHANGELOG.md` records the safe merge path and branch cleanup evidence requirement | Verify: inspection and workflow validation pass

## Parallelization

- Lane A: `checks/pr_gate.py` + tests + fixtures.
- Lane B: schema file.
- Lane C: skill markdown + template + CHANGELOG.
Disjoint files; `merge_path` enum agreed first.

## Verification

- `python3 -m pytest -q tests/`
- `python3 checks/check_workflow.py --repo . --all-specs`
- Unconfirmed-merge fixture demonstrably fails; api-fallback fixture passes.

## Handoff Notes

Related to #55 (branch naming / duplicate-work gate): branch lifecycle
discipline reduces how often worktrees own PR branches in the first place;
this spec handles the residual merge-stage case. Never delete another
session's worktree as part of the fallback — prune only reports/cleans
stale entries.
