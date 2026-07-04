# Tech Spec

## Linked Issue

GH-63

## Product Spec

`specs/GH63/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue skill | `skills/specrail-implement-queue/SKILL.md` | Owns merge/closure flow; no worktree-safe path | Contract text home |
| pr gate | `checks/pr_gate.py` | Validates merge-readiness evidence | Merge-path evidence enforcement |
| schema | `schemas/pr_review_gate.schema.json` | Gate evidence structure | Gains merge-path fields |
| implx | `skills/implx/SKILL.md` | Lists worktrees at startup | Startup inventory feeds cleanup |
| checkpoint template | `templates/tranche_checkpoint.md` | Closure/handoff format | Worktree-cleanup report line |

## Proposed Design

1. Skill text (`specrail-implement-queue`, merge/closure section), the
   "Safe merge path" protocol:
   a. run merge from a neutral cwd with explicit `--repo`;
   b. on local ownership errors (`branch ... is checked out at ...`,
      worktree lock), fall back to
      `gh api -X PUT /repos/{owner}/{repo}/pulls/{n}/merge` with the repo's
      allowed merge method (query merge settings first);
   c. always confirm via remote query (`gh pr view --json merged,mergeCommit`)
      before recording success or failure;
   d. post-merge: separate branch-deletion step; `git worktree prune` in each
      local checkout used during the tranche; list stale/removed worktrees in
      the closure report.
2. Evidence: extend `schemas/pr_review_gate.schema.json` merge records with
   `merge_path` (`gh_pr_merge` | `api_fallback` | `merged_by_other`),
   `remote_confirmed` (bool), `merge_commit_sha`, and optional
   `branch_deletion_outcome`.
3. `checks/pr_gate.py`: a merge record with `remote_confirmed` absent/false,
   or missing `merge_path`, is a blocking violation; `merged_by_other` is a
   valid confirmed terminal.
4. Fixtures: gh-pr-merge-confirmed (pass), api-fallback-confirmed (pass),
   local-failure-recorded-as-merge-failure without remote query (fail),
   missing merge_path (fail).

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | skill protocol step (a) | doc review + check_workflow |
| P2 | skill protocol step (b) | doc review; fallback fixture passes |
| P3 | `remote_confirmed` requirement in pr_gate | unconfirmed fixture fails |
| P4 | closure worktree-prune step + template line | doc review |
| P5 | `merge_path` + confirmation fields | missing-field fixture fails |

## Data Flow

Merge attempt (local gh or API) -> remote confirmation query -> merge record
written into gate/closure evidence -> `checks/pr_gate.py` validates locally.
The only network calls are the ones agents already make (gh); the check
itself stays offline.

## Alternatives Considered

- Shipping a `safe_merge.sh` helper script: rejected — SpecRail is a
  contract pack (consistent with prior non-goals); scripts drift from the
  runtimes that consume the contract.
- Always using the API path (skip `gh pr merge` entirely): considered
  viable but rejected as the default — `gh pr merge` handles merge-method
  and match-head-commit ergonomics well when no worktree owns the branch;
  fallback ordering keeps the common path simple.
- Deleting the offending worktree before merging: rejected — the worktree
  may belong to another live session (W-14-style ownership); merging must
  not destroy someone else's workspace.

## Risks

- Security: none new; API fallback uses existing gh auth.
- Compatibility: additive evidence fields; older records exempt via
  contract-version keying.
- Performance: one extra remote confirmation query per merge.
- Maintenance: gh error-message matching for ownership errors can drift with
  gh versions; the contract keys the fallback on "local ownership failure
  class", with current known message patterns listed as examples, not an
  exhaustive match list.

## Test Plan

- [ ] Unit tests: pr_gate matrix over (merge_path, remote_confirmed,
      merge_commit_sha) combinations.
- [ ] Integration tests: `python3 checks/check_workflow.py --repo . --all-specs`.
- [ ] Manual verification: dry-run the documented protocol against a test PR
      in a sandbox repo with a deliberately checked-out head branch.

## Rollback Plan

Revert gate rule and schema fields in separate commits; skill section reverts
independently. No local state to migrate; per-session memory notes remain
valid interim guidance if reverted.
