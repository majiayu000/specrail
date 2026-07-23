from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402
from runtime_gate_rules import RUNTIME_V1_ITEM_FIELDS  # noqa: E402
from schema_validation import load_json_schema  # noqa: E402
from specrail_lib import (  # noqa: E402
    InstanceMismatch,
    SchemaDefinitionError,
    SpecRailError,
    validate_instance,
)


def runtime_checkpoint_schema() -> dict[str, object]:
    return load_json_schema(ROOT / "schemas" / "runtime_checkpoint.schema.json")


def pr_review_gate_schema() -> dict[str, object]:
    return load_json_schema(ROOT / "schemas" / "pr_review_gate.schema.json")


def review_result_schema() -> dict[str, object]:
    return json.loads(
        (ROOT / "schemas" / "review_result.schema.json").read_text(encoding="utf-8")
    )


def valid_checkpoint() -> dict[str, object]:
    return {
        "checkpoint_version": 1,
        "tranche_id": "2026-07-03-schema-instance-t01",
        "repo": "example/repo",
        "scope": "schema instance validation",
        "status": "handoff",
        "context_budget": {
            "window_tokens": 258400,
            "soft_stop_ratio": 0.5,
            "hard_stop_ratio": 0.65,
            "critical_stop_ratio": 0.75,
        },
        "output_firewall": {
            "raw_log_policy": "file_only",
            "max_parent_stdout_lines": 150,
            "max_subagent_final_lines": 150,
            "artifact_root": "artifacts/logs/schema-instance",
        },
        "items": [
            {
                "issue": 40,
                "state": "needs_review",
                "spec_status": "complete",
                "spec_status_reason": "specs/GH40 has product, tech, and tasks",
                "local_verification": [
                    {
                        "command": "uvx pytest -q",
                        "status": "passed",
                        "evidence": "artifacts/logs/schema-instance/pytest.log",
                    }
                ],
                "next_action": "refresh PR evidence",
            }
        ],
        "resume_prompt": "Refresh remote truth and continue.",
    }


def v1_snapshot(head_sha: str = "a" * 40) -> dict[str, object]:
    return {
        "head_sha": head_sha,
        "base_tree_oid": "b" * 40,
        "algorithm": "sha256",
        "normalization": "specrail-v1",
        "collector": "github_pr_evidence",
    }


def v1_content_hashes() -> dict[str, str]:
    return {
        "code_inputs": "1" * 64,
        "spec_files": "2" * 64,
        "pr_metadata": "3" * 64,
    }


def v1_component_binding() -> dict[str, object]:
    return {
        "content_binding_version": 1,
        "covered_categories": ["code_inputs", "spec_files"],
        "content_bindings": {
            "code_inputs": "1" * 64,
            "spec_files": "2" * 64,
        },
    }


def v1_reuse_audit() -> dict[str, object]:
    return {
        "artifact_id": "workflow-check-run-123",
        "original_head_sha": "c" * 40,
        "covered_categories": ["code_inputs", "spec_files"],
        "original_content_bindings": {
            "code_inputs": "1" * 64,
            "spec_files": "2" * 64,
        },
        "current_content_bindings": {
            "code_inputs": "1" * 64,
            "spec_files": "2" * 64,
        },
        "collector_provenance": v1_snapshot(),
        "reason": "all covered category hashes match the current snapshot",
    }


def valid_v1_pr_evidence() -> dict[str, object]:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    evidence.update(
        {
            "content_binding_version": 1,
            "snapshot": v1_snapshot(evidence["head_sha"]),
            "content_hashes": v1_content_hashes(),
            "reused_components": [v1_reuse_audit()],
        }
    )
    for index, check in enumerate(evidence["checks"], start=1):
        check.update(v1_component_binding())
        check["artifact_id"] = f"github-check-{index}"
        check["head_sha"] = evidence["head_sha"]
    return evidence


def valid_v1_review_result() -> dict[str, object]:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review.update(v1_component_binding())
    review["content_binding_evidence"] = {
        "artifact_id": "content-binding-pr-489-aaaa00000000",
        "path": "artifacts/content-bindings/pr-489.json",
        "sha256": "d" * 64,
    }
    return review


