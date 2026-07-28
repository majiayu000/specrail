from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from route_gate_test_support import (
    complete_issue_evidence,
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
        "--github-repo",
        "example/consumer",
        "--approved-spec-revision",
        head,
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
    assert "spec approval established by trusted readiness label" in payload["satisfied"]
    assert "security_decision" in payload["human_gates"]
    assert "security evidence bound to explicit approved spec revision" in payload["satisfied"]


def test_heavy_route_fails_closed_without_approved_spec_revision(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    payload = sensitive_route_evidence(repo, head)
    evidence = write_evidence(tmp_path, payload)

    result, route = run_route_gate(
        "--route",
        "implement",
        "--profile",
        "heavy",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        "--mode",
        "required",
        repo=repo,
    )

    assert result.returncode == 1
    assert route["decision"] == "needs_human"
    assert "security_evidence" in route["missing"]
    assert "security_decision" in route["human_gates"]


def test_heavy_route_rejects_spec_drift_after_approved_revision(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    approved = write_sensitive_pack(repo)
    tech = repo / "specs/GH999/tech.md"
    tech.write_text(tech.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid", "commit", "-qm", "drift",
        ],
        check=True,
    )
    evidence = write_evidence(
        tmp_path, sensitive_route_evidence(repo, approved)
    )

    result, route = run_route_gate(
        "--route", "implement", "--profile", "heavy", "--issue", "999",
        "--github-repo", "example/consumer", "--approved-spec-revision", approved,
        "--evidence", str(evidence), "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert route["decision"] == "needs_human"
    assert "security_evidence" in route["missing"]


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


def test_non_heavy_route_without_tech_spec_defers_to_pr_gate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_sensitive_pack(repo)
    for path in (repo / "specs" / "GH999").iterdir():
        path.unlink()
    (repo / "specs" / "GH999").rmdir()
    evidence = write_evidence(
        tmp_path,
        complete_issue_evidence(
            testable_plan={
                "source": "issue_body_checklist",
                "items": ["verify deferred sensitive classification"],
            },
        ),
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--profile",
        "standard",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence),
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path)),
        "--mode",
        "required",
        repo=repo,
    )

    assert result.returncode == 0, payload["reasons"]
    assert payload["decision"] == "allowed"
    assert payload["sensitive_classification"]["source"] == "deferred_to_pr"


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
