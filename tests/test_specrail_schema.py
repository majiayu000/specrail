from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from schema_validation import SpecRailError, load_json_schema, validate_instance  # noqa: E402


SCHEMAS = {
    "duplicate_work_evidence.schema.json",
    "evaluation_result.schema.json",
    "issue_evidence.schema.json",
    "issue_triage.schema.json",
    "pr_review_gate.schema.json",
    "review_result.schema.json",
    "spec_packet.schema.json",
    "task_plan.schema.json",
}


def valid_review() -> dict[str, object]:
    return {
        "artifact_id": "review-1",
        "contract_version": 3,
        "repository": "acme/widgets",
        "pr": 1,
        "profile": "standard",
        "head_sha": "a" * 40,
        "review_source": "independent_lane",
        "round": 1,
        "mode": "full",
        "verdict": "clean",
        "body": "## Summary\nReviewed.\n\n## Verdict\nClean.",
        "findings": [],
    }


def test_schema_set_is_exactly_eight() -> None:
    assert {path.name for path in (ROOT / "schemas").glob("*.json")} == SCHEMAS


def test_all_schemas_are_loadable_closed_objects() -> None:
    for name in SCHEMAS:
        raw = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert raw["type"] == "object"
        assert "title" in raw
        load_json_schema(ROOT / "schemas" / name)


def test_compact_review_schema_accepts_v3_and_rejects_legacy() -> None:
    schema = load_json_schema(ROOT / "schemas" / "review_result.schema.json")
    validate_instance(schema, valid_review(), "review")
    legacy = valid_review()
    legacy["review_round"] = 1

    with pytest.raises(SpecRailError):
        validate_instance(schema, legacy, "review")


def test_compact_pr_schema_accepts_current_evidence() -> None:
    review = valid_review()
    changed = ["src/app.py"]
    payload = {
        "contract_version": 3,
        "repository": "acme/widgets",
        "pr": 1,
        "linked_issue": 8,
        "state": "OPEN",
        "is_draft": False,
        "base_sha": "b" * 40,
        "head_sha": "a" * 40,
        "gate_query_head_sha": "a" * 40,
        "changed_files": changed,
        "changed_files_count": 1,
        "changed_files_sha256": "c" * 64,
        "checks": [
            {
                "name": "tests",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "head_sha": "a" * 40,
            }
        ],
        "merge_state": "CLEAN",
        "profile": "standard",
        "enforcement_sensitive": False,
        "sensitive_classification": {
            "source": "github_changed_files",
            "changed_paths": changed,
            "spec_refs": changed,
            "matched_paths": [],
            "matched_specs": [],
            "registry_configured": False,
            "enforcement_sensitive": False,
        },
        "review": review,
        "gate_invocation_id": "gate-1",
    }
    schema = load_json_schema(ROOT / "schemas" / "pr_review_gate.schema.json")

    validate_instance(schema, payload, "pr")
    payload["runtime_checkpoint"] = {}
    with pytest.raises(SpecRailError):
        validate_instance(schema, payload, "pr")