def valid_v1_checkpoint() -> dict[str, object]:
    checkpoint = valid_checkpoint()
    checkpoint["items"][0].update(
        {
            "content_binding_version": 1,
            "snapshot": v1_snapshot(),
            "content_hashes": v1_content_hashes(),
            "reused_components": [v1_reuse_audit()],
        }
    )
    return checkpoint


def test_validate_instance_supports_local_schema_subset() -> None:
    schema = {
        "type": "object",
        "required": ["name", "count", "tags"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "count": {"type": "integer", "minimum": 1},
            "mode": {"enum": ["dry_run", "required"]},
            "tags": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "fixed": {"const": True},
        },
    }

    validate_instance(
        schema,
        {
            "name": "SpecRail",
            "count": 1,
            "mode": "dry_run",
            "tags": ["runtime"],
            "fixed": True,
        },
    )


def test_validate_instance_supports_schema_composition_and_conditionals() -> None:
    schema = {
        "allOf": [
            {
                "anyOf": [
                    {"required": ["mode"]},
                    {"required": ["legacy"]},
                ]
            },
            {
                "if": {
                    "properties": {"mode": {"const": "sensitive"}},
                    "required": ["mode"],
                },
                "then": {"required": ["approval"]},
                "else": {"properties": {"approval": {"const": None}}},
            },
        ]
    }

    validate_instance(schema, {"mode": "sensitive", "approval": "maintainer"})
    validate_instance(schema, {"legacy": True})

    with pytest.raises(InstanceMismatch, match="approval: missing required field"):
        validate_instance(schema, {"mode": "sensitive"})
    with pytest.raises(InstanceMismatch, match="expected const None"):
        validate_instance(schema, {"legacy": True, "approval": "forged"})


@pytest.mark.parametrize(
    "schema",
    [
        {
            "if": {"typoKeyword": True},
            "then": {"required": ["approval"]},
        },
        {
            "anyOf": [
                {"typoKeyword": True},
                {"required": ["legacy"]},
            ]
        },
        {
            "allOf": [
                {
                    "if": {"const": "current"},
                    "then": {"const": "current"},
                    "else": {
                        "properties": {
                            "nested": {"typoKeyword": True},
                        }
                    },
                }
            ]
        },
    ],
)
def test_validate_instance_rejects_invalid_nested_schema_before_evaluation(
    schema: dict[str, object],
) -> None:
    with pytest.raises(
        SchemaDefinitionError,
        match="unsupported JSON Schema keyword",
    ):
        validate_instance(schema, {"legacy": True})


def test_load_json_schema_rejects_reference_escape(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (tmp_path / "outside.schema.json").write_text(
        '{"type":"object"}', encoding="utf-8"
    )
    entry = schema_dir / "entry.schema.json"
    entry.write_text(
        '{"$ref":"../outside.schema.json"}', encoding="utf-8"
    )

    with pytest.raises(SchemaDefinitionError, match="escapes the schema directory"):
        load_json_schema(entry)


def test_load_json_schema_rejects_reference_cycle(tmp_path: Path) -> None:
    entry = tmp_path / "entry.schema.json"
    helper = tmp_path / "helper.schema.json"
    entry.write_text('{"$ref":"helper.schema.json"}', encoding="utf-8")
    helper.write_text('{"$ref":"entry.schema.json"}', encoding="utf-8")

    with pytest.raises(SchemaDefinitionError, match="circular"):
        load_json_schema(entry)


def test_validate_instance_supports_min_properties_for_approved_spec_revisions() -> None:
    approved_spec_schema = pr_review_gate_schema()["properties"]["approved_spec"]
    revisions_schema = approved_spec_schema["properties"]["spec_revisions"]
    revision = {
        "source_commit_sha": "a" * 40,
        "pr_number": 97,
        "merged_at": "2026-07-15T00:00:00Z",
        "merge_commit_sha": "b" * 40,
    }

    validate_instance(
        revisions_schema,
        {
            "specs/GH97/product.md": revision,
            "specs/GH97/tech.md": revision,
        },
    )
    validate_instance({"type": "object", "minProperties": 0}, {})


@pytest.mark.parametrize("threshold", [True, -1, 1.5, "2"])
def test_validate_instance_rejects_invalid_min_properties_keyword(
    threshold: object,
) -> None:
    with pytest.raises(
        SpecRailError,
        match="minProperties must be a non-negative integer",
    ):
        validate_instance({"minProperties": threshold}, {})


def test_validate_instance_rejects_min_properties_for_non_object_instance() -> None:
    with pytest.raises(
        SpecRailError,
        match="minProperties requires an object instance",
    ):
        validate_instance({"minProperties": 1}, [])


def test_validate_instance_rejects_object_below_min_properties_threshold() -> None:
    with pytest.raises(
        SpecRailError,
        match="object has fewer properties than minProperties",
    ):
        validate_instance({"type": "object", "minProperties": 2}, {"only": 1})


def test_validate_instance_reports_required_enum_additional_and_unsupported() -> None:
    with pytest.raises(SpecRailError, match=r"\$\.name: missing required field"):
        validate_instance({"type": "object", "required": ["name"]}, {})

    with pytest.raises(SpecRailError, match="not in enum"):
        validate_instance({"enum": ["allowed"]}, "blocked")

    with pytest.raises(SpecRailError, match="additional property"):
        validate_instance(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"name": {"type": "string"}},
            },
            {"name": "ok", "extra": True},
        )

    with pytest.raises(SpecRailError, match="unsupported JSON Schema keyword"):
        validate_instance({"type": "string", "maxLength": 3}, "value")


