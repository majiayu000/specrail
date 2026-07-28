from __future__ import annotations

import json
import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from schema_validation import SpecRailError, load_json_schema, validate_instance  # noqa: E402
from review_json_gate import evaluate_review_gate  # noqa: E402


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
        "base_head_sha": "b" * 40,
        "head_sha": "a" * 40,
        "diff_sha256": "c" * 64,
        "review_source": "independent_lane",
        "round": 1,
        "mode": "full",
        "verdict": "clean",
        "body": "## Summary\nReviewed.\n\n## Verdict\nClean.",
        "findings": [],
    }


def valid_attestation(
    review: dict[str, object],
) -> dict[str, object]:
    attestation: dict[str, object] = {
        "artifact_id": review["artifact_id"],
        "lane_id": "review-lane-1",
        "reviewer_actor": "reviewer-agent-1",
        "head_sha": review["head_sha"],
        "invocation_id": "gate-1",
    }
    prior = review.get("prior_review")
    if review.get("round") == 2 and isinstance(prior, dict):
        attestation["prior_artifact_id"] = prior["artifact_id"]
        attestation["prior_head_sha"] = prior["head_sha"]
    return attestation


def valid_pr_evidence() -> dict[str, object]:
    review = valid_review()
    changed = ["src/app.py"]
    return {
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
        "checks": [{
            "name": "tests",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "head_sha": "a" * 40,
        }],
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
        "review_attestation": valid_attestation(review),
        "gate_invocation_id": "gate-1",
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

    embedded_attestation = valid_review()
    embedded_attestation["review_attestation"] = {}
    with pytest.raises(SpecRailError):
        validate_instance(schema, embedded_attestation, "review")


def test_compact_pr_schema_accepts_current_evidence() -> None:
    payload = valid_pr_evidence()
    schema = load_json_schema(ROOT / "schemas" / "pr_review_gate.schema.json")

    validate_instance(schema, payload, "pr")
    unavailable = {
        "reason": "hosted_ci_not_triggered_for_base",
        "base_ref": "feature-base",
        "default_base_ref": "main",
        "workflow_trigger_evidence": "workflow only triggers for main",
        "local_verification": ["python3 -m pytest -q"],
        "verified": True,
    }
    payload["checks"] = []
    payload["base_ref"] = "feature-base"
    payload["default_base_ref"] = "main"
    payload["checks_unavailable"] = unavailable
    validate_instance(schema, payload, "pr")
    for field in ("base_ref", "default_base_ref"):
        missing_ref = copy.deepcopy(payload)
        missing_ref.pop(field)
        with pytest.raises(SpecRailError):
            validate_instance(schema, missing_ref, f"missing {field}")
        blank_ref = copy.deepcopy(payload)
        blank_ref[field] = " "
        with pytest.raises(SpecRailError):
            validate_instance(schema, blank_ref, f"blank {field}")
    for field in (
        "base_ref",
        "default_base_ref",
        "workflow_trigger_evidence",
    ):
        blank_declaration = copy.deepcopy(payload)
        blank_declaration["checks_unavailable"][field] = " "
        with pytest.raises(SpecRailError):
            validate_instance(schema, blank_declaration, f"blank declaration {field}")
    blank_command = copy.deepcopy(payload)
    blank_command["checks_unavailable"]["local_verification"] = [" "]
    with pytest.raises(SpecRailError):
        validate_instance(schema, blank_command, "blank local verification")
    payload["checks"] = [
        {
            "name": "tests",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "head_sha": "a" * 40,
        }
    ]
    with pytest.raises(SpecRailError):
        validate_instance(schema, payload, "pr")
    payload.pop("checks_unavailable")
    payload["runtime_checkpoint"] = {}
    with pytest.raises(SpecRailError):
        validate_instance(schema, payload, "pr")


def test_attestation_schema_runtime_parity_matrix() -> None:
    schema = load_json_schema(ROOT / "schemas" / "pr_review_gate.schema.json")
    cases: list[tuple[str, dict[str, object], bool]] = []

    standard = valid_pr_evidence()
    cases.append(("standard valid", standard, True))
    missing = copy.deepcopy(standard)
    missing.pop("review_attestation")
    cases.append(("standard missing", missing, False))
    blank = copy.deepcopy(standard)
    blank["review_attestation"]["artifact_id"] = " "
    cases.append(("standard blank", blank, False))
    fastlane = copy.deepcopy(standard)
    fastlane["profile"] = "fastlane"
    fastlane["review"]["profile"] = "fastlane"
    fastlane["review"]["review_source"] = "self_review"
    fastlane.pop("review_attestation")
    cases.append(("fastlane self", fastlane, True))
    fastlane_with_attestation = copy.deepcopy(fastlane)
    fastlane_with_attestation["review_attestation"] = valid_attestation(
        fastlane_with_attestation["review"]
    )
    cases.append(("fastlane attested", fastlane_with_attestation, False))

    for name, payload, expected in cases:
        try:
            validate_instance(schema, payload, name)
            schema_allowed = True
        except SpecRailError:
            schema_allowed = False
        review = payload["review"]
        runtime = evaluate_review_gate(
            review,
            "",
            verify_diff=False,
            requires_independent_review=payload["profile"] != "fastlane",
            gate_invocation_id="gate-1",
            attestation=payload.get("review_attestation"),
        )
        assert schema_allowed is expected, name
        assert (runtime["decision"] == "allowed") is expected, name


def test_round_two_attestation_binds_current_and_prior_artifacts() -> None:
    schema = load_json_schema(ROOT / "schemas" / "pr_review_gate.schema.json")
    payload = valid_pr_evidence()
    prior = copy.deepcopy(payload["review"])
    prior.update({
        "artifact_id": "review-prior",
        "base_head_sha": "d" * 40,
        "head_sha": "b" * 40,
        "verdict": "blocking",
        "findings": [{
            "id": "P1-prior",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Prior defect.",
            "fix_paths": ["src/app.py"],
        }],
    })
    payload["review"].update({
        "round": 2,
        "mode": "diff_only",
        "base_head_sha": "b" * 40,
        "prior_review": prior,
        "findings": [{
            "id": "P1-prior",
            "severity": "P1",
            "status": "resolved",
            "summary": "Prior defect.",
            "introduced_by_diff": False,
        }],
    })
    payload["review_attestation"] = valid_attestation(payload["review"])

    validate_instance(schema, payload, "round2")
    runtime = evaluate_review_gate(
        payload["review"],
        "",
        verify_diff=False,
        requires_independent_review=True,
        gate_invocation_id="gate-1",
        attestation=payload["review_attestation"],
    )
    assert runtime["decision"] == "allowed", runtime["reasons"]

    for field in ("prior_artifact_id", "prior_head_sha"):
        invalid = copy.deepcopy(payload)
        invalid["review_attestation"].pop(field)
        with pytest.raises(SpecRailError):
            validate_instance(schema, invalid, f"round2 missing {field}")
        blocked = evaluate_review_gate(
            invalid["review"],
            "",
            verify_diff=False,
            requires_independent_review=True,
            gate_invocation_id="gate-1",
            attestation=invalid["review_attestation"],
        )
        assert blocked["decision"] == "blocked"
