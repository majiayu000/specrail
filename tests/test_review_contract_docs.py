from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CANONICAL_FILE = "skills/specrail-review-pr/SKILL.md"
REFERENCE_FILES = (
    "review/agent_first_review.md",
    "skills/specrail-implement-queue/SKILL.md",
    "skills/implx/SKILL.md",
    "integrations/threads.md",
)
START = "<!-- specrail-bounded-review-contract-v1:start -->"
END = "<!-- specrail-bounded-review-contract-v1:end -->"
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


def test_bounded_review_contract_has_one_canonical_source() -> None:
    canonical = (REPO / CANONICAL_FILE).read_text(encoding="utf-8")
    block = _contract_block(canonical)
    assert '`round_policy: {name: "bounded_diff_v1", cap: 2}`' in block
    assert "Before every `review_round >= 3`" in block
    for relative_path in REFERENCE_FILES:
        text = (REPO / relative_path).read_text(encoding="utf-8")
        assert START not in text, relative_path
        assert END not in text, relative_path
        assert "skills/specrail-review-pr/SKILL.md" in text, relative_path


def test_authoritative_docs_reject_legacy_full_review_escape_hatches() -> None:
    for relative_path in (CANONICAL_FILE, *REFERENCE_FILES):
        text = (REPO / relative_path).read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_LEGACY_PHRASES:
            assert phrase not in text, f"{relative_path}: forbidden legacy phrase: {phrase}"