def test_validate_instance_enforces_string_pattern() -> None:
    validate_instance({"type": "string", "pattern": "^[0-9a-f]{40}$"}, "a" * 40)

    with pytest.raises(SpecRailError, match="does not match pattern"):
        validate_instance({"type": "string", "pattern": "^[0-9a-f]{40}$"}, "xyz")


def test_runtime_checkpoint_fixture_instances_validate_against_schema() -> None:
    schema = runtime_checkpoint_schema()
    for fixture in sorted((ROOT / "examples" / "fixtures").glob("runtime-*.json")):
        validate_instance(schema, json.loads(fixture.read_text(encoding="utf-8")))


def test_pr_gate_fixture_instances_validate_against_schema() -> None:
    schema = pr_review_gate_schema()
    for fixture in sorted((ROOT / "examples" / "fixtures").glob("pr-*.json")):
        if fixture.name == "pr-missing-thread-resolver.json":
            continue
        validate_instance(schema, json.loads(fixture.read_text(encoding="utf-8")))


def test_pr_gate_schema_rejects_missing_thread_resolver_fixture() -> None:
    schema = pr_review_gate_schema()
    fixture = ROOT / "examples" / "fixtures" / "pr-missing-thread-resolver.json"

    with pytest.raises(SpecRailError, match="resolved_by"):
        validate_instance(schema, json.loads(fixture.read_text(encoding="utf-8")))


@pytest.mark.parametrize("missing", ["original_author", "original_comment_id"])
def test_pr_gate_schema_requires_root_comment_identity(missing: str) -> None:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    evidence["review_threads"][0].pop(missing)

    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(pr_review_gate_schema(), evidence)


@pytest.mark.parametrize("location", ["top_level", "review_evidence"])
def test_pr_gate_schema_requires_review_execution(location: str) -> None:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    if location == "top_level":
        evidence.pop("review_execution")
    else:
        evidence["review_evidence"].pop("review_execution")

    with pytest.raises(InstanceMismatch, match="review_execution.*missing required field"):
        validate_instance(pr_review_gate_schema(), evidence)


def test_pr_gate_schema_accepts_structured_partial_issue_reference() -> None:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    evidence["linked_issue"] = 671
    evidence["issue_reference"] = {
        "number": 671,
        "kind": "partial",
        "source": "pr_body",
        "verified": True,
        "state": "OPEN",
        "url": "https://github.com/majiayu000/remem/issues/671",
        "closing_issue_numbers": [806],
    }

    validate_instance(pr_review_gate_schema(), evidence)


