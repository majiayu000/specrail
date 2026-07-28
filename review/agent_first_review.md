# Agent First Review

Agent review is advisory. Check linked scope, acceptance criteria, changed
behavior, tests, degradation, and security-sensitive paths.

Use the v3 artifact in `schemas/review_result.schema.json` and validate it:

```sh
python3 checks/review_json_gate.py --repo . \
  --review artifacts/review.json --diff artifacts/review.patch --json
```

The canonical compact contract lives in
`skills/specrail-review-pr/SKILL.md`; do not copy it here. Current P0/P1 blocks,
P2/P3 is follow-up, and outdated hosted findings do not block.

Do not approve, merge, close Issues, or publish security findings.
