---
name: specrail-write-product-spec
description: Use when writing or updating a SpecRail product spec for a linked issue. Produces the numbered `product.md` spec from the locale-appropriate template, focusing on user-facing behavior, goals, non-goals, and acceptance criteria without implementation detail. Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language.
---

# SpecRail Write Product Spec

Use this skill for the product half of the `write_spec` route.

## Steps

1. Confirm the linked issue number. Search first if no issue is provided.
2. Read `workflow.yaml`, `states.yaml`, `labels.yaml`, and the relevant product
   spec template from `templates/<locale>/product_spec.md` or
   `templates/product_spec.md`.
3. If `workflow.yaml` is absent, report `not_adopted` and use repository-native
   checks. If it exists, the route gate is mandatory; a missing checker blocks:

```sh
python3 checks/github_issue_evidence.py --repo . --github-repo OWNER/REPO \
  --issue <issue-number> --json > issue-evidence.json
python3 checks/route_gate.py --repo . --route write_spec --issue <issue-number> \
  --github-repo OWNER/REPO --evidence issue-evidence.json --mode required --json
```

Continue only when the route decision is `allowed`; stop and report every
other decision and its missing evidence. Do not substitute `--state` or
`--label` for current collector evidence.

4. Pick the depth tier from the length heuristic below, then write
   `specs/GH<issue-number>/product.md`.
5. Keep product content about observable behavior: goals, non-goals, behavior
   invariants, acceptance criteria, edge cases, and open questions.
6. Write behavior as numbered, testable invariants without implementation
   detail, following the density rule and the worked example below.
7. Fill the boundary checklist: every category is either covered by a named
   invariant or explicitly marked N/A with a reason.
8. Keep implementation approach, file ownership, test commands, and rollout
   mechanics for the tech spec or task plan.

## Length heuristic

Length follows complexity, never the template. Do not pad a simple change and
do not compress a gate-contract change.

| Tier | Typical change | Spec size |
| --- | --- | --- |
| trivial | single-file fix, no new behavior contract | minimal spec; declare `complexity: trivial` under the Linked Issue heading and keep only the invariants that actually exist |
| small | one behavior, few states | ~30-60 lines |
| medium | new contract, several failure/authorization states | ~80-150 lines |
| large | multi-component contract, state machine, migration | longer as needed |

If a tier feels ambiguous, pick the higher tier: err toward one more edge
case, not one less.

## Stable invariant IDs

- Number invariants `B-001`, `B-002`, ... consecutively.
- Revisions append new IDs; never renumber, and never reuse a published
  `B-xxx` for a different behavior.
- Downstream artifacts reference these IDs: the tech spec maps every `B-xxx`
  to a verification, and task-plan items carry `Covers: B-xxx`.

## Boundary checklist

Enumerate boundaries before writing invariants, then record the verdict per
category in the spec (a table works well). Every category gets either
`covered: B-xxx` or `N/A + reason`. Silent omission is the failure mode this
checklist exists to kill.

1. Empty / missing input (absent fields, empty lists vs missing keys)
2. Error and failure paths (each failure mode, not "errors are handled")
3. Authorization / permission (and every combination with failure states)
4. Concurrency / race / ordering
5. Retry / repetition / idempotency
6. Illegal state transitions
7. Compatibility / migration (old data, old clients, old specs)
8. Degradation / fallback (is the degraded path allowed to look like success?)
9. Evidence and audit integrity (can a claim pass without its prerequisite
   recorded?)
10. Cancellation / interruption / partial completion

Pay special attention to combinations: the historically expensive misses are
rarely single categories — they are cross products like "authorized + no
prerequisite evidence recorded" or "failed + retried + evidence reused".

## Worked example

The invariants below are the density target. They describe a bounded
merge-review gate with risk-based review sources.

> 1. B-001 每个 merge 候选项必须记录 review 来源，取值为闭集
>    {independent_lane, self_review}；缺失、为空或越界取值时该项判为
>    blocked。
> 2. B-002 canonical profile 中 fastlane 使用 self_review，standard/heavy
>    必须使用 independent_lane；任何覆盖 canonical 安全属性的配置一次返回全部
>    问题。
> 3. B-003 review 最多两轮：第一轮必须 full，第二轮只能 diff-only；第三轮
>    返回 needs_human。
> 4. B-004 当前 head 上未解决的 P0/P1 必须阻断，P2/P3 只进入 follow-ups。
> 5. B-005 outdated hosted finding 不得单独阻断当前 head。
> 6. B-006 heavy 候选必须持有绑定当前 head 与当前 gate invocation 的人类
>    merge authorization；旧授权不得复用。
> 7. B-007 CI、review 和 gate query 必须绑定同一个当前 head。
> 8. B-008 gate 对缺失和矛盾证据必须聚合报告，不得逐项失败。
> 9. B-009 负例 fixture 必须 schema 合法但被 gate 拒绝；schema 非法的
>    负例测不到 gate 逻辑，不算覆盖。
> 10. B-010 旧 runtime/tier/review-round artifact 必须返回 unsupported 与
>     重建指令，不得解释为当前授权。
>
> Boundary checklist verdict — Cancellation / interruption: N/A. The gate is
> an offline check with no long-running session state; rerunning it is
> idempotent after interruption. This verdict has no `B-xxx` ID because it is
> not a behavior invariant.

Note how B-006 combines risk classification, current-head identity, invocation
identity, and authorization. Specs that mention those fields independently but
omit the cross-product still permit stale authorization.

## Density rule

Match the density of the worked example, not the emptiness of the template.
The template supplies structure; this skill supplies depth. Filling one or two
bullets under each heading is slot completion, not a spec. A useful self-check
before finishing: for the boundary checklist's combination categories, either
point at the invariant that pins each cross product down, or write the N/A
reason you would defend in review.

## Boundaries

- Do not write a numbered spec without a linked issue unless a human explicitly
  chooses a non-GitHub workflow.
- Do not translate stable IDs, paths, commands, JSON keys, states, or route
  names.
- Keep human-facing product text in the selected locale; invariant phrasing
  may use natural "当/若…系统应…" or "When/If … the system shall …" style in
  either locale.
- Do not invent invariants to satisfy a length target; the heuristic bounds
  effort, it is not a quota.
- Fix every reported rejection item before one bounded retry. Do not persist a
  parallel retry ledger.
