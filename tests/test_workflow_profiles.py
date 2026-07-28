from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from route_gate_test_support import (  # noqa: E402
    complete_issue_evidence,
    run_route_gate,
    write_duplicate_evidence,
    write_issue_evidence,
)
from specrail_lib import (  # noqa: E402
    ISSUE_STATES,
    load_pack,
    validate_labels,
    validate_state_graph,
    validate_verification_profiles,
    verification_profiles,
)


def test_workflow_has_exact_profiles_and_eight_issue_states() -> None:
    config = load_pack(ROOT)
    default, profiles = verification_profiles(config)

    assert default == "standard"
    assert set(profiles) == {"fastlane", "standard", "heavy"}
    assert set(config.states["states"]) == set(ISSUE_STATES)
    assert validate_state_graph(config) == []
    assert validate_labels(config) == []
    assert validate_verification_profiles(config) == []


@pytest.mark.parametrize(
    ("profile", "field", "value"),
    [
        ("fastlane", "requires_independent_review", True),
        ("standard", "max_review_rounds", 1),
        ("heavy", "requires_independent_review", False),
    ],
)
def test_profile_safety_policy_cannot_be_configured_away(
    profile: str,
    field: str,
    value: object,
) -> None:
    config = load_pack(ROOT)
    config.workflow["verification_profiles"]["profiles"][profile][field] = value

    errors = validate_verification_profiles(config)

    assert f"workflow.yaml: {profile} profile must match canonical safety policy" in errors


@pytest.mark.parametrize("profile", ["fastlane", "standard"])
def test_non_heavy_implement_does_not_require_spec_packet(
    tmp_path: Path,
    profile: str,
) -> None:
    duplicate = write_duplicate_evidence(tmp_path)
    evidence = tmp_path / "issue-evidence.json"
    evidence.write_text(
        json.dumps(
            complete_issue_evidence(
                testable_plan={
                    "source": "issue_body_checklist",
                    "items": ["「TODO fix parser」"],
                },
            )
        ),
        encoding="utf-8",
    )
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--profile",
        profile,
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(duplicate),
        "--mode",
        "required",
    )

    assert result.returncode == 0, payload
    assert payload["decision"] == "allowed"
    assert payload["profile"] == profile
    assert not {
        "specs/GH999/product.md",
        "specs/GH999/tech.md",
        "specs/GH999/tasks.md",
    } & set(payload["required_artifacts"])


def test_standard_implement_requires_testable_plan(tmp_path: Path) -> None:
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path)),
        "--profile",
        "standard",
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert "testable_plan" in payload["missing"]


@pytest.mark.parametrize(
    "item",
    [
        '"TBD"',
        "'TODO'",
        "“TBD”",
        "‘TODO’",
        '`"TBD"`',
        "「TBD」",
        "«TBD»",
        "„TBD“",
        '“TBD"',
        "TBD/TODO",
        "**「`TBD/TODO`」**",
        "\u200b",
        "\u0301",
        "TBD\u200bTODO",
        "TBD\u0301TODO",
        "TBDTODO",
        "pendingTBD",
        "TODOunknownnull",
        "comingsoon",
        "tobedeterminedTODO",
    ],
)
def test_standard_implement_rejects_placeholder_issue_plan(
    tmp_path: Path,
    item: str,
) -> None:
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(
            tmp_path,
            testable_plan={
                "source": "issue_body_checklist",
                "items": [item],
            },
        )),
        "--profile",
        "standard",
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert "testable_plan" in payload["missing"]


def test_heavy_implement_requires_complete_spec_packet(tmp_path: Path) -> None:
    duplicate = write_duplicate_evidence(tmp_path)
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path)),
        "--profile",
        "heavy",
        "--duplicate-evidence",
        str(duplicate),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert payload["profile"] == "heavy"
    assert {
        "product_spec:specs/GH999/product.md",
        "tech_spec:specs/GH999/tech.md",
        "task_plan:specs/GH999/tasks.md",
    } <= set(payload["missing"])


def test_conflicting_parked_and_ready_labels_fail_once(tmp_path: Path) -> None:
    evidence = tmp_path / "issue.json"
    evidence.write_text(
        json.dumps(
            {
                "github_state": "OPEN",
                "labels": ["parked", "ready_to_implement"],
                "state_source": "label",
                "state_trusted": True,
            }
        ),
        encoding="utf-8",
    )
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert len(
        [
            reason
            for reason in payload["reasons"]
            if "conflicting state labels" in reason
        ]
    ) == 1