def _approved_spec_evidence() -> dict[str, object]:
    revision = {
        "source_commit_sha": "a" * 40,
        "pr_number": 168,
        "merged_at": "2026-07-22T01:00:00Z",
        "merge_commit_sha": "b" * 40,
    }
    return {
        "repository": "majiayu000/specrail",
        "issue": 168,
        "spec_paths": ["specs/GH168/product.md", "specs/GH168/tech.md"],
        "content_hashes": {
            "specs/GH168/product.md": "c" * 64,
            "specs/GH168/tech.md": "d" * 64,
        },
        "spec_revisions": {
            "specs/GH168/product.md": revision,
            "specs/GH168/tech.md": revision,
        },
        "approved_at": "2026-07-22T01:00:00Z",
        "maintainer_actor": "maintainer",
        "state_source": "label",
        "state_trusted": True,
        "default_base_ref": "main",
        "default_base_sha": "e" * 40,
    }


def _spec_approval_evidence() -> dict[str, object]:
    return {
        "lifecycle_state": "spec_approved",
        "state_source": "label",
        "state_trusted": True,
        "maintainer_actor": "maintainer",
        "approved_at": "2026-07-22T02:00:00Z",
        "approval_source": "github_pr_review",
        "approval_url": "https://github.com/majiayu000/specrail/pull/177#pullrequestreview-1",
        "commit_oid": "f" * 40,
        "artifact_paths": [
            "specs/GH168/product.md",
            "specs/GH168/tech.md",
            "specs/GH168/tasks.md",
        ],
        "spec_artifacts_sha256": "1" * 64,
    }


def _sensitive_pr_evidence(
    route: str, approval_key: str, approval: dict[str, object]
) -> dict[str, object]:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    evidence["enforcement_sensitive"] = True
    evidence["sensitive_route"] = route
    evidence[approval_key] = approval
    return evidence


def _sensitive_classification() -> dict[str, object]:
    paths = ["specs/GH168/product.md"]
    return {
        "source": "github_changed_files",
        "changed_paths": paths,
        "spec_refs": paths,
        "matched_paths": [],
        "matched_specs": paths,
        "registry_configured": True,
        "enforcement_sensitive": True,
    }


@pytest.mark.parametrize(
    ("route", "approval_key", "approval"),
    [
        ("approved_spec", "approved_spec", _approved_spec_evidence()),
        ("spec_revision", "spec_approval", _spec_approval_evidence()),
    ],
)
def test_pr_gate_schema_accepts_matching_sensitive_route_evidence(
    route: str, approval_key: str, approval: dict[str, object]
) -> None:
    validate_instance(
        pr_review_gate_schema(),
        _sensitive_pr_evidence(route, approval_key, approval),
    )


@pytest.mark.parametrize(
    ("route", "approval_key", "approval"),
    [
        ("approved_spec", "spec_approval", _spec_approval_evidence()),
        ("spec_revision", "approved_spec", _approved_spec_evidence()),
    ],
)
def test_pr_gate_schema_rejects_sensitive_route_evidence_mismatch(
    route: str, approval_key: str, approval: dict[str, object]
) -> None:
    evidence = _sensitive_pr_evidence(route, approval_key, approval)
    with pytest.raises(InstanceMismatch, match="anyOf"):
        validate_instance(pr_review_gate_schema(), evidence)


def test_pr_gate_schema_rejects_mixed_sensitive_evidence() -> None:
    evidence = _sensitive_pr_evidence(
        "spec_revision", "spec_approval", _spec_approval_evidence()
    )
    evidence["approved_spec"] = _approved_spec_evidence()
    with pytest.raises(InstanceMismatch, match="anyOf"):
        validate_instance(pr_review_gate_schema(), evidence)


def test_pr_gate_schema_requires_sensitive_route() -> None:
    evidence = _sensitive_pr_evidence(
        "spec_revision", "spec_approval", _spec_approval_evidence()
    )
    evidence.pop("sensitive_route")
    with pytest.raises(InstanceMismatch, match="sensitive_route.*missing required field"):
        validate_instance(pr_review_gate_schema(), evidence)


