from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from shutil import copyfile

from pr_gate_test_support import (
    ROOT,
    clean_evidence,
    evaluate_pr_gate,
    fixture,
    sensitive_evidence,
    v1_reuse_evidence,
    write_review_evidence as _write_review_evidence,
)
from evidence_content_binding import build_content_binding_evidence
from pr_review_contract import (
    _verified_reviewer_resolver,
    evaluate_review_contract,
)
from review_result_semantics import load_review_manifest
from specrail_lib import load_pack


def _git(repo: Path, *args: str) -> bytes:
    process = subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    return process.stdout


def _round_artifact(review_round: int, head_sha: str, prior_head_sha: str | None) -> dict[str, object]:
    artifact: dict[str, object] = {
        "artifact_id": f"pr718-round-{review_round}",
        "pr": 718,
        "reviewer_lane": "merge-reviewer-2",
        "producer_identity": "reviewer-1",
        "review_source": "independent_lane",
        "review_execution": "local",
        "head_sha": head_sha,
        "review_started_at": f"2026-07-23T00:0{review_round}:00Z",
        "review_completed_at": f"2026-07-23T00:0{review_round}:30Z",
        "status": "completed",
        "verdict": "clean",
        "human_final_review_required": False,
        "findings": [],
        "prior_findings": [],
        "body": "## Summary\nBounded review.\n\n## Verdict\nclean",
        "comments": [],
        "round_policy_version": 1,
        "review_round": review_round,
        "review_mode": "full" if review_round == 1 else "resumed",
    }
    if review_round >= 2:
        artifact["base_head_sha"] = prior_head_sha
        artifact["diff_sha256"] = f"{review_round}" * 64
    if review_round > 3:
        artifact["round_cap_escalation"] = {
            "authorization_id": f"RCA-718-{review_round}",
            "unresolved_findings": [],
        }
    return artifact


def _bounded_round_evidence(tmp_path: Path) -> tuple[dict[str, object], Path]:
    repo = tmp_path / "repo"
    review_dir = repo / "artifacts" / "reviews"
    schema_dir = repo / "schemas"
    review_dir.mkdir(parents=True)
    schema_dir.mkdir()
    copyfile(
        ROOT / "schemas" / "review_result.schema.json",
        schema_dir / "review_result.schema.json",
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "SpecRail Test")
    _git(repo, "config", "user.email", "specrail@example.invalid")
    heads = []
    for review_round in range(1, 5):
        (repo / "review-target.txt").write_text(str(review_round), encoding="utf-8")
        _git(repo, "add", "--", "review-target.txt")
        _git(repo, "commit", "-m", f"review target {review_round}")
        heads.append(_git(repo, "rev-parse", "HEAD").decode().strip())
    artifacts = [
        _round_artifact(
            review_round,
            heads[review_round - 1],
            heads[review_round - 2] if review_round >= 2 else None,
        )
        for review_round in range(1, 5)
    ]
    for index, artifact in enumerate(artifacts[1:], start=1):
        exact = _git(
            repo, "diff", "--no-ext-diff", "--binary",
            f"{heads[index - 1]}..{heads[index]}", "--",
        )
        artifact["diff_sha256"] = hashlib.sha256(exact).hexdigest()
    artifact_paths: list[str] = []
    rounds: list[dict[str, object]] = []
    for artifact in artifacts:
        artifact_path = review_dir / f"{artifact['artifact_id']}.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        relative_path = artifact_path.relative_to(repo).as_posix()
        artifact_paths.append(relative_path)
        escalation = artifact.get("round_cap_escalation")
        rounds.append(
            {
                "artifact_id": artifact["artifact_id"],
                "review_round": artifact["review_round"],
                "review_mode": artifact["review_mode"],
                "base_head_sha": artifact.get("base_head_sha"),
                "head_sha": artifact["head_sha"],
                "diff_sha256": artifact.get("diff_sha256"),
                "escalation_authorization_id": (
                    escalation["authorization_id"]
                    if isinstance(escalation, dict)
                    else None
                ),
            }
        )
    manifest = {
        "version": 2,
        "pr": 718,
        "head_sha": heads[-1],
        "human_final_review_required": False,
        "round_policy": {"name": "bounded_diff_v1", "cap": 3},
        "rounds": rounds,
        "lanes": [
            {
                "lane_id": "merge-reviewer-2",
                "producer_identity": "reviewer-1",
                "artifact_paths": artifact_paths,
            }
        ],
    }
    manifest_path = review_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    trusted = load_review_manifest(
        repo,
        manifest_path.relative_to(repo).as_posix(),
        expected_pr=718,
        expected_head_sha=heads[-1],
    )
    assert trusted["errors"] == []
    evidence = clean_evidence()
    evidence["head_sha"] = heads[-1]
    evidence["gate_query_head_sha"] = heads[-1]
    evidence["review_evidence"] = trusted
    evidence["review_completed_at"] = trusted["review_completed_at"]
    evidence["gate_started_at"] = "2026-07-23T00:05:00Z"
    evidence["gate_query_completed_at"] = "2026-07-23T00:06:00Z"
    evidence["round_cap_authorizations"] = [
        {
            "authorization_id": "RCA-718-4",
            "pr": 718,
            "prior_head_sha": heads[-2],
            "target_head_sha": heads[-1],
            "review_round": 4,
            "decision": "continue_once",
            "actor": "maintainer",
            "source": "maintainer decision in GH-167",
            "authorized_at": "2026-07-23T00:03:45Z",
            "authorized_human_maintainer": True,
        }
    ]
    return evidence, repo


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


