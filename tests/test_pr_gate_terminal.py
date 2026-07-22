from __future__ import annotations

import hashlib
import json
from pathlib import Path
from shutil import copyfile

from pr_gate_test_support import (
    ROOT,
    clean_evidence,
    evaluate_pr_gate,
    fixture,
    sensitive_evidence,
)
from evidence_content_binding import build_content_binding_evidence
from review_result_semantics import load_review_manifest
from specrail_lib import load_pack


def _write_review_evidence(
    repo: Path, evidence: dict[str, object], artifacts: list[dict[str, object]],
) -> None:
    schema_dir = repo / "schemas"
    schema_dir.mkdir(exist_ok=True)
    for name in ["review_result.schema.json", "content_binding_evidence.schema.json"]:
        copyfile(ROOT / "schemas" / name, schema_dir / name)
    review_dir = repo / "artifacts/reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, artifact in enumerate(artifacts, start=1):
        path = review_dir / f"review-{index}.json"
        stored = {key: value for key, value in artifact.items() if key != "artifact_path"}
        path.write_text(json.dumps(stored), encoding="utf-8")
        paths.append(path.relative_to(repo).as_posix())
    manifest = {
        "version": 1, "pr": evidence["pr"], "head_sha": evidence["head_sha"],
        "human_final_review_required": False,
        "lanes": [{
            "lane_id": artifacts[0]["reviewer_lane"],
            "producer_identity": artifacts[0]["producer_identity"],
            "artifact_paths": paths,
        }],
    }
    manifest_path = review_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence["review_evidence"] = load_review_manifest(
        repo, manifest_path.relative_to(repo).as_posix(),
        expected_pr=evidence["pr"], expected_head_sha=evidence["head_sha"],
        current_binding={key: evidence[key] for key in [
            "content_binding_version", "snapshot", "content_hashes"
        ]},
    )


