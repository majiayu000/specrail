from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from shutil import copyfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from review_json_gate import evaluate_review_gate  # noqa: E402
from pr_review_contract import evaluate_review_contract  # noqa: E402
from review_result_semantics import (  # noqa: E402
    ReviewSemanticError,
    UNGATED_DISCLOSURE_MARKER,
    evaluate_review_evidence,
    load_review_manifest,
    validate_review_artifact,
)


def load_review(name: str) -> dict[str, object]:
    review = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    review.setdefault("artifact_id", f"fixture-{name.removesuffix('.json')}")
    review.setdefault("pr", 489)
    review.setdefault("reviewer_lane", "reviewer-1")
    review.setdefault("producer_identity", "agent-reviewer-1")
    review.setdefault("review_source", "independent_lane")
    review.setdefault("review_execution", "local")
    review.setdefault("head_sha", "aaaa000000000000000000000000000000000001")
    review.setdefault("review_started_at", "2026-07-16T00:00:00Z")
    review.setdefault("review_completed_at", "2026-07-16T00:01:00Z")
    review.setdefault("status", "completed")
    review["verdict"] = "blocking"
    review.setdefault("human_final_review_required", False)
    review.setdefault(
        "findings",
        [
            {
                "id": "fixture-finding",
                "severity": "important",
                "actionable": True,
                "summary": "Fixture review finding.",
            }
        ],
    )
    if name != "review-resumed-no-checklist.json":
        review.setdefault("prior_findings", [])
    for index, finding in enumerate(review.get("prior_findings", []), start=1):
        finding.setdefault("id", f"prior-{index}")
        finding.setdefault("source_head_sha", "aaaa000000000000000000000000000000000000")
        if finding.get("status") in {"resolved", "obsolete"}:
            finding.setdefault("closure_evidence", f"review round {index} evidence")
    return review


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def test_review_json_gate_allows_valid_review() -> None:
    result = evaluate_review_gate(load_review("review-valid.json"), load_diff())

    assert result["decision"] == "allowed"
    assert result["verdict"] == "blocking"
    assert result["comment_count"] == 2
    assert result["advisory_only"] is True
    assert result["reasons"] == []
    assert result["missing"] == []
    assert "body includes ## Summary" in result["satisfied"]
    assert "body includes ## Verdict" in result["satisfied"]


def test_review_semantics_blocks_missing_execution_provenance() -> None:
    review = load_review("review-valid.json")
    del review["review_execution"]

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert any("review_execution" in error for error in result["errors"])


def test_review_semantics_blocks_hosted_review_as_primary() -> None:
    review = load_review("review-valid.json")
    review["review_execution"] = "hosted"

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert any("supplemental only" in error for error in result["errors"])


def test_review_json_gate_blocks_clean_verdict_with_findings() -> None:
    review = load_review("review-valid.json")
    review["verdict"] = "clean"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "clean verdict requires zero findings" in result["reasons"]


