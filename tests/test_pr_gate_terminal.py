from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "checks"))

from pr_gate import evaluate_pr_gate
from rejection_items import canonical_review_sha256
from test_pr_gate import ROOT, evidence


def refresh_review_digest(payload: dict[str, object]) -> None:
    payload["review_attestation"]["review_sha256"] = canonical_review_sha256(
        payload["review"]
    )


def test_round_above_cap_returns_needs_human() -> None:
    payload, pack = evidence()
    payload["review"]["round"] = 3
    payload["review"]["mode"] = "diff_only"
    refresh_review_digest(payload)

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human"
    assert "human_review" in result["missing"]


def test_p2_follow_up_does_not_block_terminal_gate() -> None:
    payload, pack = evidence()
    payload["review"]["verdict"] = "non_blocking"
    payload["review"]["findings"] = [
        {
            "id": "P2-cleanup",
            "severity": "P2",
            "status": "unresolved",
            "summary": "Cleanup can follow after merge.",
        }
    ]
    refresh_review_digest(payload)

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]


def test_outdated_hosted_p0_does_not_block_terminal_gate() -> None:
    payload, pack = evidence()
    payload["review"]["findings"] = [
        {
            "id": "P0-outdated",
            "severity": "P0",
            "status": "unresolved",
            "summary": "The comment targets an obsolete commit.",
            "origin": "hosted",
            "outdated": True,
        }
    ]
    refresh_review_digest(payload)

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]


def test_gate_never_grants_final_approval_or_merge_authority() -> None:
    payload, pack = evidence()

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["advisory_only"] is True
    assert "final_approval" not in result
    assert "merge_authorized" not in result