def test_pr_gate_schema_requires_route_for_sensitive_classification() -> None:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    evidence["sensitive_classification"] = _sensitive_classification()
    with pytest.raises(InstanceMismatch, match="sensitive_route.*missing required field"):
        validate_instance(pr_review_gate_schema(), evidence)


@pytest.mark.parametrize("missing", sorted(_spec_approval_evidence()))
def test_pr_gate_schema_rejects_partial_spec_approval(missing: str) -> None:
    approval = _spec_approval_evidence()
    approval.pop(missing)
    evidence = _sensitive_pr_evidence("spec_revision", "spec_approval", approval)
    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(pr_review_gate_schema(), evidence)


def test_pr_gate_schema_rejects_unknown_spec_approval_field() -> None:
    approval = _spec_approval_evidence()
    approval["agent_approved"] = True
    evidence = _sensitive_pr_evidence("spec_revision", "spec_approval", approval)
    with pytest.raises(InstanceMismatch, match="additional property"):
        validate_instance(pr_review_gate_schema(), evidence)


def test_review_result_v2_fixture_validates_against_schema() -> None:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )

    validate_instance(review_result_schema(), review)


def test_review_result_schema_rejects_orphan_gate_authorization() -> None:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review["gate_authorization"] = "stale degraded-review authorization"

    with pytest.raises(InstanceMismatch, match="gate_status.*missing required field"):
        validate_instance(review_result_schema(), review)


def test_review_result_schema_rejects_blank_gate_authorization() -> None:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "   \t"
    review["body"] = review["body"].replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )

    with pytest.raises(InstanceMismatch, match="gate_authorization.*pattern"):
        validate_instance(review_result_schema(), review)


@pytest.mark.parametrize("missing", ["review_round", "review_mode"])
def test_review_result_schema_requires_paired_round_fields(missing: str) -> None:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review.update({"review_round": 2, "review_mode": "resumed"})
    review.pop(missing)

    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(review_result_schema(), review)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "superseded"])
def test_review_result_schema_rejects_null_completion_for_non_pending(
    status: str,
) -> None:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review["status"] = status
    review["review_completed_at"] = None

    with pytest.raises(InstanceMismatch, match="status.*const"):
        validate_instance(review_result_schema(), review)


@pytest.mark.parametrize("status", ["resolved", "obsolete"])
def test_review_result_schema_requires_prior_closure_evidence(status: str) -> None:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review["prior_findings"] = [
        {
            "id": "prior-finding",
            "source_head_sha": "a" * 40,
            "summary": "Closed without proof.",
            "status": status,
        }
    ]

    with pytest.raises(InstanceMismatch, match="closure_evidence.*missing required field"):
        validate_instance(review_result_schema(), review)


def test_review_result_schema_rejects_legacy_source_only_artifact() -> None:
    legacy = {
        "verdict": "REJECT",
        "body": "## Summary\nlegacy\n\n## Verdict\nREJECT",
        "comments": [],
    }

    with pytest.raises(SpecRailError, match="artifact_id"):
        validate_instance(review_result_schema(), legacy)


def bounded_review_result() -> dict[str, object]:
    review = json.loads(
        (ROOT / "examples" / "fixtures" / "review-valid.json").read_text(
            encoding="utf-8"
        )
    )
    review.update(
        {
            "round_policy_version": 1,
            "review_round": 2,
            "review_mode": "resumed",
            "base_head_sha": "b" * 40,
            "diff_sha256": "d" * 64,
            "prior_findings": [
                {
                    "finding_id": "F-1",
                    "source_artifact_id": "round-1",
                    "status": "resolved",
                    "evidence_pointer": {"kind": "thread", "value": "PRRT_167"},
                }
            ],
        }
    )
    return review


def test_review_result_schema_accepts_bounded_compact_finding() -> None:
    validate_instance(review_result_schema(), bounded_review_result())


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [
        ({"kind": "thread", "value": "fixed it"}, "anyOf"),
        ({"kind": "comment", "value": "PRRT_wrong-kind"}, "anyOf"),
        ({"kind": "commit", "value": "short"}, "anyOf"),
        ({"kind": "unknown", "value": "PRRC_1"}, "anyOf"),
    ],
)
def test_review_result_schema_rejects_untyped_compact_pointer(
    pointer: dict[str, str], expected: str
) -> None:
    review = bounded_review_result()
    review["prior_findings"][0]["evidence_pointer"] = pointer
    with pytest.raises(InstanceMismatch, match=expected):
        validate_instance(review_result_schema(), review)


