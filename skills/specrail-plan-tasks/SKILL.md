---
name: specrail-plan-tasks
description: Use when turning an approved SpecRail product and technical spec into the numbered `tasks.md` plan. Creates stable task IDs, owners, done-when conditions, verification commands, dependencies, and handoff notes without implementing the tasks. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Plan Tasks

Use this skill to create or update the task plan before implementation.

## Steps

1. If `workflow.yaml` is absent, report `not_adopted` and use repository-native
   checks. Planning must not call the implementation route before `tasks.md`
   exists.
2. Resolve the issue's product, tech, task, and packet paths from
   `workflow.yaml` `artifacts.*` templates; call the rendered packet path
   `<configured-spec-packet-dir>` and never assume a `specs/` root.
3. Read the resolved product and tech files.
4. Read `templates/<locale>/tasks.md` or `templates/tasks.md`.
5. Write the resolved `artifacts.task_plan` path.
6. Use stable task IDs such as `SP<issue-number>-T1`.
7. Collect every `B-xxx` invariant from `product.md`, then map each one to at
   least one implementation or verification task using `Covers: B-xxx`.
8. For every task, include owner, dependencies, done-when evidence, verify
   commands, and its `Covers:` field.
9. Separate implementation tasks from verification and handoff notes.
10. Validate the completed packet:

```sh
python3 checks/check_workflow.py --repo . \
  --spec-dir=<configured-spec-packet-dir>
```

11. Only after `tasks.md` passes validation, collect current issue evidence and
    run the required implementation preflight for the handoff:

```sh
python3 checks/github_issue_evidence.py --repo . --github-repo OWNER/REPO \
  --issue <issue-number> --json > issue-evidence.json
python3 checks/route_gate.py --repo . --route implement --issue <issue-number> \
  --github-repo OWNER/REPO --profile heavy --evidence issue-evidence.json \
  --approved-spec-revision <40-char-sha> \
  --mode required --json
```

Continue to implementation only when the route decision is `allowed`; otherwise
report every missing item in the planning handoff.

## Invariant coverage

- The union of task `Covers:` fields must include every `B-xxx` in
  `product.md`; a missing ID blocks completion of the task plan.
- A task may cover several invariants, and an invariant may require several
  tasks. Keep the mapping explicit on each affected task.
- Use `Covers: none` only for infrastructure or housekeeping that implements
  no product invariant, and include a concrete reason on the same task.
- Boundary-checklist N/A verdicts have no `B-xxx` IDs and therefore need no
  task mapping. Never invent an ID only to make the coverage sets match.
- Before finishing, compare the product ID set with the task coverage union
  and report both sets in the handoff when any mismatch remains.

## Boundaries

- Do not implement while planning tasks.
- Do not remove human gates for readiness, spec approval, final review, merge,
  release, or security decisions.
- Do not mark a task plan complete while a product invariant is absent from
  the task coverage union.
- Keep the plan small enough for one agent or a clearly partitioned thread lane.
- Fix every reported rejection item before one bounded retry; do not persist a
  parallel retry ledger.
