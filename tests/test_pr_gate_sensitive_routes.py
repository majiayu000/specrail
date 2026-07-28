from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "checks"))

from pr_gate import evaluate_pr_gate
from test_pr_gate import ROOT, evidence, verification_profile_config


def authorization(payload: dict[str, object]) -> dict[str, str]:
    return {
        "actor": "maintainer",
        "authorized_at": "2026-07-28T12:00:00Z",
        "head_sha": str(payload["head_sha"]),
        "invocation_id": str(payload["gate_invocation_id"]),
    }


def test_sensitive_change_requires_heavy_profile() -> None:
    payload, pack = evidence(
        profile="standard",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "sensitive changes must use the heavy profile" in result["reasons"]


def test_heavy_change_without_authorization_needs_human() -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human", result["reasons"]
    assert "human_merge_authorization" in result["missing"]


def test_heavy_change_with_current_invocation_authorization_is_allowed() -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    payload["human_merge_authorization"] = authorization(payload)

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]
    assert "current-invocation human merge authorization validated" in result["satisfied"]
    assert result["advisory_only"] is True


@pytest.mark.parametrize(
    "actor",
    ["codex", "self", "github-actions", "dependabot[bot]", "release-bot"],
)
def test_automation_actor_cannot_authenticate_a_human(actor: str) -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    payload["human_merge_authorization"] = {
        **authorization(payload),
        "actor": actor,
    }

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human", result["reasons"]
    assert any("actor must identify a human" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    "authorized_at",
    ["not-a-time", "2026-07-28T12:00:00", " 2026-07-28T12:00:00Z"],
)
def test_heavy_authorization_requires_timezone_timestamp(
    authorized_at: str,
) -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    payload["human_merge_authorization"] = {
        **authorization(payload),
        "authorized_at": authorized_at,
    }

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human"
    assert any("timezone-aware timestamp" in reason for reason in result["reasons"])


def test_heavy_authorization_missing_field_needs_human() -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    incomplete = authorization(payload)
    del incomplete["actor"]
    payload["human_merge_authorization"] = incomplete

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human"
    assert "human_merge_authorization.actor" in result["missing"]


def test_heavy_independent_review_requirement_cannot_be_disabled() -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    payload["human_merge_authorization"] = authorization(payload)
    pack.workflow["verification_profiles"] = verification_profile_config()
    pack.workflow["verification_profiles"]["profiles"]["heavy"][
        "requires_independent_review"
    ] = False
    payload["review"]["review_source"] = "self_review"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "workflow.yaml: heavy profile must match canonical safety policy" in result["reasons"]


def test_heavy_authorization_is_bound_to_head_and_invocation() -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    payload["human_merge_authorization"] = {
        **authorization(payload),
        "head_sha": "f" * 40,
        "invocation_id": "old-gate",
    }

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human"
    assert any("head_sha must match" in item for item in result["reasons"])
    assert any("current gate invocation" in item for item in result["reasons"])


def test_sensitive_gate_fails_closed_without_exact_checkout(tmp_path: Path) -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    payload["human_merge_authorization"] = authorization(payload)
    detached_pack = type(pack)(
        repo=tmp_path,
        workflow=pack.workflow,
        states={},
        labels={},
    )

    result = evaluate_pr_gate(payload, tmp_path, detached_pack)

    assert result["decision"] == "blocked"
    assert "sensitive PR gate requires an exact current-head checkout" in result["reasons"]


def test_invalid_heavy_profile_cannot_bypass_round_or_authorization() -> None:
    payload, pack = evidence(
        profile="heavy",
        paths=["checks/pr_gate.py"],
        patterns=["checks/**"],
    )
    pack.workflow["verification_profiles"] = verification_profile_config()
    heavy = pack.workflow["verification_profiles"]["profiles"]["heavy"]
    heavy["max_review_rounds"] = 3
    heavy["merge_authorization"] = "typo"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "human_merge_authorization" in result["missing"]
    assert any("max_review_rounds must be 1 or 2" in reason for reason in result["reasons"])
    assert any("merge_authorization must be" in reason for reason in result["reasons"])