def v1_reuse_evidence(
    repo: Path, evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    evidence = clean_evidence() if evidence is None else evidence
    current_head = evidence["head_sha"]
    prior_head = "b" * 40
    hashes = {
        "code_inputs": "1" * 64,
        "spec_files": "2" * 64,
        "pr_metadata": "3" * 64,
    }
    snapshot = {
        "head_sha": current_head,
        "base_tree_oid": "d" * 40,
        "algorithm": "sha256",
        "normalization": "specrail-v1",
        "collector": "github_pr_evidence",
    }
    evidence.update({
        "content_binding_version": 1,
        "snapshot": snapshot,
        "content_hashes": hashes,
    })
    check = evidence["checks"][0]
    check.update({
        "artifact_id": "ci-current",
        "head_sha": current_head,
        "content_binding_version": 1,
        "covered_categories": ["code_inputs", "spec_files"],
        "content_bindings": {key: hashes[key] for key in ["code_inputs", "spec_files"]},
    })
    artifact = evidence["review_evidence"]["artifacts"][0]
    artifact.update({
        "head_sha": prior_head,
        "content_binding_version": 1,
        "covered_categories": ["code_inputs", "spec_files"],
        "content_bindings": {key: hashes[key] for key in ["code_inputs", "spec_files"]},
    })
    sidecar = build_content_binding_evidence(evidence["pr"], {
        "content_binding_version": 1,
        "snapshot": {**snapshot, "head_sha": prior_head},
        "content_hashes": dict(hashes),
    })
    sidecar_path = repo / "artifacts/content-bindings/prior-review.json"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(sidecar, sort_keys=True).encode("utf-8")
    sidecar_path.write_bytes(raw)
    artifact["content_binding_evidence"] = {
        "artifact_id": sidecar["artifact_id"],
        "path": sidecar_path.relative_to(repo).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    evidence["reused_components"] = [{
        "artifact_id": artifact["artifact_id"],
        "original_head_sha": prior_head,
        "covered_categories": ["code_inputs", "spec_files"],
        "original_content_bindings": dict(artifact["content_bindings"]),
        "current_content_bindings": {key: hashes[key] for key in ["code_inputs", "spec_files"]},
        "collector_provenance": snapshot,
        "reason": "all covered categories match the current snapshot",
    }]
    _write_review_evidence(repo, evidence, [artifact])
    return evidence


def test_pr_gate_blocks_missing_review_source() -> None:
    evidence = clean_evidence()
    del evidence["review_source"]
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review_source" in result["missing"]


def test_pr_gate_blocks_self_review_source() -> None:
    evidence = fixture("pr-self-review-source.json")
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("self_review" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unknown_review_source() -> None:
    evidence = clean_evidence()
    evidence["review_source"] = "coordinator_summary"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("review_source must be one of" in reason for reason in result["reasons"])


def test_pr_gate_blocks_missing_primary_review_execution() -> None:
    evidence = clean_evidence()
    del evidence["review_execution"]

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review_execution" in result["missing"]


def test_pr_gate_blocks_hosted_review_as_primary() -> None:
    evidence = clean_evidence()
    evidence["review_execution"] = "hosted"
    evidence["review_evidence"]["review_execution"] = "hosted"
    evidence["review_evidence"]["artifacts"][0]["review_execution"] = "hosted"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("supplemental only" in reason for reason in result["reasons"])


def test_pr_gate_allows_confirmed_merge_record() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-confirmed.json"))

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_allows_confirmed_api_fallback_merge() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-api-fallback-confirmed.json"))

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_unconfirmed_merge_record() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-unconfirmed-local-failure.json"))

    assert result["decision"] == "blocked"
    assert any("remote_confirmed" in reason for reason in result["reasons"])


def test_pr_gate_blocks_merge_record_missing_path() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-missing-path.json"))

    assert result["decision"] == "blocked"
    assert "merge_record.merge_path" in result["missing"]


def test_pr_gate_allows_merged_by_other_terminal() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_record"]["merge_path"] = "merged_by_other"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_review_source_without_terminal_manifest_evidence() -> None:
    evidence = clean_evidence()
    evidence.pop("review_evidence")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("review_source alone" in reason for reason in result["reasons"])


def test_pr_gate_allows_current_wrapper_with_coverage_matched_prior_review(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "allowed", result["reasons"]
    assert result["head_sha"] == evidence["head_sha"]
    assert result["reused_components"] == evidence["reused_components"]


def test_pr_gate_allows_sensitive_previous_head_review_sidecar(tmp_path: Path) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    evidence = v1_reuse_evidence(repo, evidence)

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "allowed", result["reasons"]
    assert result["enforcement_sensitive"] is True
    assert "terminal review evidence has no blocking findings" in result["satisfied"]


def test_pr_gate_blocks_prior_review_when_spec_binding_changes(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    evidence["content_hashes"]["spec_files"] = "f" * 64

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "blocked"
    assert any("covered content bindings do not match" in reason for reason in result["reasons"])


def test_pr_gate_blocks_missing_or_incomplete_reuse_audit(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    del evidence["reused_components"][0]["collector_provenance"]

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "blocked"
    assert any("collector_provenance is invalid" in reason for reason in result["reasons"])


def test_pr_gate_rejects_old_gate_decision_as_reusable_component(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    evidence["reused_components"].append({
        **evidence["reused_components"][0],
        "artifact_id": "old-pr-gate-decision",
    })

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "blocked"
    assert any("unknown artifacts: old-pr-gate-decision" in reason for reason in result["reasons"])


def test_pr_gate_ignores_unselected_historical_review_component(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    historical = dict(evidence["review_evidence"]["artifacts"][0])
    historical.update({
        "artifact_id": "historical-review",
        "head_sha": "c" * 40,
        "content_bindings": {
            "code_inputs": "f" * 64,
            "spec_files": "f" * 64,
        },
    })
    sidecar = build_content_binding_evidence(evidence["pr"], {
        "content_binding_version": 1,
        "snapshot": {**evidence["snapshot"], "head_sha": "c" * 40},
        "content_hashes": {
            **evidence["content_hashes"],
            "code_inputs": "f" * 64,
            "spec_files": "f" * 64,
        },
    }, artifact_id="historical-sidecar")
    sidecar_path = tmp_path / "artifacts/content-bindings/historical.json"
    raw = json.dumps(sidecar, sort_keys=True).encode("utf-8")
    sidecar_path.write_bytes(raw)
    historical["content_binding_evidence"] = {
        "artifact_id": sidecar["artifact_id"],
        "path": sidecar_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    _write_review_evidence(
        tmp_path, evidence,
        [evidence["review_evidence"]["artifacts"][0], historical],
    )

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_review_completed_after_gate_started() -> None:
    evidence = clean_evidence()
    evidence["review_completed_at"] = "2026-07-04T00:00:01Z"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review must complete at or before gate start" in result["reasons"]


def test_pr_gate_blocks_gate_started_after_query_completed() -> None:
    evidence = clean_evidence()
    evidence["gate_started_at"] = "2026-07-04T00:00:01Z"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate_started_at must be at or before gate_query_completed_at" in result["reasons"]


def test_pr_gate_rejects_noncanonical_gate_completed_alias() -> None:
    evidence = clean_evidence()
    evidence["gate_completed_at"] = evidence["gate_query_completed_at"]

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("alias is unsupported" in reason for reason in result["reasons"])


def test_pr_gate_blocks_current_head_actionable_artifact_finding() -> None:
    evidence = clean_evidence()
    artifact = evidence["review_evidence"]["artifacts"][0]
    artifact["verdict"] = "blocking"
    artifact["findings"] = [
        {
            "id": "finding-current",
            "severity": "important",
            "actionable": True,
            "summary": "Current blocking finding.",
        }
    ]

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("blocking current-head finding" in reason for reason in result["reasons"])


def test_pr_gate_allows_successor_resolver_with_current_head_rereview() -> None:
    evidence = clean_evidence()
    original = evidence["review_evidence"]["artifacts"][0]
    successor = dict(original)
    successor.update(
        {
            "artifact_id": "pr718-head1-successor",
            "reviewer_lane": "reviewer-successor",
            "producer_identity": "reviewer-2",
        }
    )
    evidence["review_evidence"]["artifacts"].append(successor)
    evidence["review_evidence"]["current_artifact_ids"].append(
        "pr718-head1-successor"
    )
    evidence["review_evidence"]["lane_roster"].append(
        {
            "lane_id": "reviewer-successor",
            "producer_identity": "reviewer-2",
            "successor_of": "merge-reviewer-2",
        }
    )
    thread = evidence["review_threads"][0]
    thread.update(
        {
            "resolved_by": "reviewer-2",
            "resolver_role": "reviewer_lane",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_successor_with_mismatched_trusted_lineage() -> None:
    evidence = clean_evidence()
    original = evidence["review_evidence"]["artifacts"][0]
    successor = dict(original)
    successor.update(
        {
            "artifact_id": "pr718-head1-successor",
            "reviewer_lane": "reviewer-successor",
            "producer_identity": "reviewer-2",
        }
    )
    evidence["review_evidence"]["artifacts"].append(successor)
    evidence["review_evidence"]["current_artifact_ids"].append(
        "pr718-head1-successor"
    )
    evidence["review_evidence"]["lane_roster"].append(
        {
            "lane_id": "reviewer-successor",
            "producer_identity": "reviewer-2",
            "successor_of": "unrelated-reviewer",
        }
    )
    evidence["review_threads"][0].update(
        {
            "resolved_by": "reviewer-2",
            "resolver_role": "reviewer_lane",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("lacks original/successor re-review evidence" in reason for reason in result["reasons"])


def test_pr_gate_blocks_successor_when_original_reviewer_lane_is_ambiguous() -> None:
    evidence = clean_evidence()
    original = evidence["review_evidence"]["artifacts"][0]
    successor = dict(original)
    successor.update(
        {
            "artifact_id": "pr718-head1-successor",
            "reviewer_lane": "reviewer-successor",
            "producer_identity": "reviewer-2",
        }
    )
    evidence["review_evidence"]["artifacts"].append(successor)
    evidence["review_evidence"]["current_artifact_ids"].append(
        "pr718-head1-successor"
    )
    evidence["review_evidence"]["lane_roster"].extend(
        [
            {
                "lane_id": "duplicate-original",
                "producer_identity": "reviewer-1",
            },
            {
                "lane_id": "reviewer-successor",
                "producer_identity": "reviewer-2",
                "successor_of": "merge-reviewer-2",
            },
        ]
    )
    evidence["review_threads"][0].update(
        {
            "resolved_by": "reviewer-2",
            "resolver_role": "reviewer_lane",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("lacks original/successor re-review evidence" in reason for reason in result["reasons"])


def test_pr_gate_blocks_confirmed_merge_without_commit_sha() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_record"]["merge_commit_sha"] = None
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "merge_record.merge_commit_sha" in result["missing"]


def test_pr_gate_blocks_unknown_merge_path() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_record"]["merge_path"] = "force_push"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("merge_path must be one of" in reason for reason in result["reasons"])


def test_pr_gate_blocks_naive_merge_dispatch_timestamp() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_dispatched_at"] = "2026-07-04T07:01:00"
    evidence["merge_head_sha"] = evidence["gate_query_head_sha"]
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("timezone-aware" in reason for reason in result["reasons"])
