from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from pr_gate import LEGACY_EVIDENCE_FIELDS, evaluate_pr_gate
from sensitive_enforcement import classify_sensitive_changes
from specrail_lib import PackConfig


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
    classification = classify_sensitive_changes(
        pack,
        repo,
        changed,
        changed,
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
        "gate_invocation_id": "gate-1",
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


def test_gate_honors_configured_fastlane_independent_review() -> None:
    payload, pack = evidence(profile="fastlane")
    pack.workflow["verification_profiles"] = verification_profile_config()
    pack.workflow["verification_profiles"]["profiles"]["fastlane"][
        "requires_independent_review"
    ] = True

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert any("requires an independent_lane review" in item for item in result["reasons"])


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
    assert any("unsupported legacy evidence fields:" in item for item in result["reasons"])


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


def test_gate_honors_configured_explicit_human_authorization() -> None:
    payload, pack = evidence(profile="standard")
    pack.workflow["verification_profiles"] = verification_profile_config()
    pack.workflow["verification_profiles"]["profiles"]["standard"][
        "merge_authorization"
    ] = "explicit_human"

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "needs_human"
    assert "human_merge_authorization" in result["missing"]


def test_gate_honors_configured_profile_round_cap(tmp_path: Path) -> None:
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

    result = evaluate_pr_gate(payload, repo, pack)

    assert result["decision"] == "needs_human", result["reasons"]
    assert result["review_decision"] == "needs_human"
    assert "human_review" in result["missing"]


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

    result = evaluate_pr_gate(payload, ROOT, pack)

    assert result["decision"] == "blocked"
    assert (
        "round 2 prior_review.base_head_sha must match PR evidence base_sha"
        in result["reasons"]
    )
