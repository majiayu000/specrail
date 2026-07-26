from __future__ import annotations

from copy import deepcopy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from merge_authorization_gate import (  # noqa: E402
    evaluate_fastlane_gate,
    evaluate_merge_authorization,
    main,
)


HEAD = "a" * 40


def fastlane_evidence() -> dict[str, object]:
    return {
        "pr": 198,
        "repository": "majiayu000/specrail",
        "state": "OPEN",
        "is_draft": False,
        "head_sha": HEAD,
        "pr_tier": "fastlane",
        "pr_tier_evidence": {
            "changed_lines": 32,
            "touched_paths": ["checks/example.py"],
        },
        "enforcement_sensitive": False,
        "protected_paths": [],
        "auth_mode": "review",
        "checks_head_sha": HEAD,
        "checks": [
            {
                "name": "workflow-check",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            }
        ],
        "independent_review": {
            "review_source": "independent_lane",
            "review_execution": "local",
            "head_sha": HEAD,
            "status": "completed",
            "verdict": "clean",
            "tier_attestation": {
                "pr_tier": "fastlane",
                "attested": True,
                "basis": "32 changed lines; no protected paths",
            },
            "review_completed_at": "2026-07-26T12:00:00Z",
        },
        "focused_tests": {
            "command": "python3 -m pytest tests/test_example.py -q",
            "passed": True,
            "head_sha": HEAD,
        },
        "merge_state": "CLEAN",
        "gate_started_at": "2026-07-26T12:05:00Z",
        "human_authorization": {
            "actor": "maintainer",
            "source": "current conversation",
            "pr": 198,
            "head_sha": HEAD,
            "authorized_at": "2026-07-26T12:01:00Z",
        },
    }


def auto_evidence() -> dict[str, object]:
    evidence = fastlane_evidence()
    evidence.pop("human_authorization")
    evidence["auth_mode"] = "auto"
    evidence["run_id"] = "implx-20260726"
    evidence["run_authorization"] = {
        "actor": "maintainer",
        "source": "explicit implx auto invocation",
        "repository": "majiayu000/specrail",
        "run_id": "implx-20260726",
        "decision": "authorize_auto_run",
        "authorized_at": "2026-07-26T11:00:00Z",
    }
    return evidence


def test_fastlane_review_mode_allows_complete_exact_head_evidence() -> None:
    result = evaluate_fastlane_gate(fastlane_evidence())

    assert result["decision"] == "allowed"
    assert result["missing"] == []
    assert result["reasons"] == []
    assert {item["signal_type"] for item in result["signals"]} == {
        "ci",
        "focused_tests",
        "independent_review",
        "tier_eligibility",
        "merge_state",
        "merge_authorization",
    }
    assert all(
        set(item) == {"signal_type", "signal", "reason"}
        for item in result["signals"]
    )


def test_fastlane_missing_focused_tests_blocks() -> None:
    evidence = fastlane_evidence()
    evidence.pop("focused_tests")

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert "focused_tests" in result["missing"]


def test_fastlane_focused_tests_must_bind_current_head_and_pass() -> None:
    evidence = fastlane_evidence()
    evidence["focused_tests"] = {
        "command": "python3 -m pytest tests/test_example.py -q",
        "passed": True,
        "head_sha": "b" * 40,
    }

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert any(
        "focused_tests.head_sha must match" in reason
        for reason in result["reasons"]
    )

    evidence["focused_tests"] = {
        "command": "python3 -m pytest tests/test_example.py -q",
        "passed": False,
        "head_sha": HEAD,
    }
    result = evaluate_fastlane_gate(evidence)
    assert result["decision"] == "blocked"
    assert any(
        "focused_tests.passed must be true" in reason
        for reason in result["reasons"]
    )


def test_review_mode_authorization_must_name_the_gated_pr() -> None:
    evidence = fastlane_evidence()
    evidence["human_authorization"]["pr"] = 999

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert any(
        "human_authorization.pr must match the gated pr" in reason
        for reason in result["reasons"]
    )


def test_review_mode_authorization_without_pr_needs_human() -> None:
    evidence = fastlane_evidence()
    evidence["human_authorization"].pop("pr")

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "needs_human"
    assert "human_authorization.pr" in result["missing"]


