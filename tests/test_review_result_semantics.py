from __future__ import annotations

import json
import sys
from pathlib import Path
from shutil import copyfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from review_result_semantics import (  # noqa: E402
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
    review.setdefault("findings", [{
        "id": "fixture-finding", "severity": "important", "actionable": True,
        "summary": "Fixture review finding.",
    }])
    review.setdefault("prior_findings", [])
    for index, finding in enumerate(review["prior_findings"], start=1):
        finding.setdefault("id", f"prior-{index}")
        finding.setdefault("source_head_sha", "a" * 40)
        if finding.get("status") in {"resolved", "obsolete"}:
            finding.setdefault("closure_evidence", f"round {index} evidence")
    return review


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
    review_dir.mkdir(parents=True, exist_ok=True)
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
    assert any(
        "unavailable cannot satisfy merge-ready review evidence" in item
        for item in result["blocking_reasons"]
    )


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
        "This review is fully verified and suitable for delivery.",
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


@pytest.mark.parametrize("location", ["verdict", "comment"])
def test_review_manifest_blocks_degraded_claims_in_all_published_text(
    tmp_path: Path,
    location: str,
) -> None:
    artifact = clean_terminal_artifact()
    artifact["gate_status"] = "unavailable"
    artifact["gate_authorization"] = "Human authorization: continue without gate"
    body = artifact["body"]
    assert isinstance(body, str)
    artifact["body"] = body.replace(
        "## Summary", f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}"
    )
    if location == "verdict":
        artifact["body"] = artifact["body"].replace(
            "## Verdict", "## Verdict\n\nThis review is verified and merge-ready."
        )
    else:
        artifact["comments"] = [
            {
                "path": "checks/example.py",
                "line": 1,
                "side": "RIGHT",
                "severity": "suggestion",
                "body": "This review is verified and merge-ready.",
            }
        ]
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


