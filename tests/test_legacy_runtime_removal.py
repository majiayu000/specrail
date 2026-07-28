from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from pr_gate import evaluate_pr_gate  # noqa: E402
from route_gate_test_support import run_route_gate  # noqa: E402


REMOVED_CHECKERS = {
    "runtime_budget_dimensions.py",
    "runtime_gate_rules.py",
    "runtime_ledger_gate.py",
    "runtime_pr_gate_evidence.py",
    "runtime_review_evidence.py",
    "runtime_sensitive_routes.py",
    "runtime_tier_authorization.py",
    "session_telemetry.py",
}
REMOVED_SCHEMAS = {
    "content_binding_evidence.schema.json",
    "flow_manifest.schema.json",
    "pr_review_authorizations.schema.json",
    "runtime_checkpoint.schema.json",
    "runtime_thread_dispatch_gate.schema.json",
    "runtime_tier_authorization.schema.json",
    "workflow_run.schema.json",
}


def test_runtime_second_state_machine_is_physically_removed() -> None:
    assert not {
        path.name for path in (ROOT / "checks").glob("*.py")
    } & REMOVED_CHECKERS
    assert not {
        path.name for path in (ROOT / "schemas").glob("*.json")
    } & REMOVED_SCHEMAS
    assert not list((ROOT / "examples" / "fixtures").glob("runtime-*.json"))


def test_legacy_runtime_evidence_requires_github_rebuild() -> None:
    result = evaluate_pr_gate(
        {
            "runtime_checkpoint": {"goal": "drain queue"},
            "pr_tier": "standard",
            "tier_attestation": {"status": "passed"},
        }
    )

    assert result["decision"] == "blocked"
    assert result["unsupported_legacy_evidence"] == [
        "pr_tier",
        "runtime_checkpoint",
        "tier_attestation",
    ]
    assert any("rebuild evidence from GitHub" in item for item in result["reasons"])


def test_route_legacy_evidence_is_explicitly_rejected(tmp_path: Path) -> None:
    evidence = tmp_path / "issue-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "runtime_checkpoint": {"state": "old"},
                "tier_authorization": {"tier": "standard"},
                "review_round": 2,
            }
        ),
        encoding="utf-8",
    )

    _process, result = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "208",
        "--state",
        "ready_to_implement",
        "--profile",
        "fastlane",
        "--evidence",
        str(evidence),
        "--mode",
        "required",
    )

    assert result["decision"] == "blocked"
    assert result["reasons"] == [
        "unsupported legacy route evidence fields: review_round, "
        "runtime_checkpoint, tier_authorization; rebuild evidence from "
        "current GitHub issue state"
    ]


def test_route_legacy_diagnostic_survives_closed_issue_early_exit(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "closed-legacy-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "github_state": "CLOSED",
                "pr_tier_evidence": {"tier": "heavy"},
                "tier_dispute": {"status": "open"},
            }
        ),
        encoding="utf-8",
    )

    _process, result = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "208",
        "--state",
        "ready_to_implement",
        "--profile",
        "fastlane",
        "--evidence",
        str(evidence),
        "--mode",
        "required",
    )

    assert result["decision"] == "blocked"
    assert any(
        "pr_tier_evidence, tier_dispute" in reason
        for reason in result["reasons"]
    )
    assert "GitHub issue state must be OPEN; got CLOSED" in result["reasons"]


def test_optional_resume_cursor_has_no_gate_schema_or_checker() -> None:
    assert not (ROOT / "schemas" / "resume_cursor.schema.json").exists()
    assert not (ROOT / "checks" / "resume_cursor_gate.py").exists()
