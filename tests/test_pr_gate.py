from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from pr_gate import LEGACY_EVIDENCE_FIELDS, evaluate_pr_gate
from rejection_items import (
    canonical_hosted_snapshot_sha256,
    canonical_review_sha256,
)
from sensitive_enforcement import classify_sensitive_changes
from specrail_lib import PackConfig, spec_packet_artifact_paths


def head_sha(repo: Path = ROOT) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def config(repo: Path, patterns: list[str] | None = None) -> PackConfig:
    return PackConfig(
        repo=repo,
        workflow={
            "artifacts": {
                "spec_packet": "specs/GH{issue_number}/",
                "product_spec": "specs/GH{issue_number}/product.md",
                "tech_spec": "specs/GH{issue_number}/tech.md",
                "task_plan": "specs/GH{issue_number}/tasks.md",
            },
            "enforcement": {
                "sensitive_registry": {"paths": patterns or [], "specs": []}
            }
        },
        states={},
        labels={},
    )


def verification_profile_config() -> dict[str, object]:
    return {
        "default": "standard",
        "profiles": {
            "fastlane": {
                "requires_spec_packet": False,
                "requires_independent_review": False,
                "max_review_rounds": 1,
                "merge_authorization": "invocation",
            },
            "standard": {
                "requires_spec_packet": False,
                "requires_independent_review": True,
                "max_review_rounds": 2,
                "merge_authorization": "invocation",
            },
            "heavy": {
                "requires_spec_packet": True,
                "requires_independent_review": True,
                "max_review_rounds": 2,
                "merge_authorization": "explicit_human",
            },
        },
    }


def evidence(
    *,
    repo: Path = ROOT,
    profile: str = "standard",
    paths: list[str] | None = None,
    patterns: list[str] | None = None,
) -> tuple[dict[str, object], PackConfig]:
    head = head_sha(repo)
    changed = sorted(paths or ["src/app.py"])
    pack = config(repo, patterns)
    packet = spec_packet_artifact_paths(pack, 208)
    spec_refs = (
        [
            packet[name]
            for name in ("product_spec", "tech_spec", "task_plan")
        ]
        if pack.workflow["enforcement"]["sensitive_registry"]["specs"]
        else []
    )
    classification = classify_sensitive_changes(
        pack,
        repo,
        changed,
        spec_refs,
        source="github_changed_files",
    )
    review_source = "self_review" if profile == "fastlane" else "independent_lane"
    review = {
        "artifact_id": "review-42",
        "contract_version": 3,
        "repository": "acme/widgets",
        "pr": 42,
        "profile": profile,
        "base_head_sha": head,
        "head_sha": head,
        "diff_sha256": hashlib.sha256(b"").hexdigest(),
        "review_source": review_source,
        "round": 1,
        "mode": "full",
        "verdict": "clean",
        "body": "## Summary\nComplete review.\n\n## Verdict\nClean.",
        "findings": [],
    }
    payload: dict[str, object] = {
        "contract_version": 3,
        "repository": "acme/widgets",
        "pr": 42,
        "linked_issue": 208,
        "state": "OPEN",
        "is_draft": False,
        "base_sha": head,
        "head_sha": head,
        "gate_query_head_sha": head,
        "changed_files": changed,
        "changed_files_count": len(changed),
        "changed_files_sha256": hashlib.sha256(
            json.dumps(changed, separators=(",", ":")).encode()
        ).hexdigest(),
        "checks": [
            {
                "name": "tests",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "head_sha": head,
            }
        ],
        "merge_state": "CLEAN",
        "profile": profile,
        "enforcement_sensitive": classification["enforcement_sensitive"],
        "sensitive_classification": classification,
        "review": review,
        "hosted_findings": [],
        "prior_review_boundary": None,
        "gate_invocation_id": "gate-1",
    }
    if profile != "fastlane":
        payload["review_attestation"] = {
            "artifact_id": review["artifact_id"],
            "lane_id": "review-lane-1",
            "reviewer_actor": "reviewer-agent-1",
            "review_sha256": canonical_review_sha256(review),
            "hosted_snapshot_sha256": canonical_hosted_snapshot_sha256(
                head,
                "gate-1",
                [],
                None,
            ),
            "head_sha": head,
            "invocation_id": "gate-1",
        }
    return payload, pack