def bounded_artifact(
    review_round: int, *, findings: list[dict[str, object]] | None = None,
    prior: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    artifact = clean_terminal_artifact(
        artifact_id=f"round-{review_round}", head_sha=f"{review_round:040x}"
    )
    artifact.update({
        "round_policy_version": 1,
        "review_round": review_round,
        "review_mode": "full" if review_round == 1 else "resumed",
        "findings": findings or [],
        "prior_findings": prior or [],
    })
    if review_round >= 2:
        artifact["base_head_sha"] = f"{review_round - 1:040x}"
        artifact["diff_sha256"] = f"{review_round:064x}"
    return artifact


def write_bounded_manifest(repo: Path, artifacts: list[dict[str, object]]) -> str:
    install_review_schema(repo)
    review_dir = repo / "artifacts" / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    rounds = []
    for artifact in artifacts:
        artifact_id = str(artifact["artifact_id"])
        path = review_dir / f"{artifact_id}.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        paths.append(path.relative_to(repo).as_posix())
        escalation = artifact.get("round_cap_escalation")
        rounds.append({
            "artifact_id": artifact_id,
            "review_round": artifact.get("review_round"),
            "review_mode": artifact.get("review_mode"),
            "base_head_sha": artifact.get("base_head_sha"),
            "head_sha": artifact.get("head_sha"),
            "diff_sha256": artifact.get("diff_sha256"),
            "escalation_authorization_id": (
                escalation.get("authorization_id") if isinstance(escalation, dict) else None
            ),
        })
    manifest = {
        "version": 2, "pr": 489, "head_sha": artifacts[-1]["head_sha"],
        "human_final_review_required": False,
        "round_policy": {"name": "bounded_diff_v1", "cap": 3},
        "rounds": rounds,
        "lanes": [{
            "lane_id": "reviewer-1", "producer_identity": "agent-reviewer-1",
            "artifact_paths": paths,
        }],
    }
    path = review_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path.relative_to(repo).as_posix()


def load_bounded(repo: Path, artifacts: list[dict[str, object]]) -> dict[str, object]:
    path = write_bounded_manifest(repo, artifacts)
    return load_review_manifest(
        repo, path, expected_pr=489, expected_head_sha=str(artifacts[-1]["head_sha"])
    )


def compact(source: str, finding_id: str = "F-1", status: str = "unresolved") -> dict[str, object]:
    return {
        "finding_id": finding_id, "source_artifact_id": source, "status": status,
        "evidence_pointer": {"kind": "thread", "value": "PRRT_167"},
    }


def test_v1_multi_artifact_requires_explicit_migration(tmp_path: Path) -> None:
    path = write_review_manifest(
        tmp_path, [clean_terminal_artifact(head_sha="b" * 40), clean_terminal_artifact()]
    )
    result = load_review_manifest(tmp_path, path, expected_pr=489, expected_head_sha="a" * 40)
    assert any("v1 supports one legacy artifact only" in item for item in result["errors"])


def test_v2_derives_round_audit_and_compact_carry(tmp_path: Path) -> None:
    finding = {"id": "F-1", "severity": "important", "actionable": True, "summary": "fix"}
    artifacts = [
        bounded_artifact(1, findings=[finding]),
        bounded_artifact(2, prior=[compact("round-1")]),
        bounded_artifact(3, prior=[compact("round-1", status="resolved")]),
    ]
    result = load_bounded(tmp_path, artifacts)
    assert result["errors"] == []
    assert result["round_audit"] == {
        "policy": "bounded_diff_v1", "cap": 3, "total_rounds": 3,
        "rounds": [
            {
                "artifact_id": item["artifact_id"], "review_round": item["review_round"],
                "review_mode": item["review_mode"], "base_head_sha": item.get("base_head_sha"),
                "head_sha": item["head_sha"], "diff_sha256": item.get("diff_sha256"),
                "escalation_authorization_id": None,
            } for item in artifacts
        ],
    }


def test_v2_requires_bounded_marker_on_every_artifact(tmp_path: Path) -> None:
    artifact = bounded_artifact(1)
    artifact.pop("round_policy_version")

    result = load_bounded(tmp_path, [artifact])

    assert any("round_policy_version must be 1" in item for item in result["errors"])


@pytest.mark.parametrize("rounds", [[1, 1], [1, 3], [2, 1]])
def test_v2_rejects_duplicate_gap_and_rollback(tmp_path: Path, rounds: list[int]) -> None:
    artifacts = [bounded_artifact(index + 1) for index in range(len(rounds))]
    for artifact, review_round in zip(artifacts, rounds):
        artifact["review_round"] = review_round
    result = load_bounded(tmp_path, artifacts)
    assert any("exactly 1..N" in item for item in result["errors"])


def test_v2_malformed_first_round_fails_closed_without_crashing(tmp_path: Path) -> None:
    artifacts = [bounded_artifact(1), bounded_artifact(2)]
    relative = write_bounded_manifest(tmp_path, artifacts)
    path = tmp_path / relative
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["rounds"][0] = None
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = load_review_manifest(
        tmp_path, relative, expected_pr=489, expected_head_sha=str(artifacts[-1]["head_sha"])
    )

    assert any("bounded round fields" in item for item in result["errors"])


def test_v2_rejects_full_round_two_and_missing_carry(tmp_path: Path) -> None:
    finding = {"id": "F-1", "severity": "suggestion", "actionable": False, "summary": "note"}
    second = bounded_artifact(2)
    second["review_mode"] = "full"
    second["human_full_review_request"] = "continue"
    result = load_bounded(tmp_path, [bounded_artifact(1, findings=[finding]), second])
    assert any("must be resumed or diff_only" in item for item in result["errors"])
    assert any("missing compact prior finding carry-forward" in item for item in result["errors"])


def test_v2_rejects_unknown_duplicate_and_prose_compact_findings(tmp_path: Path) -> None:
    prior = compact("missing")
    prior["summary"] = "forbidden replay"
    second = bounded_artifact(2, prior=[prior, dict(prior)])
    result = load_bounded(tmp_path, [bounded_artifact(1), second])
    joined = "\n".join(result["errors"])
    assert "prior_findings" in joined and "only" in joined
    assert "duplicate compact prior finding key" in joined
    assert "no source definition" in joined


def test_v2_round_four_requires_exact_escalation_union(tmp_path: Path) -> None:
    finding = {"id": "F-1", "severity": "suggestion", "actionable": False, "summary": "open"}
    current = {"id": "F-4", "severity": "important", "actionable": True, "summary": "new"}
    artifacts = [bounded_artifact(1, findings=[finding])]
    artifacts.extend(bounded_artifact(i, prior=[compact("round-1")]) for i in [2, 3])
    fourth = bounded_artifact(4, prior=[compact("round-1")], findings=[current])
    fourth["round_cap_escalation"] = {
        "authorization_id": "RCA-167-4",
        "unresolved_findings": [
            {"source_artifact_id": "round-1", "finding_id": "F-1"},
            {"source_artifact_id": "round-4", "finding_id": "F-4"},
        ],
    }
    artifacts.append(fourth)
    assert load_bounded(tmp_path, artifacts)["errors"] == []
    fourth["round_cap_escalation"]["unresolved_findings"].pop()
    assert any("exactly match" in item for item in load_bounded(tmp_path, artifacts)["errors"])


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
