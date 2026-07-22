from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))
sys.path.insert(0, str(ROOT / "tests"))

from github_issue_evidence import collect_issue_evidence  # noqa: E402
from specrail_lib import SpecRailError, validate_instance  # noqa: E402
from test_github_issue_evidence import (  # noqa: E402
    approval_query_payload,
    commit_all,
    issue_payload,
    mock_sensitive_github,
    run_implement_route,
    update_origin_main,
    write_custom_pack,
    write_sensitive_implement_pack,
)


def issue_schema() -> dict[str, Any]:
    return json.loads(
        (ROOT / "schemas" / "issue_evidence.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_issue_evidence(evidence: dict[str, Any]) -> None:
    validate_instance(issue_schema(), evidence)


def ordinary_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    repo = tmp_path / "ordinary"
    write_custom_pack(repo)
    monkeypatch.setattr(
        "github_issue_evidence.run_gh_json",
        lambda _args: issue_payload(labels=[{"name": "ready_to_spec"}]),
    )
    return collect_issue_evidence("example/consumer", 16, repo)


def non_sensitive_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], Path]:
    repo = tmp_path / "non-sensitive"
    write_sensitive_implement_pack(repo)
    tech = repo / "specs" / "GH16" / "tech.md"
    tech.write_text(
        tech.read_text(encoding="utf-8").replace(
            '"paths":["checks/route_gate.py"]',
            '"paths":["README.md"]',
        ),
        encoding="utf-8",
    )
    commit_all(repo, "approve non-sensitive plan")
    head = update_origin_main(repo)
    issue = issue_payload(labels=[{"name": "ready_to_implement"}])

    def fake_run_json(args: list[str]) -> object:
        if args[:2] == ["issue", "view"]:
            return issue
        if "SpecRailDefaultBase" in " ".join(args):
            return approval_query_payload(head)
        raise AssertionError("non-sensitive route must not query approval provenance")

    monkeypatch.setattr("github_issue_evidence.run_gh_json", fake_run_json)
    return collect_issue_evidence("example/consumer", 16, repo), repo


def sensitive_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    repo = tmp_path / "sensitive"
    head = write_sensitive_implement_pack(repo)
    mock_sensitive_github(monkeypatch, head)
    return collect_issue_evidence("example/consumer", 16, repo)


def test_serialized_issue_evidence_is_schema_valid_in_all_three_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary = ordinary_evidence(tmp_path, monkeypatch)
    non_sensitive, _repo = non_sensitive_evidence(tmp_path, monkeypatch)
    sensitive = sensitive_evidence(tmp_path, monkeypatch)

    assert sensitive["sensitive_route"] == "approved_spec"

    for evidence in [ordinary, non_sensitive, sensitive]:
        serialized = json.loads(json.dumps(evidence))
        validate_issue_evidence(serialized)


def test_non_sensitive_registry_plan_skips_approval_provenance_and_allows_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, repo = non_sensitive_evidence(tmp_path, monkeypatch)
    result, payload = run_implement_route(repo, evidence, tmp_path)

    assert evidence["enforcement_sensitive"] is False
    assert evidence["sensitive_classification"]["changed_paths"] == ["README.md"]
    assert "approved_spec" not in evidence
    assert result.returncode == 0, result.stderr
    assert payload["decision"] == "allowed"


def test_registry_plan_blocks_github_default_base_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "base-drift"
    write_sensitive_implement_pack(repo)
    issue = issue_payload(labels=[{"name": "ready_to_implement"}])

    def fake_run_json(args: list[str]) -> object:
        if args[:2] == ["issue", "view"]:
            return issue
        if "SpecRailDefaultBase" in " ".join(args):
            return approval_query_payload("f" * 40)
        raise AssertionError(f"unexpected GitHub call: {args}")

    monkeypatch.setattr("github_issue_evidence.run_gh_json", fake_run_json)
    with pytest.raises(SpecRailError, match="default base SHA"):
        collect_issue_evidence("example/consumer", 16, repo)


def test_issue_evidence_schema_rejects_forged_partial_sensitive_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary = ordinary_evidence(tmp_path, monkeypatch)
    sensitive = sensitive_evidence(tmp_path, monkeypatch)
    partial_base = deepcopy(ordinary)
    partial_base["base_ref"] = "main"
    missing_approval = deepcopy(sensitive)
    missing_approval.pop("approved_spec")
    missing_route = deepcopy(sensitive)
    missing_route.pop("sensitive_route")
    conflicting_declaration = deepcopy(sensitive)
    conflicting_declaration["enforcement_sensitive"] = False

    for evidence in [
        partial_base,
        missing_approval,
        missing_route,
        conflicting_declaration,
    ]:
        with pytest.raises(SpecRailError):
            validate_issue_evidence(evidence)