def test_review_json_gate_blocks_invalid_line() -> None:
    result = evaluate_review_gate(load_review("review-invalid-line.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("src/app.py:99 is not present in the diff" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_severity() -> None:
    result = evaluate_review_gate(load_review("review-invalid-severity.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("severity must be critical" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_range() -> None:
    result = evaluate_review_gate(load_review("review-invalid-range.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("includes lines not present in the diff" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_unpaired_start_range_fields() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment.pop("start_side")

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("start_line and start_side must appear together" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_cross_side_range() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment["start_side"] = "LEFT"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "comment #1 start_side must match side for a range" in result["reasons"]


def test_review_json_gate_blocks_left_side_suggestion() -> None:
    result = evaluate_review_gate(load_review("review-invalid-suggestion-side.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("suggestions are only allowed on RIGHT-side comments" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_empty_suggestion_field() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment["suggestion"] = " "

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("suggestion must be a non-empty string" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_empty_fenced_suggestion() -> None:
    result = evaluate_review_gate(load_review("review-invalid-empty-suggestion.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("suggestion block #1 must be non-empty" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_unclosed_fenced_suggestion() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment["body"] = "Use a complete suggestion block.\n\n```suggestion\n    return title.strip()"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "comment #1 has unterminated suggestion block" in result["reasons"]


def test_review_json_gate_blocks_missing_body_headings() -> None:
    result = evaluate_review_gate(load_review("review-invalid-body.json"), load_diff())

    assert result["decision"] == "blocked"
    assert "body must include ## Summary heading" in result["reasons"]
    assert "body must include ## Verdict heading" in result["reasons"]


def test_review_contract_blocks_tampered_top_level_completion_time() -> None:
    evidence = json.loads(
        (FIXTURES / "pr-clean-authorized.json").read_text(encoding="utf-8")
    )
    evidence["review_completed_at"] = "2026-07-03T23:57:00Z"
    evidence["gate_started_at"] = "2026-07-03T23:57:30Z"
    evidence["gate_query_completed_at"] = "2026-07-03T23:59:00Z"

    _, _, reasons = evaluate_review_contract(evidence, ROOT)

    assert (
        "review_completed_at must match trusted review_evidence.review_completed_at"
        in reasons
    )


def test_review_json_gate_blocks_spec_drift() -> None:
    result = evaluate_review_gate(load_review("review-spec-drift.json"), load_diff())

    assert result["decision"] == "blocked"
    assert "spec_alignment reports drift" in result["reasons"]


def test_review_json_gate_blocks_final_authority_language() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    review["body"] = (
        "## Summary\nI approve this PR. It is approved for merge. You can merge; ship it. "
        "Go ahead and merge. Looks good to merge. Safe to merge. LGTM, merge.\n\n"
        "## Verdict\nThis advisory artifact still cannot grant merge authority."
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("final approval or merge authority" in reason for reason in result["reasons"])


def test_review_json_gate_cli_json_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "checks/review_json_gate.py",
            "--repo",
            ".",
            "--review",
            "examples/fixtures/review-valid.json",
            "--diff",
            "examples/fixtures/pr-diff.patch",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert {
        "decision",
        "verdict",
        "comment_count",
        "advisory_only",
        "reasons",
        "satisfied",
        "missing",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)


def test_review_json_gate_allows_round_two_full_review() -> None:
    result = evaluate_review_gate(load_review("review-round2-full.json"), load_diff())

    assert result["decision"] == "allowed", result["reasons"]


def test_review_json_gate_blocks_round_three_full_without_request() -> None:
    result = evaluate_review_gate(
        load_review("review-round3-full-no-request.json"), load_diff()
    )

    assert result["decision"] == "blocked"
    assert any("exceeds the cap" in reason for reason in result["reasons"])


def test_review_json_gate_allows_round_three_full_with_human_request() -> None:
    result = evaluate_review_gate(
        load_review("review-round3-full-with-request.json"), load_diff()
    )

    assert result["decision"] == "allowed", result["reasons"]


def test_review_json_gate_allows_round_three_diff_only_with_checklist() -> None:
    result = evaluate_review_gate(
        load_review("review-round3-diff-only-checklist.json"), load_diff()
    )

    assert result["decision"] == "allowed", result["reasons"]


def test_review_json_gate_blocks_resumed_round_without_checklist() -> None:
    result = evaluate_review_gate(
        load_review("review-resumed-no-checklist.json"), load_diff()
    )

    assert result["decision"] == "blocked"
    assert any("prior_findings" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_diff_only_without_base_head_sha() -> None:
    review = load_review("review-round3-diff-only-checklist.json")
    del review["base_head_sha"]
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("base_head_sha" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_round_without_mode() -> None:
    review = load_review("review-round2-full.json")
    del review["review_mode"]
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("provided together" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_first_round_diff_only() -> None:
    review = load_review("review-round3-diff-only-checklist.json")
    review["review_round"] = 1
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("review_round >= 2" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_prior_finding_status() -> None:
    review = load_review("review-round3-diff-only-checklist.json")
    review["prior_findings"][0]["status"] = "handled"
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("status must be one of" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_legacy_review_without_v2_terminal_fields() -> None:
    review = load_review("review-valid.json")
    for field in [
        "artifact_id",
        "reviewer_lane",
        "producer_identity",
        "review_source",
        "review_started_at",
        "review_completed_at",
        "status",
        "human_final_review_required",
        "findings",
        "prior_findings",
    ]:
        review.pop(field)

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("artifact_id" in reason for reason in result["reasons"])


@pytest.mark.parametrize("status", ["pending", "failed", "cancelled", "superseded"])
def test_review_semantics_terminal_lifecycle_blocks_merge_readiness(status: str) -> None:
    review = load_review("review-valid.json")
    review["status"] = status
    if status == "pending":
        review["review_completed_at"] = None

    result = validate_review_artifact(review)

    assert result["valid"] is True
    assert any("status is not completed" in item for item in result["blocking_reasons"])


def test_review_semantics_blocks_duplicate_finding_ids() -> None:
    review = load_review("review-valid.json")
    review["findings"].append(dict(review["findings"][0]))

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert "findings IDs must be unique" in result["errors"]


def test_review_semantics_requires_prior_finding_closure_evidence() -> None:
    review = load_review("review-valid.json")
    review["prior_findings"] = [
        {
            "id": "finding-old",
            "source_head_sha": "b" * 40,
            "summary": "Old blocking finding.",
            "status": "resolved",
        }
    ]

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert any("closure_evidence" in item for item in result["errors"])


def test_review_semantics_blocks_unresolved_prior_finding() -> None:
    review = load_review("review-valid.json")
    review["prior_findings"] = [
        {
            "id": "finding-old",
            "source_head_sha": "b" * 40,
            "summary": "Old blocking finding.",
            "status": "unresolved",
        }
    ]

    result = validate_review_artifact(review)

    assert result["valid"] is True
    assert any("unresolved prior finding" in item for item in result["blocking_reasons"])


def test_review_semantics_requires_self_review_human_final_gate() -> None:
    review = load_review("review-valid.json")
    review["review_source"] = "self_review"
    review["human_final_review_required"] = False

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert "self_review requires human_final_review_required=true" in result["errors"]


def clean_terminal_artifact(
    *,
    artifact_id: str = "current-clean",
    lane: str = "reviewer-1",
    producer: str = "agent-reviewer-1",
    head_sha: str = "a" * 40,
) -> dict[str, object]:
    review = load_review("review-valid.json")
    review.update(
        {
            "artifact_id": artifact_id,
            "reviewer_lane": lane,
            "producer_identity": producer,
            "head_sha": head_sha,
            "verdict": "clean",
            "findings": [],
            "prior_findings": [],
        }
    )
    return review


def install_review_schema(repo: Path) -> None:
    schema_dir = repo / "schemas"
    schema_dir.mkdir(exist_ok=True)
    copyfile(
        ROOT / "schemas" / "review_result.schema.json",
        schema_dir / "review_result.schema.json",
    )


def write_review_manifest(
    repo: Path,
    artifacts: list[dict[str, object]],
) -> str:
    install_review_schema(repo)
    review_dir = repo / "artifacts" / "reviews"
    review_dir.mkdir(parents=True)
    lanes: dict[tuple[str, str], list[str]] = {}
    for index, artifact in enumerate(artifacts, start=1):
        path = review_dir / f"artifact-{index}.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        key = (str(artifact["reviewer_lane"]), str(artifact["producer_identity"]))
        lanes.setdefault(key, []).append(path.relative_to(repo).as_posix())
    manifest = {
        "version": 1,
        "pr": 489,
        "head_sha": "a" * 40,
        "human_final_review_required": False,
        "lanes": [
            {
                "lane_id": lane,
                "producer_identity": producer,
                "artifact_paths": paths,
            }
            for (lane, producer), paths in lanes.items()
        ],
    }
    path = review_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path.relative_to(repo).as_posix()


def test_review_manifest_allows_clean_current_head(tmp_path: Path) -> None:
    manifest_path = write_review_manifest(tmp_path, [clean_terminal_artifact()])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert result["errors"] == []
    assert result["blocking_reasons"] == []
    assert result["review_execution"] == "local"


def test_review_manifest_allows_explicit_ungated_review_fields(tmp_path: Path) -> None:
    artifact = clean_terminal_artifact()
    artifact["gate_status"] = "unavailable"
    artifact["gate_authorization"] = "Human authorization: continue without gate"
    body = artifact["body"]
    assert isinstance(body, str)
    artifact["body"] = body.replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert result["errors"] == []
    assert result["blocking_reasons"] == []


def test_review_manifest_blocks_orphan_gate_authorization(tmp_path: Path) -> None:
    artifact = clean_terminal_artifact()
    artifact["gate_authorization"] = "stale degraded-review authorization"
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("gate_status" in item for item in result["errors"])


def test_review_manifest_blocks_blank_gate_authorization(tmp_path: Path) -> None:
    artifact = clean_terminal_artifact()
    artifact["gate_status"] = "unavailable"
    artifact["gate_authorization"] = "   \t"
    body = artifact["body"]
    assert isinstance(body, str)
    artifact["body"] = body.replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("gate_authorization" in item for item in result["errors"])


def test_review_manifest_blocks_unavailable_marker_outside_summary(
    tmp_path: Path,
) -> None:
    artifact = clean_terminal_artifact()
    artifact["gate_status"] = "unavailable"
    artifact["gate_authorization"] = "Human authorization: continue without gate"
    artifact["body"] = f"{artifact['body']}\n\n{UNGATED_DISCLOSURE_MARKER}"
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("## Summary marker" in item for item in result["errors"])


@pytest.mark.parametrize(
    "claim",
    [
        "This review is SpecRail-gated.",
        "This review is verified.",
        "This result is merge-ready.",
    ],
)
def test_review_manifest_blocks_degraded_positive_gate_claims(
    tmp_path: Path,
    claim: str,
) -> None:
    artifact = clean_terminal_artifact()
    artifact["gate_status"] = "unavailable"
    artifact["gate_authorization"] = "Human authorization: continue without gate"
    body = artifact["body"]
    assert isinstance(body, str)
    artifact["body"] = body.replace(
        "## Summary",
        f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}\n\n{claim}",
    )
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("must not claim" in item for item in result["errors"])


@pytest.mark.parametrize("gate_status", [None, "gated"])
def test_review_manifest_blocks_marker_without_matching_status(
    tmp_path: Path,
    gate_status: str | None,
) -> None:
    artifact = clean_terminal_artifact()
    if gate_status is not None:
        artifact["gate_status"] = gate_status
    body = artifact["body"]
    assert isinstance(body, str)
    artifact["body"] = body.replace(
        "## Summary", f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}"
    )
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("gate_status" in item for item in result["errors"])


def test_review_manifest_blocks_conflicting_execution_provenance(tmp_path: Path) -> None:
    hosted = clean_terminal_artifact(
        artifact_id="hosted-current",
        lane="hosted-reviewer",
        producer="hosted-service",
    )
    hosted["review_execution"] = "hosted"
    manifest_path = write_review_manifest(
        tmp_path,
        [clean_terminal_artifact(), hosted],
    )

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any(
        "conflicting review_execution" in item
        for item in result["blocking_reasons"]
    )
    assert result["review_execution"] is None


def test_review_manifest_blocks_pending_current_head_alongside_clean_terminal(
    tmp_path: Path,
) -> None:
    pending = clean_terminal_artifact(
        artifact_id="current-pending",
        lane="reviewer-pending",
        producer="agent-reviewer-pending",
    )
    pending["status"] = "pending"
    pending["review_completed_at"] = None
    manifest_path = write_review_manifest(
        tmp_path,
        [pending, clean_terminal_artifact()],
    )

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any(
        "review status is not completed: pending" in item
        for item in result["blocking_reasons"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (lambda artifact: artifact.update({"forged_unknown_field": True}), "additional property"),
        (lambda artifact: artifact.update({"body": "clean without required headings"}), "does not match pattern"),
        (
            lambda artifact: artifact.update(
                {
                    "comments": [
                        {
                            "path": "checks/pr_gate.py",
                            "line": 1,
                            "side": "MIDDLE",
                            "severity": "important",
                            "body": "invalid side",
                        }
                    ]
                }
            ),
            "is not in enum",
        ),
    ],
)
def test_review_manifest_rejects_schema_invalid_artifact(
    tmp_path: Path,
    mutation: object,
    expected_error: str,
) -> None:
    artifact = clean_terminal_artifact()
    assert callable(mutation)
    mutation(artifact)
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any(expected_error in item for item in result["errors"])
    assert result["review_source"] == "independent_lane"


def test_review_manifest_blocks_duplicate_terminal_for_lane_and_head(tmp_path: Path) -> None:
    artifacts = [
        clean_terminal_artifact(artifact_id="current-1"),
        clean_terminal_artifact(artifact_id="current-2"),
    ]
    manifest_path = write_review_manifest(tmp_path, artifacts)

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("duplicate terminal artifacts" in item for item in result["errors"])


def test_review_manifest_requires_stale_finding_carry_forward(tmp_path: Path) -> None:
    stale = clean_terminal_artifact(artifact_id="old", head_sha="b" * 40)
    stale["verdict"] = "blocking"
    stale["findings"] = [
        {
            "id": "finding-old",
            "severity": "important",
            "actionable": True,
            "summary": "Old blocking finding.",
        }
    ]
    manifest_path = write_review_manifest(
        tmp_path,
        [stale, clean_terminal_artifact()],
    )

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("missing prior finding carry-forward" in item for item in result["errors"])


def test_review_manifest_requires_transitive_unresolved_prior_finding(
    tmp_path: Path,
) -> None:
    stale = clean_terminal_artifact(head_sha="b" * 40)
    stale["prior_findings"] = [
        {
            "id": "finding-transitive",
            "source_head_sha": "c" * 40,
            "summary": "Still unresolved from an omitted source artifact.",
            "status": "unresolved",
        }
    ]
    current = clean_terminal_artifact()
    manifest_path = write_review_manifest(tmp_path, [stale, current])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any(
        "missing prior finding carry-forward: finding-transitive" in item
        for item in result["errors"]
    )


def test_review_manifest_blocks_concurrent_clean_and_blocking_verdicts(tmp_path: Path) -> None:
    blocking = clean_terminal_artifact(
        artifact_id="current-blocking",
        lane="reviewer-2",
        producer="agent-reviewer-2",
    )
    blocking["verdict"] = "blocking"
    blocking["findings"] = [
        {
            "id": "finding-current",
            "severity": "important",
            "actionable": True,
            "summary": "Current blocking finding.",
        }
    ]
    manifest_path = write_review_manifest(
        tmp_path,
        [clean_terminal_artifact(), blocking],
    )

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("verdict is not merge-ready" in item for item in result["blocking_reasons"])
    assert any("blocking current-head finding" in item for item in result["blocking_reasons"])


def test_review_manifest_rejects_multiple_current_head_terminal_artifacts(
    tmp_path: Path,
) -> None:
    manifest_path = write_review_manifest(
        tmp_path,
        [
            clean_terminal_artifact(lane="reviewer-1", producer="agent-reviewer-1"),
            clean_terminal_artifact(
                artifact_id="current-clean-2",
                lane="reviewer-2",
                producer="agent-reviewer-2",
            ),
        ],
    )

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert "review manifest has multiple terminal artifacts for the current head" in result["errors"]


def test_embedded_review_evidence_blocks_non_object_artifact() -> None:
    result = evaluate_review_evidence(
        {
            "pr": 489,
            "head_sha": "a" * 40,
            "errors": [],
            "blocking_reasons": [],
            "artifacts": [None],
        },
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("review artifact must be an object" in item for item in result["errors"])


def test_review_manifest_rejects_artifact_path_traversal(tmp_path: Path) -> None:
    install_review_schema(tmp_path)
    review_dir = tmp_path / "artifacts" / "reviews"
    review_dir.mkdir(parents=True)
    manifest = {
        "version": 1,
        "pr": 489,
        "head_sha": "a" * 40,
        "human_final_review_required": False,
        "lanes": [
            {
                "lane_id": "reviewer-1",
                "producer_identity": "agent-reviewer-1",
                "artifact_paths": ["../outside.json"],
            }
        ],
    }
    manifest_path = review_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = load_review_manifest(
        tmp_path,
        manifest_path.relative_to(tmp_path).as_posix(),
        expected_pr=489,
        expected_head_sha="a" * 40,
    )

    assert any("repo-relative POSIX paths" in item for item in result["errors"])


def test_review_json_gate_rejection_items_cover_missing_and_reasons() -> None:
    result = evaluate_review_gate({}, load_diff())

    assert result["decision"] == "blocked"
    items = result["rejection_items"]
    assert items
    item_ids = {item["item_id"] for item in items}
    for field in ["verdict", "body", "comments"]:
        assert f"missing_evidence_field:{field}" in item_ids
    assert len(items) >= len(result["missing"]) + len(result["reasons"])


def test_review_json_gate_allowed_result_has_empty_rejection_items() -> None:
    result = evaluate_review_gate(load_review("review-valid.json"), load_diff())

    assert result["decision"] == "allowed"
    assert result["rejection_items"] == []
    assert "repeat_rejection" not in result


def test_review_json_gate_allows_gate_status_unavailable() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = review["body"].replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "allowed"
    assert "gate_status: unavailable" in result["satisfied"]
    assert "gate_authorization present" in result["satisfied"]
    assert "body discloses unavailable SpecRail gate" in result["satisfied"]


def test_review_json_gate_blocks_unavailable_without_authorization() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["body"] = review["body"].replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires a non-empty gate_authorization" in item for item in result["reasons"])


def test_review_json_gate_blocks_unavailable_without_summary_disclosure() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires the ## Summary marker" in item for item in result["reasons"])


def test_review_json_gate_blocks_unavailable_marker_outside_summary() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = f"{review['body']}\n\n{UNGATED_DISCLOSURE_MARKER}"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires the ## Summary marker" in item for item in result["reasons"])


@pytest.mark.parametrize(
    "claim",
    [
        "This review is SpecRail-gated.",
        "This review is verified.",
        "This result is merge-ready.",
    ],
)
def test_review_json_gate_blocks_degraded_positive_gate_claims(claim: str) -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = review["body"].replace(
        "## Summary",
        f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}\n\n{claim}",
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("must not claim" in item for item in result["reasons"])


@pytest.mark.parametrize("gate_status", [None, "gated"])
def test_review_json_gate_blocks_unavailable_marker_without_matching_status(
    gate_status: str | None,
) -> None:
    review = load_review("review-valid.json")
    if gate_status is not None:
        review["gate_status"] = gate_status
    review["body"] = review["body"].replace(
        "## Summary", f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires gate_status unavailable" in item for item in result["reasons"])


def test_review_json_gate_blocks_unknown_gate_status() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "skipped"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "gate_status must be one of: gated, unavailable" in result["reasons"]


def test_review_json_gate_blocks_authorization_without_unavailable_status() -> None:
    review = load_review("review-valid.json")
    review["gate_authorization"] = "stale authorization"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("allowed only when gate_status is unavailable" in item for item in result["reasons"])