def test_pr_gate_blocks_forged_trusted_ci_coverage_reduction(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    check = evidence["checks"][0]
    check["covered_categories"] = ["code_inputs"]
    check["content_bindings"] = {
        "code_inputs": evidence["content_hashes"]["code_inputs"],
    }

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "blocked"
    assert any(
        "trusted CI coverage" in reason and "workflow-check" in reason
        for reason in result["reasons"]
    )


def test_pr_gate_blocks_v1_ci_check_without_repo_owned_mapping(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    evidence["checks"][0]["name"] = "untrusted-check"

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "blocked"
    assert any(
        "no valid trusted CI coverage mapping" in reason
        and "untrusted-check" in reason
        for reason in result["reasons"]
    )


def test_pr_gate_blocks_v1_current_component_without_head_sha(tmp_path: Path) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    del evidence["checks"][0]["head_sha"]

    result = evaluate_pr_gate(evidence, repo=tmp_path, config=load_pack(ROOT))

    assert result["decision"] == "blocked"
    assert any(
        "v1 CI check head_sha must be non-empty" in reason
        for reason in result["reasons"]
    )


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
            "resolver_role_source": "explicit_map",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed", result["reasons"]


def test_successor_resolver_accepts_validated_reusable_previous_head_review(
    tmp_path: Path,
) -> None:
    evidence = v1_reuse_evidence(tmp_path)
    review_evidence = evidence["review_evidence"]
    successor = review_evidence["artifacts"][0]
    successor.update({
        "reviewer_lane": "reviewer-successor",
        "producer_identity": "reviewer-2",
    })
    review_evidence["lane_roster"].append({
        "lane_id": "reviewer-successor",
        "producer_identity": "reviewer-2",
        "successor_of": "merge-reviewer-2",
    })
    thread = evidence["review_threads"][0]
    thread.update({
        "resolved_by": "reviewer-2",
        "resolver_role": "reviewer_lane",
        "resolver_role_source": "explicit_map",
        "original_author": "reviewer-1",
        "original_comment_id": "PRRC_fixture-root",
        "lane_id": "reviewer-successor",
        "successor_of": "merge-reviewer-2",
        "re_review_artifact_id": successor["artifact_id"],
    })

    assert successor["head_sha"] != review_evidence["head_sha"]
    assert successor["artifact_id"] in review_evidence["current_artifact_ids"]
    assert _verified_reviewer_resolver(thread, review_evidence)


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


def test_terminal_contract_allows_exact_round_four_authorization(
    tmp_path: Path,
) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)

    satisfied, missing, reasons = evaluate_review_contract(evidence, repo)

    assert missing == []
    assert reasons == []
    assert any("exact one-time maintainer authorization" in item for item in satisfied)


def test_terminal_contract_requires_external_round_cap_authorization(
    tmp_path: Path,
) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    del evidence["round_cap_authorizations"]
    evidence["human_authorization"] = {
        "actor": "maintainer",
        "source": "implx auto merge authorization",
    }
    current = evidence["review_evidence"]["artifacts"][-1]
    current["human_full_review_request"] = "maintainer requested another review"

    _, missing, reasons = evaluate_review_contract(evidence, repo)

    assert "round_cap_authorizations[RCA-718-4]" in missing
    assert any("missing round cap authorization" in reason for reason in reasons)


def test_terminal_contract_rejects_tampered_embedded_round_audit(
    tmp_path: Path,
) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    evidence["review_evidence"]["round_audit"]["total_rounds"] = 3

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert "review_evidence.round_audit differs from trusted manifest" in reasons


def test_terminal_contract_rejects_forged_manifest_diff_hash(tmp_path: Path) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    artifact_path = repo / evidence["review_evidence"]["artifacts"][1]["artifact_path"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["diff_sha256"] = "f" * 64
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    manifest_path = repo / evidence["review_evidence"]["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rounds"][1]["diff_sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence["review_evidence"] = load_review_manifest(
        repo, evidence["review_evidence"]["manifest_path"],
        expected_pr=718, expected_head_sha=evidence["head_sha"],
    )

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert any("diff_sha256 does not match exact Git" in reason for reason in reasons)


def test_terminal_contract_blocks_string_round_without_crashing(tmp_path: Path) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    artifact_path = repo / evidence["review_evidence"]["artifacts"][1]["artifact_path"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["review_round"] = "2"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    manifest_path = repo / evidence["review_evidence"]["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rounds"][1]["review_round"] = "2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence["review_evidence"] = load_review_manifest(
        repo, evidence["review_evidence"]["manifest_path"],
        expected_pr=718, expected_head_sha=evidence["head_sha"],
    )

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert any("review_round" in reason for reason in reasons)


def test_terminal_contract_requires_repo_safe_reload_for_bounded_rounds(
    tmp_path: Path,
) -> None:
    evidence, _ = _bounded_round_evidence(tmp_path)

    _, _, reasons = evaluate_review_contract(evidence)

    assert "bounded round audit requires repository-safe manifest reload" in reasons


def test_terminal_contract_rejects_duplicate_round_cap_authorization_id(
    tmp_path: Path,
) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    evidence["round_cap_authorizations"].append(
        deepcopy(evidence["round_cap_authorizations"][0])
    )

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert any("authorization_id is reused" in reason for reason in reasons)


def test_terminal_contract_rejects_unbound_round_cap_authorization(
    tmp_path: Path,
) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    unused = deepcopy(evidence["round_cap_authorizations"][0])
    unused["authorization_id"] = "RCA-718-5"
    unused["review_round"] = 5
    evidence["round_cap_authorizations"].append(unused)

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert any("not bound to an over-cap manifest round" in reason for reason in reasons)


def test_terminal_contract_rejects_authorization_rebound_to_other_scope(
    tmp_path: Path,
) -> None:
    mutations = [
        ("pr", 719),
        ("prior_head_sha", "e" * 40),
        ("target_head_sha", "f" * 40),
        ("review_round", 5),
        ("decision", "merge"),
        ("authorized_human_maintainer", False),
    ]
    for field, value in mutations:
        evidence, repo = _bounded_round_evidence(tmp_path / field)
        evidence["round_cap_authorizations"][0][field] = value

        _, _, reasons = evaluate_review_contract(evidence, repo)

        assert any(
            f"RCA-718-4.{field} must equal trusted round binding" in reason
            for reason in reasons
        ), (field, reasons)


def test_terminal_contract_rejects_authorization_unknown_fields_and_bad_time(
    tmp_path: Path,
) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    authorization = evidence["round_cap_authorizations"][0]
    authorization["authorized_at"] = "2026-07-23T00:03:45"
    authorization["scope_alias"] = "all future rounds"

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert any("contains unsupported fields: scope_alias" in reason for reason in reasons)
    assert any("authorized_at must be a timezone-aware" in reason for reason in reasons)


def test_terminal_contract_rejects_authorization_after_review_start(tmp_path: Path) -> None:
    evidence, repo = _bounded_round_evidence(tmp_path)
    evidence["round_cap_authorizations"][0]["authorized_at"] = "2026-07-23T00:04:01Z"

    _, _, reasons = evaluate_review_contract(evidence, repo)

    assert any("must precede target review start" in reason for reason in reasons)
