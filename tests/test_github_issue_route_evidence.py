from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))
sys.path.insert(0, str(ROOT / "tests"))

from github_issue_evidence import collect_issue_evidence  # noqa: E402
from rejection_items import item_from_reason  # noqa: E402
from route_gate_test_support import (  # noqa: E402
    complete_issue_evidence,
    run_route_gate,
    write_custom_pack as write_route_pack,
)
from schema_validation import SpecRailError, load_json_schema, validate_instance  # noqa: E402
from test_github_issue_evidence import (  # noqa: E402
    issue_payload,
    mock_sensitive_github,
    write_custom_pack,
    write_sensitive_implement_pack,
)


def test_ordinary_and_sensitive_issue_evidence_use_one_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary_repo = tmp_path / "ordinary"
    write_custom_pack(ordinary_repo)
    monkeypatch.setattr(
        "github_issue_evidence.run_gh_json",
        lambda _args: issue_payload(labels=[{"name": "ready_to_spec"}]),
    )
    ordinary = collect_issue_evidence("example/consumer", 16, ordinary_repo)

    sensitive_repo = tmp_path / "sensitive"
    head = write_sensitive_implement_pack(sensitive_repo)
    mock_sensitive_github(monkeypatch, head)
    sensitive = collect_issue_evidence("example/consumer", 16, sensitive_repo)
    schema = load_json_schema(ROOT / "schemas" / "issue_evidence.schema.json")

    validate_instance(schema, json.loads(json.dumps(ordinary)), "ordinary issue")
    validate_instance(schema, json.loads(json.dumps(sensitive)), "sensitive issue")
    assert sensitive["enforcement_sensitive"] is True
    assert "approved_spec" not in sensitive
    assert "sensitive_route" not in sensitive


def test_issue_schema_rejects_removed_approval_ledger_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "sensitive"
    head = write_sensitive_implement_pack(repo)
    mock_sensitive_github(monkeypatch, head)
    evidence = collect_issue_evidence("example/consumer", 16, repo)
    forged = deepcopy(evidence)
    forged["approved_spec"] = {"maintainer_actor": "someone"}
    schema = load_json_schema(ROOT / "schemas" / "issue_evidence.schema.json")

    with pytest.raises(SpecRailError):
        validate_instance(schema, forged, "issue")


def test_issue_schema_accepts_bound_testable_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "ordinary"
    write_custom_pack(repo)
    monkeypatch.setattr(
        "github_issue_evidence.run_gh_json",
        lambda _args: issue_payload(
            labels=[{"name": "ready_to_implement"}],
            body="## Acceptance Criteria\n\n- [ ] observable result\n",
        ),
    )

    evidence = collect_issue_evidence("example/consumer", 16, repo)
    schema = load_json_schema(ROOT / "schemas" / "issue_evidence.schema.json")

    validate_instance(schema, evidence, "issue")
    assert evidence["testable_plan"]["items"] == ["observable result"]


