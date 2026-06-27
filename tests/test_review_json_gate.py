from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from review_json_gate import evaluate_review_gate  # noqa: E402


def load_review(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def test_review_json_gate_allows_valid_review() -> None:
    result = evaluate_review_gate(load_review("review-valid.json"), load_diff())

    assert result["decision"] == "allowed"
    assert result["verdict"] == "REJECT"
    assert result["comment_count"] == 2
    assert result["advisory_only"] is True
    assert result["reasons"] == []
    assert result["missing"] == []


def test_review_json_gate_blocks_invalid_line() -> None:
    result = evaluate_review_gate(load_review("review-invalid-line.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("src/app.py:99 is not present in the diff" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_severity() -> None:
    result = evaluate_review_gate(load_review("review-invalid-severity.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("severity must be critical" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_spec_drift() -> None:
    result = evaluate_review_gate(load_review("review-spec-drift.json"), load_diff())

    assert result["decision"] == "blocked"
    assert "spec_alignment reports drift" in result["reasons"]


def test_review_json_gate_blocks_final_authority_language() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    review["body"] = (
        "I approve this PR. It is approved for merge. You can merge; ship it. "
        "Go ahead and merge. Looks good to merge. Safe to merge. LGTM, merge."
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("final approval or merge authority" in reason for reason in result["reasons"])


def test_review_json_gate_cli_json_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "checks/review_json_gate.py",
            "--repo",
            ".",
            "--review",
            "examples/fixtures/review-valid.json",
            "--diff",
            "examples/fixtures/pr-diff.patch",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert {
        "decision",
        "verdict",
        "comment_count",
        "advisory_only",
        "reasons",
        "satisfied",
        "missing",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)
