from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CANONICAL_FILE = "skills/specrail-review-pr/SKILL.md"
REFERENCING_FILES = (
    "review/agent_first_review.md",
    "skills/implx/SKILL.md",
    "integrations/threads.md",
    "skills/specrail-implement-queue/SKILL.md",
)
START = "<!-- specrail-bounded-review-contract-v1:start -->"
END = "<!-- specrail-bounded-review-contract-v1:end -->"
EXPECTED_BLOCK = """<!-- specrail-bounded-review-contract-v1:start -->
Compact review contract (`contract_version: 3`):

- Round 1 uses `mode: full`; round 2 uses `mode: diff_only` and binds
  `base_head_sha` plus `diff_sha256`; round greater than 2 returns
  `needs_human`.
- Current unresolved `P0`/`P1` findings block. `P2`/`P3` findings are
  non-blocking follow-ups on the current Issue/PR and never create Issues
  automatically.
- A hosted finding with `outdated: true` does not block. A current-head
  unresolved `P0`/`P1` still blocks regardless of origin.
- Standard/heavy require `review_source: independent_lane`; fastlane may use
  `self_review`.
- The artifact is advisory and cannot grant final approval or merge authority.
<!-- specrail-bounded-review-contract-v1:end -->"""
FORBIDDEN_LEGACY_PHRASES = (
    "allowed for rounds 1-2",
    "full reviews are capped at 2 rounds",
    "explicitly requests another full pass",
    "past round 2 requires a quoted `human_full_review_request`",
    "manifest.version: 2",
    "round_cap_escalation",
)


def _contract_block(text: str) -> str:
    assert text.count(START) == 1
    assert text.count(END) == 1
    start = text.index(START)
    end = text.index(END, start) + len(END)
    return text[start:end]


def test_bounded_review_contract_is_canonical_in_review_pr_skill_only() -> None:
    text = (REPO / CANONICAL_FILE).read_text(encoding="utf-8")
    assert _contract_block(text) == EXPECTED_BLOCK, CANONICAL_FILE


def test_referencing_docs_point_to_canonical_contract_without_copies() -> None:
    for relative_path in REFERENCING_FILES:
        text = (REPO / relative_path).read_text(encoding="utf-8")
        assert START not in text, f"{relative_path}: duplicated contract block"
        assert END not in text, f"{relative_path}: duplicated contract block"
        assert CANONICAL_FILE in text, f"{relative_path}: missing contract reference"
        assert "do not copy it here" in text, relative_path


def test_authoritative_docs_reject_legacy_full_review_escape_hatches() -> None:
    for relative_path in (CANONICAL_FILE, *REFERENCING_FILES):
        text = (REPO / relative_path).read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_LEGACY_PHRASES:
            assert phrase not in text, f"{relative_path}: forbidden legacy phrase: {phrase}"
