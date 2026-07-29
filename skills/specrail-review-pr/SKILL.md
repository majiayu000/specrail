---
name: specrail-review-pr
description: Perform an advisory review of the current PR head against linked work and repository conventions, reporting concrete findings without approving or merging.
---

# Review PR

1. Fetch the current PR head, base, full diff, linked Issue, review threads, CI
   state, and applicable repository instructions.
2. Review correctness, acceptance coverage, regressions, error handling,
   security, compatibility, tests, and unintended scope.
3. Verify each finding against the current head and cite exact file and line.
4. Classify findings:
   - `P0`: critical security or data-loss risk;
   - `P1`: correctness issue that should block delivery;
   - `P2`: important non-blocking defect or maintainability risk;
   - `P3`: optional improvement.
5. Distinguish unresolved current findings from outdated or already-fixed
   threads.
6. Report a concise summary, findings, verification gaps, and recommended next
   action.

The review is advisory. Do not modify, approve, merge, close, or publish
security details unless separately requested and authorized.
