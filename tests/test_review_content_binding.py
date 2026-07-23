"""Review manifest and content-binding provenance tests."""

from __future__ import annotations

import hashlib
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
    ReviewSemanticError,
    UNGATED_DISCLOSURE_MARKER,
    evaluate_review_evidence,
    load_review_manifest,
    validate_review_artifact,
)
from evidence_content_binding import build_content_binding_evidence  # noqa: E402


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
        [{
            "id": "fixture-finding",
            "severity": "important",
            "actionable": True,
            "summary": "Fixture review finding.",
        }],
    )
    if name != "review-resumed-no-checklist.json":
        review.setdefault("prior_findings", [])
    for index, finding in enumerate(review.get("prior_findings", []), start=1):
        finding.setdefault("id", f"prior-{index}")
        finding.setdefault("source_head_sha", "aaaa000000000000000000000000000000000000")
        if finding.get("status") in {"resolved", "obsolete"}:
            finding.setdefault("closure_evidence", f"review round {index} evidence")
    return review


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


def content_binding(head_sha: str = "a" * 40) -> dict[str, object]:
    return {
        "content_binding_version": 1,
        "snapshot": {
            "head_sha": head_sha,
            "base_tree_oid": "d" * 40,
            "algorithm": "sha256",
            "normalization": "specrail-v1",
            "collector": "github_pr_evidence",
        },
        "content_hashes": {
            "code_inputs": "1" * 64,
            "spec_files": "2" * 64,
            "pr_metadata": "3" * 64,
        },
    }


def bind_review(
    repo: Path, artifact: dict[str, object], categories: list[str]
) -> dict[str, object]:
    binding = content_binding(str(artifact["head_sha"]))
    sidecar = build_content_binding_evidence(489, binding)
    relative = f"artifacts/content-bindings/{sidecar['artifact_id']}.json"
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(sidecar, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    artifact.update(
        {
            "content_binding_version": 1,
            "covered_categories": categories,
            "content_bindings": {
                category: binding["content_hashes"][category]  # type: ignore[index]
                for category in categories
            },
            "content_binding_evidence": {
                "artifact_id": sidecar["artifact_id"],
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
            },
        }
    )
    return artifact


def install_review_schema(repo: Path) -> None:
    schema_dir = repo / "schemas"
    schema_dir.mkdir(exist_ok=True)
    copyfile(
        ROOT / "schemas" / "review_result.schema.json",
        schema_dir / "review_result.schema.json",
    )
    copyfile(
        ROOT / "schemas" / "content_binding_evidence.schema.json",
        schema_dir / "content_binding_evidence.schema.json",
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


def test_review_manifest_allows_previous_head_when_all_covered_bindings_match(
    tmp_path: Path,
) -> None:
    artifact = bind_review(tmp_path, clean_terminal_artifact(head_sha="b" * 40), [
        "code_inputs", "spec_files", "pr_metadata"
    ])
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
        current_binding=content_binding(),
    )

    assert result["errors"] == []
    assert result["current_artifact_ids"] == [artifact["artifact_id"]]


@pytest.mark.parametrize("changed_category", ["spec_files", "pr_metadata"])
def test_previous_head_review_invalidates_when_covered_binding_changes(
    tmp_path: Path,
    changed_category: str,
) -> None:
    install_review_schema(tmp_path)
    artifact = bind_review(tmp_path, clean_terminal_artifact(head_sha="b" * 40), [changed_category])
    binding = content_binding()
    binding["content_hashes"][changed_category] = "f" * 64  # type: ignore[index]
    result = evaluate_review_evidence(
        {
            "pr": 489,
            "head_sha": "a" * 40,
            "review_execution": "local",
            "artifacts": [artifact],
            "current_artifact_ids": [artifact["artifact_id"]],
            "errors": [],
            "blocking_reasons": [],
        },
        expected_pr=489,
        expected_head_sha="a" * 40,
        current_binding=binding,
        repo=tmp_path,
    )

    assert any("covered content bindings do not match" in item for item in result["errors"])


def test_previous_head_review_blocks_joint_embedded_binding_rewrite(tmp_path: Path) -> None:
    install_review_schema(tmp_path)
    artifact = bind_review(
        tmp_path, clean_terminal_artifact(head_sha="b" * 40), ["spec_files"]
    )
    current = content_binding()
    current["content_hashes"]["spec_files"] = "f" * 64  # type: ignore[index]
    artifact["content_bindings"]["spec_files"] = "f" * 64  # type: ignore[index]
    artifact["original_content_binding"] = content_binding("b" * 40)
    artifact["original_content_binding"]["content_hashes"]["spec_files"] = "f" * 64  # type: ignore[index]

    result = evaluate_review_evidence(
        {
            "pr": 489, "head_sha": "a" * 40, "review_execution": "local",
            "artifacts": [artifact], "current_artifact_ids": [artifact["artifact_id"]],
            "errors": [], "blocking_reasons": [],
        },
        expected_pr=489,
        expected_head_sha="a" * 40,
        current_binding=current,
        repo=tmp_path,
    )

    assert any(
        "must match its collector sidecar" in item
        for item in result["errors"]
    )


def test_review_manifest_schema_requires_sidecar_reference(tmp_path: Path) -> None:
    artifact = bind_review(
        tmp_path, clean_terminal_artifact(head_sha="b" * 40), ["code_inputs"]
    )
    artifact.pop("content_binding_evidence")
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path,
        manifest_path,
        expected_pr=489,
        expected_head_sha="a" * 40,
        current_binding=content_binding(),
    )

    assert any("content_binding_evidence" in item for item in result["errors"])


@pytest.mark.parametrize("failure", ["missing", "digest"])
def test_review_manifest_blocks_untrusted_sidecar(
    tmp_path: Path, failure: str,
) -> None:
    artifact = bind_review(
        tmp_path, clean_terminal_artifact(head_sha="b" * 40), ["code_inputs"]
    )
    reference = artifact["content_binding_evidence"]
    if failure == "missing":
        (tmp_path / reference["path"]).unlink()  # type: ignore[index]
    else:
        reference["sha256"] = "f" * 64  # type: ignore[index]
    manifest_path = write_review_manifest(tmp_path, [artifact])

    result = load_review_manifest(
        tmp_path, manifest_path, expected_pr=489, expected_head_sha="a" * 40,
        current_binding=content_binding(),
    )

    expected = "cannot read content binding evidence" if failure == "missing" else "sha256"
    assert any(expected in item for item in result["errors"])


def test_sensitive_previous_head_review_requires_code_spec_and_independent_lane(tmp_path: Path) -> None:
    install_review_schema(tmp_path)
    artifact = bind_review(tmp_path, clean_terminal_artifact(head_sha="b" * 40), ["code_inputs"])
    result = validate_review_artifact(
        artifact,
        expected_head_sha="a" * 40,
        current_binding=content_binding(),
        original_binding=content_binding("b" * 40),
        enforcement_sensitive=True,
    )

    assert any("must cover actual code_inputs and spec_files" in item for item in result["errors"])


def test_legacy_previous_head_review_remains_exact_head() -> None:
    result = validate_review_artifact(
        clean_terminal_artifact(head_sha="b" * 40),
        expected_head_sha="a" * 40,
    )

    assert "legacy review artifact head_sha must match the expected final head" in result["errors"]


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