def test_readiness_route_rejects_partial_issue_evidence_downgrade(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "partial.json"
    evidence_path.write_text(
        json.dumps(
            {
                "state": "ready_to_implement",
                "state_source": "label",
                "state_trusted": True,
                "labels": ["ready_to_implement"],
            }
        ),
        encoding="utf-8",
    )

    process, result = run_route_gate(
        "--route", "implement", "--issue", "999", "--profile", "standard",
        "--evidence", str(evidence_path), "--mode", "required",
    )

    assert process.returncode == 1
    assert result["decision"] == "blocked"
    for field in [
        "issue",
        "repository",
        "body_sha256",
        "github_state",
        "outcomes",
        "url",
        "title",
        "artifacts",
    ]:
        assert f"issue evidence.{field}: missing required field" in result["reasons"]
    assert "collector Issue evidence requires --github-repo OWNER/REPO" in result["reasons"]


def test_issue_schema_reports_all_invalid_nested_siblings(tmp_path: Path) -> None:
    evidence = complete_issue_evidence()
    evidence["testable_plan"] = {
        "items": [1, 2],
        "extra": "not allowed",
    }
    evidence["artifacts"] = {
        "product_spec": "",
        "extra": "not allowed",
    }
    evidence["sensitive_classification"] = {
        "source": "wrong_source",
        "matched_specs": [1, 2],
        "extra": "not allowed",
    }
    evidence_path = tmp_path / "invalid-nested.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    process, result = run_route_gate(
        "--route", "implement", "--issue", "999",
        "--github-repo", "example/consumer",
        "--profile", "standard",
        "--evidence", str(evidence_path), "--mode", "required",
    )

    assert process.returncode == 1
    assert result["decision"] == "blocked"
    expected_schema_reasons = {
        "issue evidence.testable_plan.source: missing required field",
        "issue evidence.testable_plan.body_sha256: missing required field",
        "issue evidence.testable_plan.extra: additional property is not allowed",
        "issue evidence.testable_plan.items[0]: expected type string",
        "issue evidence.testable_plan.items[1]: expected type string",
        "issue evidence.artifacts.tech_spec: missing required field",
        "issue evidence.artifacts.task_plan: missing required field",
        "issue evidence.artifacts.extra: additional property is not allowed",
        "issue evidence.artifacts.product_spec: string is shorter than minLength",
        "issue evidence.sensitive_classification.changed_paths: missing required field",
        "issue evidence.sensitive_classification.spec_refs: missing required field",
        "issue evidence.sensitive_classification.matched_paths: missing required field",
        "issue evidence.sensitive_classification.registry_configured: missing required field",
        "issue evidence.sensitive_classification.enforcement_sensitive: missing required field",
        "issue evidence.sensitive_classification.source_path: missing required field",
        "issue evidence.sensitive_classification.planned_paths_complete: missing required field",
        "issue evidence.sensitive_classification.extra: additional property is not allowed",
        "issue evidence.sensitive_classification.source: expected const 'tech_spec'",
        "issue evidence.sensitive_classification.matched_specs[0]: expected type string",
        "issue evidence.sensitive_classification.matched_specs[1]: expected type string",
    }
    schema_reasons = {
        reason
        for reason in result["reasons"]
        if reason.startswith("issue evidence.")
    }
    assert schema_reasons == expected_schema_reasons

    expected_evidence_reasons = expected_schema_reasons | {
        "testable_plan.body_sha256 must match issue evidence body_sha256"
    }
    expected_item_ids = {
        item_from_reason(reason, "invalid_evidence_value")["item_id"]
        for reason in expected_evidence_reasons
    }
    invalid_items = [
        item
        for item in result["rejection_items"]
        if item["category"] == "invalid_evidence_value"
    ]
    assert {item["item_id"] for item in invalid_items} == expected_item_ids
    assert len(invalid_items) == len(expected_item_ids)
    all_item_ids = [item["item_id"] for item in result["rejection_items"]]
    assert len(all_item_ids) == len(set(all_item_ids))


def test_issue_schema_definition_error_is_reported_once(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_route_pack(repo)
    schema_path = repo / "schemas" / "issue_evidence.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["unsupportedKeyword"] = True
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(state="ready_to_spec")),
        encoding="utf-8",
    )

    process, result = run_route_gate(
        "--route", "write_spec", "--issue", "999",
        "--github-repo", "example/consumer",
        "--evidence", str(evidence_path), "--mode", "required",
        repo=repo,
    )

    schema_reason = (
        "$schema: unsupported JSON Schema keyword 'unsupportedKeyword'"
    )
    assert process.returncode == 1
    assert result["decision"] == "blocked"
    assert result["reasons"].count(schema_reason) == 1
    schema_item = item_from_reason(schema_reason, "invalid_evidence_value")
    assert [
        item
        for item in result["rejection_items"]
        if item["item_id"] == schema_item["item_id"]
    ] == [schema_item]


def test_readiness_route_rejects_missing_collector_evidence() -> None:
    process, result = run_route_gate(
        "--route", "implement", "--issue", "999",
        "--profile", "standard", "--mode", "required",
    )

    assert process.returncode == 1
    assert result["decision"] == "blocked"
    assert "issue evidence.issue: missing required field" in result["reasons"]
    assert "collector Issue evidence requires --github-repo OWNER/REPO" in result["reasons"]


def test_cli_label_cannot_augment_collector_readiness_labels(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "collector.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(
            state="new_issue", labels=["new_issue"]
        )),
        encoding="utf-8",
    )

    process, result = run_route_gate(
        "--route", "implement", "--issue", "999",
        "--github-repo", "example/consumer",
        "--label", "ready_to_implement",
        "--profile", "standard",
        "--evidence", str(evidence_path), "--mode", "required",
    )

    assert process.returncode == 1
    assert result["decision"] == "blocked"
    assert "readiness collector evidence cannot be augmented with --label" in result["reasons"]
    assert result["current_state"] == "new_issue"


def test_cli_state_cannot_override_collector_readiness_state(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "collector.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(
            state="new_issue", labels=["new_issue"]
        )),
        encoding="utf-8",
    )

    process, result = run_route_gate(
        "--route", "implement", "--issue", "999",
        "--github-repo", "example/consumer",
        "--state", "ready_to_implement",
        "--profile", "standard",
        "--evidence", str(evidence_path), "--mode", "required",
    )

    assert process.returncode == 1
    assert result["decision"] == "blocked"
    assert "--state ready_to_implement conflicts with collector state 'new_issue'" in result["reasons"]
    assert result["current_state"] == "new_issue"