def test_standard_current_evidence_is_allowed() -> None:
    payload, pack = evidence()

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]
    assert result["advisory_only"] is True
    assert result["unsupported_legacy_evidence"] == []


def test_fastlane_self_review_is_allowed() -> None:
    payload, pack = evidence(profile="fastlane")

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]


def test_fastlane_rejects_explicit_null_attestation() -> None:
    payload, pack = evidence(profile="fastlane")
    payload["review_attestation"] = None

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "fastlane must not include review_attestation" in result["reasons"]


def test_nonsensitive_gate_blocks_stale_local_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=SpecRail Test",
            "-c",
            "user.email=specrail@example.invalid",
            "commit",
            "-qm",
            "local",
        ],
        cwd=repo,
        check=True,
    )
    payload, _pack = evidence()
    pack = config(repo)

    result = evaluate_pr_gate(payload, repo, pack)

    assert result["decision"] == "blocked"
    assert "PR gate requires an exact current-head checkout" in result["reasons"]


def checks_unavailable() -> dict[str, object]:
    return {
        "reason": "hosted_ci_not_triggered_for_base",
        "base_ref": "feature-base",
        "default_base_ref": "main",
        "workflow_trigger_evidence": "pull_request.branches only contains main",
        "local_verification": ["python3 -m pytest -q"],
        "verified": True,
    }


def test_empty_checks_accepts_closed_trusted_unavailable_declaration() -> None:
    payload, pack = evidence()
    payload["checks"] = []
    payload["base_ref"] = "feature-base"
    payload["default_base_ref"] = "main"
    payload["checks_unavailable"] = checks_unavailable()

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "allowed", result["reasons"]
    assert any(item.startswith("degraded:") for item in result["satisfied"])


def test_empty_checks_without_declaration_remains_missing() -> None:
    payload, pack = evidence()
    payload["checks"] = []

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "checks" in result["missing"]


def test_checks_unavailable_binds_closed_top_level_base_refs() -> None:
    mutations = [
        ("base_ref", None, "base_ref"),
        ("default_base_ref", None, "default_base_ref"),
        ("base_ref", " ", "base_ref"),
        ("default_base_ref", " ", "default_base_ref"),
        ("base_ref", "other", "must match base_ref"),
        ("default_base_ref", "trunk", "must match default_base_ref"),
    ]
    for field, value, expected in mutations:
        payload, pack = evidence()
        payload["checks"] = []
        payload["base_ref"] = "feature-base"
        payload["default_base_ref"] = "main"
        payload["checks_unavailable"] = checks_unavailable()
        if value is None:
            payload.pop(field)
        else:
            payload[field] = value

        result = evaluate_pr_gate(payload, ROOT, pack)

        assert result["decision"] == "blocked"
        assert expected in " ".join([*result["missing"], *result["reasons"]])


def test_available_checks_conflict_with_unavailable_declaration() -> None:
    payload, pack = evidence()
    payload["checks_unavailable"] = checks_unavailable()

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert (
        "checks_unavailable must not be present when checks are available"
        in result["reasons"]
    )


def test_available_checks_reject_explicit_null_unavailable_declaration() -> None:
    payload, pack = evidence()
    payload["checks_unavailable"] = None

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert (
        "checks_unavailable must not be present when checks are available"
        in result["reasons"]
    )


