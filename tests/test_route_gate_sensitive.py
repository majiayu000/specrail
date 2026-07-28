from __future__ import annotations

import json
from pathlib import Path

import pytest

from route_gate_test_support import (
    run_route_gate,
    sensitive_route_evidence,
    write_duplicate_evidence,
    write_sensitive_pack,
)


def write_evidence(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "issue-evidence.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_route_gate_derives_sensitive_classification_from_current_tech_spec(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = write_evidence(tmp_path, sensitive_route_evidence(repo, head))

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--profile",
        "heavy",
        "--issue",
        "999",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        repo=repo,
    )

    assert result.returncode == 0, result.stderr
    assert payload["decision"] == "allowed", payload["reasons"]
    assert payload["sensitive_classification"]["matched_paths"] == [
        "checks/route_gate.py"
    ]


def test_sensitive_planned_change_blocks_non_heavy_profile(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_sensitive_pack(repo)
    evidence = write_evidence(
        tmp_path,
        {
            "github_state": "OPEN",
            "state": "ready_to_implement",
            "state_source": "label",
            "state_trusted": True,
            "enforcement_sensitive": False,
        },
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--profile",
        "standard",
        "--issue",
        "999",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        repo=repo,
    )

    assert result.returncode == 1
    assert "sensitive planned changes must use the heavy profile" in payload["reasons"]


def test_route_gate_blocks_complete_manifest_with_empty_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo, planned_paths=[])
    evidence = write_evidence(tmp_path, sensitive_route_evidence(repo, head))

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--profile",
        "heavy",
        "--issue",
        "999",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        repo=repo,
    )

    assert result.returncode == 1
    assert any("manifest paths must be non-empty" in item for item in payload["reasons"])


@pytest.mark.parametrize(
    ("manifest_count", "render_manifest", "reason"),
    [
        (0, True, "exactly one"),
        (2, True, "exactly one"),
        (1, False, "version/issue binding"),
    ],
)
def test_route_gate_fails_closed_on_invalid_tech_manifest(
    tmp_path: Path,
    manifest_count: int,
    render_manifest: bool,
    reason: str,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(
        repo,
        manifest_count=manifest_count,
        render_manifest=render_manifest,
    )
    evidence = write_evidence(tmp_path, sensitive_route_evidence(repo, head))

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--profile",
        "heavy",
        "--issue",
        "999",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        repo=repo,
    )

    assert result.returncode == 1
    assert any(reason in item for item in payload["reasons"])