def test_review_result_schema_rejects_bounded_history_prose() -> None:
    review = bounded_review_result()
    review["prior_findings"][0]["summary"] = "forbidden history replay"
    with pytest.raises(InstanceMismatch, match="additional property"):
        validate_instance(review_result_schema(), review)


@pytest.mark.parametrize("missing", ["base_head_sha", "diff_sha256"])
def test_review_result_schema_requires_bounded_scoped_provenance(missing: str) -> None:
    review = bounded_review_result()
    review.pop(missing)
    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(review_result_schema(), review)


def test_review_result_schema_rejects_bounded_round_two_full() -> None:
    review = bounded_review_result()
    review["review_mode"] = "full"
    review["human_full_review_request"] = "does not expand bounded policy"
    with pytest.raises(InstanceMismatch, match="review_mode.*enum"):
        validate_instance(review_result_schema(), review)


def test_runtime_checkpoint_inline_valid_instance_matches_schema() -> None:
    validate_instance(runtime_checkpoint_schema(), valid_checkpoint())


def test_runtime_checkpoint_required_field_is_rejected_by_schema_and_gate() -> None:
    checkpoint = valid_checkpoint()
    checkpoint.pop("resume_prompt")

    with pytest.raises(SpecRailError, match="resume_prompt"):
        validate_instance(runtime_checkpoint_schema(), checkpoint)

    result = evaluate_checkpoint(checkpoint)
    assert result["decision"] == "blocked"
    assert any("resume_prompt" in error for error in result["errors"])


def _valid_v3_checkpoint() -> dict[str, object]:
    checkpoint = valid_checkpoint()
    checkpoint["checkpoint_version"] = 3
    checkpoint["tranche_started_at"] = "2026-07-17T01:00:00Z"
    checkpoint["tranche_session_offset"] = 0
    return checkpoint


def test_runtime_checkpoint_v3_schema_accepts_real_tranche_fields() -> None:
    validate_instance(runtime_checkpoint_schema(), _valid_v3_checkpoint())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("tranche_started_at", None),
        ("tranche_session_offset", None),
        ("tranche_session_offset", -1),
    ],
)
def test_runtime_checkpoint_v3_schema_rejects_null_or_negative_tranche_fields(
    key: str, value: object
) -> None:
    checkpoint = _valid_v3_checkpoint()
    checkpoint[key] = value

    with pytest.raises(SpecRailError):
        validate_instance(runtime_checkpoint_schema(), checkpoint)


def test_v1_content_binding_instances_validate_across_all_three_schemas() -> None:
    validate_instance(pr_review_gate_schema(), valid_v1_pr_evidence())
    validate_instance(review_result_schema(), valid_v1_review_result())
    validate_instance(runtime_checkpoint_schema(), valid_v1_checkpoint())


@pytest.mark.parametrize("missing", ["snapshot", "content_hashes", "reused_components"])
def test_pr_gate_schema_rejects_partial_v1_wrapper(missing: str) -> None:
    evidence = valid_v1_pr_evidence()
    evidence.pop(missing)

    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(pr_review_gate_schema(), evidence)


@pytest.mark.parametrize(
    "missing", ["covered_categories", "content_bindings", "content_binding_evidence"]
)
def test_review_result_schema_rejects_partial_v1_component(missing: str) -> None:
    review = valid_v1_review_result()
    review.pop(missing)

    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(review_result_schema(), review)


@pytest.mark.parametrize("missing", ["snapshot", "content_hashes", "reused_components"])
def test_runtime_checkpoint_schema_rejects_partial_v1_wrapper(missing: str) -> None:
    checkpoint = valid_v1_checkpoint()
    checkpoint["items"][0].pop(missing)

    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(runtime_checkpoint_schema(), checkpoint)


