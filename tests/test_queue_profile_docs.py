from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "skills" / "specrail-implement-queue" / "SKILL.md"


def test_queue_profiles_reduce_fastlane_evidence() -> None:
    text = QUEUE.read_text(encoding="utf-8")

    assert "| `fastlane` |" in text
    assert "structured review manifest, hosted review, GraphQL thread collection" in text
    assert "`pr_gate`, runtime checkpoint" in text
    assert "`fastlane` does not invoke those gates" in text
    assert "verification gates themselves stay identical for every tier" not in text
    assert "Tiering never weakens CI" not in text


def test_fastlane_keeps_minimum_safety_evidence() -> None:
    text = QUEUE.read_text(encoding="utf-8")

    assert "focused tests, repository-required CI, one independent exact-head review" in text
    assert "A protected path or enforcement-sensitive change is always `heavy`" in text
    assert "A missing or disputed tier fails closed to `heavy`" in text
