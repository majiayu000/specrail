---
name: specrail-implement
description: Use when implementing a SpecRail-governed issue after the implementation gate. Executes the scoped task plan, keeps changes tied to linked specs and acceptance criteria, runs deterministic verification, and preserves human approval, merge, and security boundaries. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Implement

Use this skill for the `implement` route.

## Steps

1. Read the linked issue and selected verification profile. Read the complete
   product/tech/tasks packet when the profile is `heavy`; for `fastlane` and
   `standard`, use the smallest current plan that makes done-when testable.
2. If `workflow.yaml` is absent, report `not_adopted` and use repository-native
   checks. If it exists, the route gate is mandatory; a missing checker blocks:

```sh
python3 checks/github_issue_evidence.py --repo . --github-repo OWNER/REPO \
  --issue <issue-number> --json > issue-evidence.json
python3 checks/route_gate.py --repo . --route implement --issue <issue-number> \
  --profile <fastlane|standard|heavy> --evidence issue-evidence.json \
  --mode required --json
```

3. Continue only when the gate returns `allowed`; stop and report every other
   decision and its missing evidence.
4. Implement only the scoped tasks. Search before adding files, workflows,
   schemas, templates, policies, or public APIs.
5. Keep machine-facing IDs in English and human-facing text in the selected
   locale.
6. Run focused verification for touched behavior, then run the pack check when
   workflow assets changed:

```sh
python3 checks/check_workflow.py --repo .
```

7. For a GitHub PR, review the exact current-head diff, validate the compact
   review JSON with `checks/review_json_gate.py`, collect current PR evidence,
   then run `checks/pr_gate.py` serially. Use an independent review source when
   the selected profile's configured `requires_independent_review` policy is
   true. A current P0/P1 blocks.
8. Record changed files, commands, results, and remaining human gates.

## Boundaries

- Do not provide final approval.
- Do not merge without explicit human authorization and a passing PR gate.
- Do not publish secrets or private security details.
- Do not weaken tests or deterministic checks to make implementation pass.
- Fix every reported rejection item before one bounded retry. If the same
  rejection repeats, stop and report it instead of creating persistent retry
  state.