@pytest.mark.parametrize("schema_kind", ["pr_gate", "review", "runtime"])
def test_content_binding_schemas_reject_unsupported_version(schema_kind: str) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        instance["content_binding_version"] = 2
        schema = pr_review_gate_schema()
    elif schema_kind == "review":
        instance = valid_v1_review_result()
        instance["content_binding_version"] = 2
        schema = review_result_schema()
    else:
        instance = valid_v1_checkpoint()
        instance["items"][0]["content_binding_version"] = 2
        schema = runtime_checkpoint_schema()

    with pytest.raises(InstanceMismatch, match="content_binding_version.*const"):
        validate_instance(schema, instance)


@pytest.mark.parametrize("schema_kind", ["pr_gate", "review", "runtime"])
def test_content_binding_schemas_reject_v1_fields_mixed_into_legacy(
    schema_kind: str,
) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        instance.pop("content_binding_version")
        schema = pr_review_gate_schema()
    elif schema_kind == "review":
        instance = valid_v1_review_result()
        instance.pop("content_binding_version")
        schema = review_result_schema()
    else:
        instance = valid_v1_checkpoint()
        instance["items"][0].pop("content_binding_version")
        schema = runtime_checkpoint_schema()

    with pytest.raises(InstanceMismatch):
        validate_instance(schema, instance)


def test_pr_gate_schema_rejects_versioned_component_without_v1_wrapper() -> None:
    evidence = valid_v1_pr_evidence()
    for key in [
        "content_binding_version",
        "snapshot",
        "content_hashes",
        "reused_components",
    ]:
        evidence.pop(key)

    with pytest.raises(InstanceMismatch):
        validate_instance(pr_review_gate_schema(), evidence)


def test_pr_gate_v1_wrapper_accepts_current_head_legacy_check() -> None:
    evidence = valid_v1_pr_evidence()
    for key in [
        "content_binding_version",
        "covered_categories",
        "content_bindings",
    ]:
        evidence["checks"][0].pop(key)

    validate_instance(pr_review_gate_schema(), evidence)


@pytest.mark.parametrize("schema_kind", ["pr_gate", "review", "runtime"])
def test_content_binding_schemas_reject_unknown_coverage_category(
    schema_kind: str,
) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        instance["checks"][0]["covered_categories"] = ["dependencies"]
        schema = pr_review_gate_schema()
    elif schema_kind == "review":
        instance = valid_v1_review_result()
        instance["covered_categories"] = ["dependencies"]
        schema = review_result_schema()
    else:
        instance = valid_v1_checkpoint()
        instance["items"][0]["reused_components"][0]["covered_categories"] = [
            "dependencies"
        ]
        schema = runtime_checkpoint_schema()

    with pytest.raises(InstanceMismatch, match="not in enum"):
        validate_instance(schema, instance)


@pytest.mark.parametrize("schema_kind", ["pr_gate", "review", "runtime"])
def test_content_binding_schemas_reject_empty_coverage(schema_kind: str) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        instance["checks"][0]["covered_categories"] = []
        schema = pr_review_gate_schema()
    elif schema_kind == "review":
        instance = valid_v1_review_result()
        instance["covered_categories"] = []
        schema = review_result_schema()
    else:
        instance = valid_v1_checkpoint()
        instance["items"][0]["reused_components"][0]["covered_categories"] = []
        schema = runtime_checkpoint_schema()

    with pytest.raises(InstanceMismatch, match="shorter than minItems"):
        validate_instance(schema, instance)


@pytest.mark.parametrize("schema_kind", ["pr_gate", "review", "runtime"])
def test_content_binding_schemas_reject_unknown_binding_key(schema_kind: str) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        bindings = instance["checks"][0]["content_bindings"]
        schema = pr_review_gate_schema()
    elif schema_kind == "review":
        instance = valid_v1_review_result()
        bindings = instance["content_bindings"]
        schema = review_result_schema()
    else:
        instance = valid_v1_checkpoint()
        bindings = instance["items"][0]["reused_components"][0][
            "current_content_bindings"
        ]
        schema = runtime_checkpoint_schema()
    bindings["dependencies"] = "4" * 64

    with pytest.raises(InstanceMismatch, match="additional property"):
        validate_instance(schema, instance)


