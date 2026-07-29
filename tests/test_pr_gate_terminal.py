from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "checks"))

from pr_gate import evaluate_pr_gate
from rejection_items import (
    canonical_hosted_snapshot_sha256,
    canonical_review_sha256,
)
from test_pr_gate import ROOT, evidence


def refresh_review_digest(payload: dict[str, object]) -> None:
    payload["review_attestation"]["review_sha256"] = canonical_review_sha256(
        payload["review"]
    )
    payload["review_attestation"][
        "hosted_snapshot_sha256"
    ] = canonical_hosted_snapshot_sha256(
        payload["head_sha"],
        payload["gate_invocation_id"],
        payload["hosted_findings"],
        payload["prior_review_boundary"],
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
    payload["review"]["findings"] = []
    payload["review"]["verdict"] = "clean"
    payload["hosted_findings"] = [
        {
            "id": "P0-outdated",
            "severity": "P0",
            "status": "unresolved",
            "summary": "The comment targets an obsolete commit.",
            "fix_paths": ["src/app.py"],
            "origin": "hosted",
            "outdated": True,
        }
    ]
    refresh_review_digest(payload)

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]


def test_current_hosted_p1_blocks_terminal_gate() -> None:
    payload, pack = evidence()
    payload["hosted_findings"] = [
        {
            "id": "P1-current",
            "severity": "P1",
            "status": "unresolved",
            "summary": "The current hosted review found a blocker.",
            "fix_paths": ["src/app.py"],
            "origin": "hosted",
            "outdated": False,
        }
    ]
    refresh_review_digest(payload)

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "current unresolved P0/P1 findings: P1-current" in result["reasons"]


def test_hosted_snapshot_digest_blocks_every_signed_input_mutation() -> None:
    signed, pack = evidence()
    signed["hosted_findings"] = [
        {
            "id": "hosted:P2-signed",
            "severity": "P2",
            "status": "unresolved",
            "summary": "Signed hosted follow-up.",
            "fix_paths": ["src/app.py"],
            "origin": "hosted",
            "outdated": False,
        }
    ]
    refresh_review_digest(signed)
    mutations = {
        "deleted findings": lambda payload: payload.pop("hosted_findings"),
        "empty findings": lambda payload: payload.update(hosted_findings=[]),
        "edited finding": lambda payload: payload["hosted_findings"][0].update(
            summary="Tampered."
        ),
        "edited boundary": lambda payload: payload.update(
            prior_review_boundary="2026-07-29T00:00:00Z"
        ),
        "edited head": lambda payload: payload.update(head_sha="b" * 40),
        "edited invocation": lambda payload: payload.update(
            gate_invocation_id="gate-2"
        ),
    }
    for name, mutate in mutations.items():
        payload = copy.deepcopy(signed)
        mutate(payload)
        result = evaluate_pr_gate(payload, ROOT, pack)
        assert result["decision"] == "blocked", name
        assert (
            "review_attestation.hosted_snapshot_sha256 must match canonical "
            "hosted snapshot"
        ) in result["reasons"], name


def test_gate_never_grants_final_approval_or_merge_authority() -> None:
    payload, pack = evidence()

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["advisory_only"] is True
    assert "final_approval" not in result
    assert "merge_authorized" not in result
