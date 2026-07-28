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
