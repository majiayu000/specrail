from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from review_json_gate import evaluate_review_gate  # noqa: E402


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def review_with(
    *,
    profile: str = "standard",
    review_round: int = 1,
    mode: str = "full",
    verdict: str = "clean",
    findings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    review: dict[str, object] = {
        "artifact_id": f"review-{profile}-{review_round}",
        "contract_version": 3,
        "repository": "acme/widgets",
        "pr": 489,
        "profile": profile,
        "head_sha": "a" * 40,
        "review_source": "independent_lane",
        "round": review_round,
        "mode": mode,
        "verdict": verdict,
        "body": "## Summary\nReviewed the bounded change.\n\n## Verdict\nAdvisory result only.",
        "findings": findings or [],
    }
    if review_round == 2:
        diff = load_diff().encode()
        review["base_head_sha"] = "b" * 40
        review["diff_sha256"] = hashlib.sha256(diff).hexdigest()
    return review


@pytest.mark.parametrize("profile", ["standard", "heavy"])
def test_standard_and_heavy_require_independent_review(profile: str) -> None:
    review = review_with(profile=profile)
    review["review_source"] = "self_review"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert f"{profile} profile requires an independent_lane review" in result["reasons"]


def test_fastlane_allows_self_review() -> None:
    review = review_with(profile="fastlane")
    review["review_source"] = "self_review"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "allowed", result["reasons"]


@pytest.mark.parametrize(
    ("review_round", "mode", "expected_reason"),
    [
        (1, "diff_only", "round 1 must use full mode"),
        (2, "full", "round 2 must use diff_only mode"),
    ],
)
def test_round_mode_contract(
    review_round: int,
    mode: str,
    expected_reason: str,
) -> None:
    result = evaluate_review_gate(
        review_with(review_round=review_round, mode=mode),
        load_diff(),
    )

    assert result["decision"] == "blocked"
    assert expected_reason in result["reasons"]


def test_round_above_two_requires_human() -> None:
    result = evaluate_review_gate(
        review_with(review_round=3, mode="diff_only"),
        load_diff(),
    )

    assert result["decision"] == "needs_human"
    assert "review round cap exceeded; human review is required" in result["reasons"]


@pytest.mark.parametrize("severity", ["P0", "P1"])
def test_current_unresolved_p0_p1_blocks(severity: str) -> None:
    finding = {
        "id": f"{severity}-current",
        "severity": severity,
        "status": "unresolved",
        "summary": "Current-head defect.",
        "path": "src/app.py",
        "line": 2,
    }

    result = evaluate_review_gate(
        review_with(verdict="blocking", findings=[finding]),
        load_diff(),
    )

    assert result["decision"] == "blocked"
    assert result["blocking_findings"] == [f"{severity}-current"]


@pytest.mark.parametrize("severity", ["P2", "P3"])
def test_p2_p3_becomes_non_blocking_follow_up(severity: str) -> None:
    finding = {
        "id": f"{severity}-follow-up",
        "severity": severity,
        "status": "unresolved",
        "summary": "Non-blocking improvement.",
    }

    result = evaluate_review_gate(
        review_with(verdict="non_blocking", findings=[finding]),
        load_diff(),
    )

    assert result["decision"] == "allowed", result["reasons"]
    assert result["follow_ups"] == [f"{severity}-follow-up"]


def test_outdated_hosted_p0_does_not_block() -> None:
    finding = {
        "id": "P0-outdated-hosted",
        "severity": "P0",
        "status": "unresolved",
        "summary": "Finding is attached to an obsolete commit.",
        "origin": "hosted",
        "outdated": True,
    }

    result = evaluate_review_gate(
        review_with(findings=[finding]),
        load_diff(),
    )

    assert result["decision"] == "allowed", result["reasons"]
    assert result["outdated_hosted_findings"] == ["P0-outdated-hosted"]
    assert result["blocking_findings"] == []


def test_outdated_local_finding_is_invalid() -> None:
    finding = {
        "id": "P1-outdated-local",
        "severity": "P1",
        "status": "unresolved",
        "summary": "Local evidence cannot claim hosted obsolescence.",
        "outdated": True,
    }

    result = evaluate_review_gate(
        review_with(verdict="blocking", findings=[finding]),
        load_diff(),
    )

    assert result["decision"] == "blocked"
    assert "finding #1 outdated is only valid for hosted findings" in result["reasons"]


def test_resolved_p0_does_not_block() -> None:
    finding = {
        "id": "P0-resolved",
        "severity": "P0",
        "status": "resolved",
        "summary": "The defect was corrected.",
    }

    result = evaluate_review_gate(review_with(findings=[finding]), load_diff())

    assert result["decision"] == "allowed", result["reasons"]


def test_round_two_p0_declares_if_introduced_by_fix_diff() -> None:
    finding = {
        "id": "P0-round2",
        "severity": "P0",
        "status": "unresolved",
        "summary": "Fix diff introduced a critical defect.",
        "introduced_by_diff": True,
    }
    review = review_with(
        review_round=2,
        mode="diff_only",
        verdict="blocking",
        findings=[finding],
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert result["blocking_findings"] == ["P0-round2"]
    assert not any("must declare introduced_by_diff" in item for item in result["reasons"])


def test_round_two_p0_without_diff_classification_is_invalid() -> None:
    finding = {
        "id": "P0-round2-unclassified",
        "severity": "P0",
        "status": "unresolved",
        "summary": "Unclassified critical defect.",
    }
    result = evaluate_review_gate(
        review_with(
            review_round=2,
            mode="diff_only",
            verdict="blocking",
            findings=[finding],
        ),
        load_diff(),
    )

    assert result["decision"] == "blocked"
    assert "finding #1 round 2 P0/P1 must declare introduced_by_diff" in result["reasons"]


def test_verdict_must_match_current_findings() -> None:
    finding = {
        "id": "P2-hidden",
        "severity": "P2",
        "status": "unresolved",
        "summary": "Follow-up cannot be hidden by a clean verdict.",
    }

    result = evaluate_review_gate(
        review_with(verdict="clean", findings=[finding]),
        load_diff(),
    )

    assert result["decision"] == "blocked"
    assert any("expected 'non_blocking'" in item for item in result["reasons"])
