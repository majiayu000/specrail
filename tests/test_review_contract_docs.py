from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CONTRACT_FILES = (
    "review/agent_first_review.md",
    "skills/specrail-review-pr/SKILL.md",
    "skills/specrail-implement-queue/SKILL.md",
    "skills/implx/SKILL.md",
    "integrations/threads.md",
)
START = "<!-- specrail-bounded-review-contract-v1:start -->"
END = "<!-- specrail-bounded-review-contract-v1:end -->"
EXPECTED_BLOCK = """<!-- specrail-bounded-review-contract-v1:start -->
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
<!-- specrail-bounded-review-contract-v1:end -->"""
FORBIDDEN_LEGACY_PHRASES = (
    "allowed for rounds 1-2",
    "full reviews are capped at 2 rounds",
    "explicitly requests another full pass",
    "past round 2 requires a quoted `human_full_review_request`",
)


def _contract_block(text: str) -> str:
    assert text.count(START) == 1
    assert text.count(END) == 1
    start = text.index(START)
    end = text.index(END, start) + len(END)
    return text[start:end]


def test_bounded_review_contract_is_identical_in_every_authoritative_doc() -> None:
    for relative_path in CONTRACT_FILES:
        text = (REPO / relative_path).read_text(encoding="utf-8")
        assert _contract_block(text) == EXPECTED_BLOCK, relative_path


def test_authoritative_docs_reject_legacy_full_review_escape_hatches() -> None:
    for relative_path in CONTRACT_FILES:
        text = (REPO / relative_path).read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_LEGACY_PHRASES:
            assert phrase not in text, f"{relative_path}: forbidden legacy phrase: {phrase}"