def test_review_mode_rejects_authorization_before_terminal_review() -> None:
    evidence = fastlane_evidence()
    evidence["human_authorization"]["authorized_at"] = "2000-01-01T00:00:00Z"

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert any(
        "must be at or after review_completed_at" in reason
        for reason in result["reasons"]
    )


def test_review_mode_missing_authorization_needs_human() -> None:
    evidence = fastlane_evidence()
    evidence.pop("human_authorization")

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "needs_human"
    assert "human_authorization" in result["missing"]


def test_auto_mode_allows_bound_run_authorization() -> None:
    result = evaluate_fastlane_gate(auto_evidence())

    assert result["decision"] == "allowed"
    assert any(
        "repository and run" in item for item in result["satisfied"]
    )


def test_auto_mode_missing_run_authorization_blocks() -> None:
    evidence = auto_evidence()
    evidence.pop("run_authorization")

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert "run_authorization" in result["missing"]


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("repository", "other/repo", "repository must match"),
        ("run_id", "other-run", "run_id must match"),
        ("decision", "merge", "authorize_auto_run"),
        ("authorized_at", "not-a-time", "timezone-aware"),
    ],
)
def test_auto_mode_rejects_unbound_run_authorization(
    field: str, value: str, expected: str,
) -> None:
    evidence = auto_evidence()
    evidence["run_authorization"][field] = value

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert any(expected in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda item: item.update({"checks_head_sha": "b" * 40}), "checks_head_sha"),
        (
            lambda item: item["independent_review"].update({"head_sha": "b" * 40}),
            "independent_review.head_sha",
        ),
        (
            lambda item: item["independent_review"].update(
                {"review_source": "self_review"}
            ),
            "independent_review.review_source",
        ),
        (
            lambda item: item["pr_tier_evidence"].update({"changed_lines": 51}),
            "pr_tier_evidence.changed_lines",
        ),
        (
            lambda item: item.update({"enforcement_sensitive": True}),
            "enforcement-sensitive",
        ),
        (
            lambda item: item.update({"protected_paths": ["schemas/api.json"]}),
            "protected paths",
        ),
        (
            lambda item: item["independent_review"]["tier_attestation"].update(
                {"attested": False}
            ),
            "tier_attestation",
        ),
        (lambda item: item.update({"merge_state": "BLOCKED"}), "merge_state"),
    ],
)
def test_fastlane_gate_rejects_incomplete_profile_evidence(
    mutate: object, expected: str,
) -> None:
    evidence = deepcopy(fastlane_evidence())
    mutate(evidence)

    result = evaluate_fastlane_gate(evidence)

    assert result["decision"] == "blocked"
    assert any(expected in reason for reason in result["reasons"])


def test_shared_authorization_defaults_to_review_mode() -> None:
    evidence = fastlane_evidence()
    evidence.pop("auth_mode")
    evidence["review_completed_at"] = evidence["independent_review"][
        "review_completed_at"
    ]

    _, missing, reasons, signals = evaluate_merge_authorization(evidence)

    assert missing == []
    assert reasons == []
    assert signals[0]["signal"]["auth_mode"] == "review"


def test_fastlane_gate_cli_validates_schema_backed_fixture(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "checks/merge_authorization_gate.py",
            "--repo",
            str(ROOT),
            "--evidence",
            str(ROOT / "examples/fixtures/fastlane-gate-review.json"),
            "--json",
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "allowed"
    assert payload["signals"]


def test_fastlane_gate_cli_reports_needs_human(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = fastlane_evidence()
    evidence.pop("human_authorization")
    path = tmp_path / "needs-human.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_authorization_gate.py",
            "--repo",
            str(ROOT),
            "--evidence",
            str(path),
            "--json",
        ],
    )

    assert main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "needs_human"
    assert payload["blocked_actions"] == ["merge"]


def test_fastlane_gate_cli_rejects_malformed_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_authorization_gate.py",
            "--repo",
            str(ROOT),
            "--evidence",
            str(path),
        ],
    )

    assert main() == 2
    assert "invalid evidence JSON" in capsys.readouterr().err
