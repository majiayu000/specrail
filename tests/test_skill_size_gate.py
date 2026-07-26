import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from skill_size_gate import (  # noqa: E402
    DEFAULT_SKILL_LINE_CAP,
    FASTLANE_BYTE_BUDGET,
    FASTLANE_READ_SET,
    FULL_DRAIN_STARTUP_BYTE_BUDGET,
    LINE_CAPS,
    evaluate,
)


def test_repository_passes_the_size_gate() -> None:
    result = evaluate(ROOT)
    assert result["decision"] == "allowed", result["errors"]


def test_hard_caps_match_gh208_contract() -> None:
    assert LINE_CAPS["skills/specrail-implement-queue/SKILL.md"] == 400
    assert LINE_CAPS["skills/implx/SKILL.md"] == 150
    assert DEFAULT_SKILL_LINE_CAP == 200
    assert FASTLANE_BYTE_BUDGET == 30 * 1024
    assert FULL_DRAIN_STARTUP_BYTE_BUDGET == 60 * 1024


def test_fastlane_read_set_is_three_skill_files() -> None:
    assert len(FASTLANE_READ_SET) == 3
    assert set(FASTLANE_READ_SET) == {
        "skills/implx/SKILL.md",
        "skills/specrail-implement/SKILL.md",
        "skills/specrail-pr-gate/SKILL.md",
    }


def test_gate_blocks_oversized_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(f"line {i}" for i in range(DEFAULT_SKILL_LINE_CAP + 1)),
        encoding="utf-8",
    )
    result = evaluate(tmp_path)
    assert result["decision"] == "blocked"
    assert any("exceeds hard cap" in error for error in result["errors"])


def test_queue_skill_keeps_single_review_lane_default() -> None:
    text = (ROOT / "skills/specrail-implement-queue/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "One reviewer lane per PR is the default" in text


def test_implx_declares_tiered_read_set() -> None:
    text = (ROOT / "skills/implx/SKILL.md").read_text(encoding="utf-8")
    assert "## Tiered Read Set" in text
    assert "at most three skill files" in text