@pytest.mark.parametrize(
    "missing",
    [
        "artifact_id",
        "original_head_sha",
        "covered_categories",
        "original_content_bindings",
        "current_content_bindings",
        "collector_provenance",
        "reason",
    ],
)
@pytest.mark.parametrize("schema_kind", ["pr_gate", "runtime"])
def test_reuse_audit_schema_requires_every_audit_field(
    schema_kind: str, missing: str
) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        audit = instance["reused_components"][0]
        schema = pr_review_gate_schema()
    else:
        instance = valid_v1_checkpoint()
        audit = instance["items"][0]["reused_components"][0]
        schema = runtime_checkpoint_schema()
    audit.pop(missing)

    with pytest.raises(InstanceMismatch, match=rf"{missing}.*missing required field"):
        validate_instance(schema, instance)


@pytest.mark.parametrize("schema_kind", ["pr_gate", "runtime"])
def test_snapshot_schema_rejects_unknown_or_partial_provenance(schema_kind: str) -> None:
    if schema_kind == "pr_gate":
        instance = valid_v1_pr_evidence()
        snapshot = instance["snapshot"]
        schema = pr_review_gate_schema()
    else:
        instance = valid_v1_checkpoint()
        snapshot = instance["items"][0]["snapshot"]
        schema = runtime_checkpoint_schema()
    snapshot.pop("base_tree_oid")
    snapshot["sha_provenance"] = "caller supplied"

    with pytest.raises(InstanceMismatch):
        validate_instance(schema, instance)


def test_component_binding_key_equality_is_reserved_for_semantic_validator() -> None:
    review = valid_v1_review_result()
    review["covered_categories"] = ["code_inputs"]

    validate_instance(review_result_schema(), review)


@pytest.mark.parametrize(
    "field",
    ["covered_categories", "future_tier_override", "original_content_bindings"],
)
def test_runtime_schema_closes_v1_item_field_set(field: str) -> None:
    checkpoint = valid_v1_checkpoint()
    checkpoint["items"][0][field] = {}

    with pytest.raises(InstanceMismatch, match=rf"{field}.*additional property"):
        validate_instance(runtime_checkpoint_schema(), checkpoint)


def test_runtime_schema_keeps_legacy_item_extensions() -> None:
    checkpoint = valid_checkpoint()
    checkpoint["items"][0]["consumer_extension"] = "legacy metadata"

    validate_instance(runtime_checkpoint_schema(), checkpoint)


def test_runtime_v1_schema_and_semantic_field_sets_match() -> None:
    item_schema = runtime_checkpoint_schema()["properties"]["items"]["items"]
    schema_fields = set(item_schema["allOf"][0]["then"]["properties"])

    assert schema_fields == RUNTIME_V1_ITEM_FIELDS


def _checks_unavailable_evidence() -> dict[str, object]:
    evidence = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    evidence["checks"] = []
    evidence["base_ref"] = "spec/GH60-transactional-patching"
    evidence["default_base_ref"] = "main"
    evidence["checks_unavailable"] = {
        "reason": "hosted_ci_not_triggered_for_base",
        "base_ref": "spec/GH60-transactional-patching",
        "default_base_ref": "main",
        "workflow_trigger_evidence": (
            ".github/workflows/ci.yml: on.pull_request.branches == ['main']"
        ),
        "local_verification": ["cargo test --workspace --locked"],
        "verified": True,
    }
    return evidence


def test_pr_gate_schema_accepts_checks_unavailable_declaration() -> None:
    validate_instance(pr_review_gate_schema(), _checks_unavailable_evidence())


@pytest.mark.parametrize(
    "mutation",
    [
        {"reason": "ci_is_slow"},
        {"verified": False},
        {"local_verification": []},
        {"extra": "x"},
    ],
)
def test_pr_gate_schema_rejects_invalid_checks_unavailable(
    mutation: dict[str, object],
) -> None:
    evidence = _checks_unavailable_evidence()
    evidence["checks_unavailable"].update(mutation)

    with pytest.raises(InstanceMismatch):
        validate_instance(pr_review_gate_schema(), evidence)
