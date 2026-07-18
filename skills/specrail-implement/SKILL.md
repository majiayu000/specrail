---
name: specrail-implement
description: Use when implementing a SpecRail-governed issue after the implementation gate. Executes the scoped task plan, keeps changes tied to linked specs and acceptance criteria, runs deterministic verification, and preserves human approval, merge, and security boundaries. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Implement

Use this skill for the `implement` route.

## Steps

1. Read the linked issue, product spec, tech spec, and task plan.
2. Run the implementation route gate when available:

```sh
python3 checks/route_gate.py --repo . --route implement --issue <issue-number> --state ready_to_implement --json
```

3. If the gate returns `needs_human` or `blocked`, stop and report the missing
   evidence or gate.
4. Implement only the scoped tasks. Search before adding files, workflows,
   schemas, templates, policies, or public APIs.
5. Keep machine-facing IDs in English and human-facing text in the selected
   locale.
6. Run focused verification for touched behavior, then run the pack check when
   workflow assets changed:

```sh
python3 checks/check_workflow.py --repo .
```

7. Record changed files, commands, results, and remaining human gates.

## Boundaries

- Do not provide final approval.
- Do not merge without explicit human authorization and a passing PR gate.
- Do not publish secrets or private security details.
- Do not weaken tests or deterministic checks to make implementation pass.

## Rejection Persistence And Retry

When a gate command in this skill (`checks/route_gate.py`,
`checks/review_json_gate.py`, or `checks/pr_gate.py`) rejects with a decision
other than `allowed`, the caller persists the gate's JSON output to
`.specrail/runtime/rejections/<gate>-<issue|pr>.json` (create the directory if
missing). This write is orchestrator behavior; the gate itself stays
read-only. Use the `rejection_items[]` list to fix every defect in a single
round instead of guessing one item per retry.

On the next retry of the same gate for the same issue or PR, pass
`--prior-rejection .specrail/runtime/rejections/<gate>-<issue|pr>.json`. If
the new output contains a `repeat_rejection` section, the same item was
rejected verbatim twice: stop retrying and report the contract violation to a
human instead of starting another round.
