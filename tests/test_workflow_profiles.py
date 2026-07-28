from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from route_gate_test_support import run_route_gate, write_duplicate_evidence  # noqa: E402
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


@pytest.mark.parametrize("profile", ["fastlane", "standard"])
def test_non_heavy_implement_does_not_require_spec_packet(
    tmp_path: Path,
    profile: str,
) -> None:
    duplicate = write_duplicate_evidence(tmp_path)
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
        "--profile",
        profile,
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


def test_heavy_implement_requires_complete_spec_packet(tmp_path: Path) -> None:
    duplicate = write_duplicate_evidence(tmp_path)
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
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
