# Agent First Review

Agent review is advisory. It must produce findings and evidence, not final
approval.

## Check

- Scope matches linked issue and spec.
- Implementation satisfies acceptance criteria.
- Tests cover changed behavior.
- User-visible behavior is not silently degraded.
- Security-sensitive areas are identified.
- PR template is complete.
- Release note need is explicit.

## Output

Return advisory structured findings. For simple chat review, use:

```json
{
  "verdict": "findings|no_findings",
  "blocking_findings": [],
  "non_blocking_findings": [],
  "missing_evidence": [],
  "recommended_human_reviewers": []
}
```

For a file artifact that should be checked before posting or handoff, use
`schemas/review_result.schema.json` and validate it against the diff:

```sh
python3 checks/review_json_gate.py --repo . --review artifacts/review/pr-<pr-number>.json --diff <patch> --json
```

Inline comments must reference real diff `path`, `line`, and `side` values.
Severity must be `critical`, `important`, `suggestion`, or `nit`.

Top-level `body` must include `## Summary` and `## Verdict` headings. A
multi-line inline comment may add `start_line` and `start_side`, but those fields
must appear together and every line in the inclusive range must exist in the
diff. Suggested changes may use a non-empty `suggestion` field, a non-empty
fenced `suggestion` block in `body`, or both; suggestions are only valid on
RIGHT-side comments.

## Bounded Review Contract

<!-- specrail-bounded-review-contract-v1:start -->
Bounded review contract (`manifest.version: 2`,
`round_policy: {name: "bounded_diff_v1", cap: 3}`):

- `rounds[]` is the source of truth. Each entry is the closed set
  `{artifact_id, review_round, review_mode, base_head_sha, head_sha, diff_sha256, escalation_authorization_id}`;
  the loader derives continuous rounds `1..N` from the artifact set.
- Round 1 may use `full`. Every `review_round >= 2` must use `review_mode:
  resumed | diff_only`, never `full`; `base_head_sha` must equal the previous
  round's `head_sha`, and the supplied bytes and `diff_sha256` must match the
  exact `git diff --no-ext-diff --binary <base_head_sha>..<head_sha> --` output.
- `prior_findings[]` is compact typed carry only:
  `{finding_id, source_artifact_id, status, evidence_pointer}` with
  `evidence_pointer.kind: thread | comment | artifact | commit`; do not replay
  historical finding prose. Carry every still-unresolved historical finding.
- Before every `review_round >= 4`, stop. Continue exactly once only with an
  external, role-mapped maintainer authorization whose `decision` is
  `continue_once` and whose id, PR, prior/target heads, and round match exactly.
- The over-cap `round_cap_escalation.unresolved_findings[]` must equal the full
  union of historical unresolved findings and current critical, important, or
  otherwise actionable findings; no finding may disappear or be invented.
- `auth_mode: auto` merge authorization and `human_full_review_request` do not
  authorize an over-cap review round and cannot replace that exact cap evidence.
<!-- specrail-bounded-review-contract-v1:end -->

## Boundary

Do not approve, merge, close issues, or mark security findings public.