def test_round_one_uses_pr_merge_base_diff_when_base_has_diverged(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "shared.py").write_text("base = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid",
            "commit", "-qm", "base",
        ],
        cwd=repo,
        check=True,
    )
    base = head_sha(repo)
    base_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-qb", "feature"], cwd=repo, check=True)
    (repo / "feature.py").write_text("feature = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid",
            "commit", "-qm", "feature",
        ],
        cwd=repo,
        check=True,
    )
    feature_head = head_sha(repo)
    subprocess.run(["git", "checkout", "-q", base_branch], cwd=repo, check=True)
    (repo / "base-only.py").write_text("base_only = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid",
            "commit", "-qm", "advance base",
        ],
        cwd=repo,
        check=True,
    )
    base_tip = head_sha(repo)
    subprocess.run(["git", "checkout", "-q", "feature"], cwd=repo, check=True)

    payload, pack = evidence(repo=repo, paths=["feature.py"])
    payload["base_sha"] = base_tip
    payload["review"]["base_head_sha"] = base_tip
    payload["review"]["head_sha"] = feature_head
    exact_pr_diff = subprocess.run(
        [
            "git", "diff", "--no-ext-diff", "--binary",
            f"{base_tip}...{feature_head}", "--",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    two_dot_diff = subprocess.run(
        [
            "git", "diff", "--no-ext-diff", "--binary",
            f"{base_tip}..{feature_head}", "--",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    assert exact_pr_diff != two_dot_diff
    payload["review"]["diff_sha256"] = hashlib.sha256(exact_pr_diff).hexdigest()
    payload["review_attestation"]["review_sha256"] = canonical_review_sha256(
        payload["review"]
    )

    result = evaluate_pr_gate(payload, repo, pack)

    assert result["decision"] == "allowed", result["reasons"]


def test_sensitive_spec_registry_uses_linked_issue_packet_refs() -> None:
    payload, pack = evidence(profile="heavy")
    pack.workflow["enforcement"]["sensitive_registry"]["specs"] = [
        "specs/GH208/**"
    ]
    packet = spec_packet_artifact_paths(pack, 208)
    classification = classify_sensitive_changes(
        pack,
        ROOT,
        payload["changed_files"],
        [
            packet[name]
            for name in ("product_spec", "tech_spec", "task_plan")
        ],
        source="github_changed_files",
    )
    payload["enforcement_sensitive"] = True
    payload["sensitive_classification"] = classification

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human", result["reasons"]
    assert result["sensitive_classification"]["matched_specs"] == [
        "specs/GH208/product.md",
        "specs/GH208/tasks.md",
        "specs/GH208/tech.md",
    ]


def test_gate_rejects_noncanonical_fastlane_independent_review() -> None:
    payload, pack = evidence(profile="fastlane")
    pack.workflow["verification_profiles"] = verification_profile_config()
    pack.workflow["verification_profiles"]["profiles"]["fastlane"][
        "requires_independent_review"
    ] = True

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "workflow.yaml: fastlane profile must match canonical safety policy" in result["reasons"]


def test_gate_requires_every_configured_ci_check() -> None:
    payload, pack = evidence()
    pack.workflow["evidence"] = {
        "ci_component_coverage": {
            "tests": ["unit"],
            "workflow-check": ["contract"],
        }
    }

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "configured CI checks are missing: workflow-check" in result["reasons"]


def test_gate_aggregates_all_legacy_fields() -> None:
    payload, pack = evidence()
    for field in LEGACY_EVIDENCE_FIELDS:
        payload[field] = "legacy"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert result["unsupported_legacy_evidence"] == sorted(LEGACY_EVIDENCE_FIELDS)
    assert len(result["reasons"]) == 1
    assert result["reasons"][0].startswith("unsupported legacy evidence fields:")
    assert "rebuild evidence from GitHub PR current state" in result["reasons"][0]
    assert result["missing"] == []
    assert len(result["rejection_items"]) == 1


def test_gate_rejects_invalid_repository_even_when_review_matches() -> None:
    payload, pack = evidence()
    payload["repository"] = "not-a-repository"
    payload["review"]["repository"] = "not-a-repository"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "GitHub repository must use OWNER/REPO format" in result["reasons"]


def test_gate_blocks_stale_head_ci_and_review_together() -> None:
    payload, pack = evidence()
    payload["gate_query_head_sha"] = "c" * 40
    payload["checks"][0]["head_sha"] = "d" * 40
    payload["review"]["head_sha"] = "e" * 40

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert any("gate_query_head_sha" in item for item in result["reasons"])
    assert any("check #1 head_sha" in item for item in result["reasons"])
    assert any("review.head_sha" in item for item in result["reasons"])


def test_gate_blocks_failed_ci_draft_and_dirty_merge_state() -> None:
    payload, pack = evidence()
    payload["is_draft"] = True
    payload["merge_state"] = "DIRTY"
    payload["checks"][0]["conclusion"] = "FAILURE"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "draft PR cannot merge" in result["reasons"]
    assert any("merge_state must be CLEAN" in item for item in result["reasons"])
    assert any("conclusion is not successful" in item for item in result["reasons"])


def test_gate_blocks_current_p0_and_exposes_identifier() -> None:
    payload, pack = evidence()
    payload["review"]["verdict"] = "blocking"
    payload["review"]["findings"] = [
        {
            "id": "P0-auth-bypass",
            "severity": "P0",
            "status": "unresolved",
            "summary": "Authentication can be bypassed.",
        }
    ]

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert any("P0-auth-bypass" in item for item in result["reasons"])


def test_gate_reports_all_missing_contract_fields() -> None:
    result = evaluate_pr_gate({})

    assert result["decision"] == "blocked"
    assert {"pr", "linked_issue", "checks", "review", "profile"} <= set(result["missing"])
    assert result["rejection_items"]


def test_gate_rejects_noncanonical_standard_merge_authorization() -> None:
    payload, pack = evidence(profile="standard")
    pack.workflow["verification_profiles"] = verification_profile_config()
    pack.workflow["verification_profiles"]["profiles"]["standard"][
        "merge_authorization"
    ] = "explicit_human"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "workflow.yaml: standard profile must match canonical safety policy" in result["reasons"]


def test_gate_rejects_noncanonical_profile_round_cap(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "app.py").write_text("before = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=SpecRail Test",
            "-c",
            "user.email=specrail@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=repo,
        check=True,
    )
    base = head_sha(repo)
    (repo / "app.py").write_text("after = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=SpecRail Test",
            "-c",
            "user.email=specrail@example.invalid",
            "commit",
            "-qm",
            "head",
        ],
        cwd=repo,
        check=True,
    )
    payload, pack = evidence(repo=repo, profile="standard")
    payload["base_sha"] = base
    pack.workflow["verification_profiles"] = verification_profile_config()
    pack.workflow["verification_profiles"]["profiles"]["standard"][
        "max_review_rounds"
    ] = 1
    payload["review"]["round"] = 2
    payload["review"]["mode"] = "diff_only"
    payload["review"]["base_head_sha"] = base
    exact_diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary", f"{base}..HEAD", "--"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    payload["review"]["diff_sha256"] = hashlib.sha256(exact_diff).hexdigest()
    payload["review"]["prior_review"] = {
        **payload["review"],
        "artifact_id": "review-42-round1",
        "head_sha": base,
        "round": 1,
        "mode": "full",
        "base_head_sha": base,
        "diff_sha256": hashlib.sha256(b"").hexdigest(),
    }
    for field in ["prior_review"]:
        payload["review"]["prior_review"].pop(field, None)
    payload["review_attestation"].update({
        "prior_artifact_id": "review-42-round1",
        "prior_head_sha": base,
    })

    result = evaluate_pr_gate(payload, repo, pack)

    assert result["decision"] == "blocked", result["reasons"]
    assert "workflow.yaml: standard profile must match canonical safety policy" in result["reasons"]


def test_round_two_prior_review_must_start_at_pr_base() -> None:
    payload, pack = evidence()
    pr_base = subprocess.run(
        ["git", "rev-parse", "HEAD~3"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    truncated_base = subprocess.run(
        ["git", "rev-parse", "HEAD~2"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prior_head = subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    current_head = head_sha()
    prior_diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary",
         f"{truncated_base}..{prior_head}", "--"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    current_diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary",
         f"{prior_head}..{current_head}", "--"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    prior_review = {
        **payload["review"],
        "artifact_id": "review-42-round1",
        "base_head_sha": truncated_base,
        "head_sha": prior_head,
        "diff_sha256": hashlib.sha256(prior_diff).hexdigest(),
    }
    payload["base_sha"] = pr_base
    payload["review"].update(
        {
            "round": 2,
            "mode": "diff_only",
            "base_head_sha": prior_head,
            "head_sha": current_head,
            "diff_sha256": hashlib.sha256(current_diff).hexdigest(),
            "prior_review": prior_review,
        }
    )
    payload["review_attestation"].update({
        "prior_artifact_id": "review-42-round1",
        "prior_head_sha": prior_head,
    })

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert (
        "round 2 prior_review.base_head_sha must match PR evidence base_sha"
        in result["reasons"]
    )


def test_pr_gate_blocks_non_array_prior_findings_without_crashing() -> None:
    payload, pack = evidence()
    review = payload["review"]
    prior = {
        **review,
        "artifact_id": "review-42-round1",
        "findings": None,
    }
    review.update(
        {
            "round": 2,
            "mode": "diff_only",
            "prior_review": prior,
        }
    )
    payload["review_attestation"].update(
        {
            "prior_artifact_id": prior["artifact_id"],
            "prior_head_sha": prior["head_sha"],
            "review_sha256": canonical_review_sha256(review),
        }
    )

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert "review: prior_review: findings must be an array" in result["reasons"]
