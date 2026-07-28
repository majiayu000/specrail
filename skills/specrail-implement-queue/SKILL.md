---
name: specrail-implement-queue
description: Use only when implx delegates a GitHub issue/PR queue or the user names this skill. Drain actionable SpecRail work while preserving one-issue ownership, current GitHub truth, bounded review, verification, and human merge/security gates.
---

# SpecRail Implement Queue

This is the full-queue worker for explicit `implx` requests. For one named
issue, prefer `skills/specrail-implement/SKILL.md`.

## Startup

1. Read `AGENTS.md`, `workflow.yaml`, this skill, and current GitHub
   issues/PRs/branches. Existing PRs and remote branches are ownership facts.
2. Classify every candidate as `fastlane`, `standard`, or `heavy`.
3. Search for duplicates before creating work. Duplicate results are advisory:
   show the warning and avoid knowingly replacing another owner's work.
4. Record a bounded tranche with issue, profile, owner, done-when, verification,
   current branch/PR, blocker, and next action. GitHub is durable truth.

Optional handoff cursors may contain only:

```yaml
completed: []
pending: []
blocked: []
artifact_refs: []
resume_action: ""
```

The cursor is not a gate. Refresh GitHub before resuming.

## Profiles

- `fastlane`: small mechanical/docs/test fix, no sensitive path. Linked Issue,
  focused diff, project tests, one review, and human merge boundary. No spec
  packet is required.
- `standard`: normal feature/fix. Linked Issue, testable plan, project tests,
  one full review, and at most one diff-only re-review after P0/P1 fixes. A
  spec packet is optional.
- `heavy`: architecture, public contract, migration, workflow enforcement, auth,
  secrets, payments, or any sensitive-registry match. Require approved
  `product.md`, `tech.md`, `tasks.md`, independent review, security evidence,
  and explicit current-invocation human merge authorization. The trusted
  readiness label records spec approval; security evidence is content-bound to
  an exact maintainer-supplied approved revision and fails closed when any
  product/tech/tasks content is missing or drifted. Never infer that revision.

Sensitive classification always upgrades to `heavy`; ambiguity also chooses the
heavier profile.
The canonical profile policy controls review source and hosted-thread
collection: fastlane is self-review; standard/heavy are independent.

## Queue Rules

- One issue per implementation PR by default. Map an existing PR before creating
  a branch or replacement PR.
- Use `Refs #N` for partial slices; use a closing keyword only on the final slice
  that satisfies all acceptance criteria.
- `needs_info` and `parked` are skipped. Missing or open-ended done-when goes to
  `human_decisions`, not implementation.
- For heavy work, draft missing specs/tasks with focused SpecRail skills, then
  wait for required human confirmation. Fastlane/standard do not get spec-only
  PRs by default.
- Never convert P2/P3 review findings into new Issues automatically. Record them
  in the current PR/Issue follow-up section.
- A blocked item does not end a full drain. Refresh truth and select another
  independent item. Finish only when remaining items each have a blocker and
  next action.

## Implementation

Run the route gate with the selected profile:

```sh
python3 checks/github_issue_evidence.py --repo . --github-repo OWNER/REPO \
  --issue <n> --json > issue-evidence.json
python3 checks/route_gate.py --repo . --route implement --profile <profile> \
  --issue <n> --github-repo OWNER/REPO --evidence issue-evidence.json \
  --mode required --json
```

For `heavy`, append the exact maintainer-supplied
`--approved-spec-revision <40-char-sha>`.
Continue only when the route decision is `allowed`.

Load `skills/specrail-workflow/SKILL.md` only if routing is ambiguous. Load
`skills/specrail-implement/SKILL.md` for implementation. Keep worktrees and file
ownership disjoint when native threads are explicitly in use.

Duplicate evidence is optional advisory context:

```sh
python3 checks/github_duplicate_evidence.py --github-repo OWNER/REPO \
  --issue <n> --json > duplicate.json
```

## Review

Load `skills/specrail-review-pr/SKILL.md` before review; do not copy it here.
One reviewer lane per PR is the default. The canonical
`requires_independent_review` policy selects self-review for fastlane and
`independent_lane` plus hosted-thread collection for standard/heavy.

- Round 1: `full`.
- Round 2: `diff_only`, only after P0/P1 fixes and only for the blocker
  finding's predeclared `path` or `fix_paths`; extra paths require a new full
  review.
- Round >2: `needs_human`.
- Current unresolved P0/P1 blocks.
- P2/P3 are non-blocking follow-ups.
- Outdated hosted findings do not block.

Use `checks/review_json_gate.py` for the artifact. The skill is advisory and
cannot approve or merge. Raw current and embedded prior review artifacts never
contain `review_attestation`; the trusted host supplies one separate current
attestation, which also binds prior artifact ID and head for round 2.

## PR Gate

Collect current evidence, then run the compact gate:

```sh
python3 checks/github_pr_evidence.py --github-repo OWNER/REPO --pr <n> \
  --issue <issue> --profile <profile> --gate-invocation-id <id> \
  --review <review.json> --review-attestation <host-attestation.json> \
  --json > pr-evidence.json
python3 checks/pr_gate.py --repo . --evidence pr-evidence.json --json
```

Current head, linked Issue, successful CI, clean merge state, compact review,
profile, and sensitive classification must agree. Heavy additionally requires
the current invocation's human authorization. Never run evidence collection and
merge in one parallel batch.

The trusted host/coordinator injects the head-and-invocation-bound review
attestation for standard/heavy; implementation and review agents must not mint,
edit, copy, persist, or reuse it. Fastlane self-review omits that flag.

## External Actions

Push, create/update PR, comment, label, close, approve, merge, and release only
when the user's authorization covers that exact action. Never force-push or
publish security details. Report `allowed`, `needs_human`, and `blocked`
literally; an allowed advisory gate still does not grant final approval.

## Completion

For every completed item report:

- linked Issue and PR;
- profile and current head;
- acceptance coverage;
- fresh verification commands;
- review decision and follow-ups;
- remaining blockers/human decisions.

Before declaring the queue drained, refresh GitHub once more and reconcile every
open actionable Issue/PR.
