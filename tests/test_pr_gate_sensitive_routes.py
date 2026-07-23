from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from pr_gate_test_support import evaluate_pr_gate, sensitive_evidence
from sensitive_enforcement import classify_sensitive_changes
from spec_revision_evidence import spec_artifacts_sha256
from specrail_lib import PackConfig


SPEC_APPROVAL_FIELDS = {
    "lifecycle_state",
    "state_source",
    "state_trusted",
    "maintainer_actor",
    "approved_at",
    "approval_source",
    "approval_url",
    "commit_oid",
    "artifact_paths",
    "spec_artifacts_sha256",
}


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _run(repo, "add", ".")
    _run(
        repo,
        "-c",
        "user.name=SpecRail Test",
        "-c",
        "user.email=specrail@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return _run(repo, "rev-parse", "HEAD")


def _bind_terminal_review(evidence: dict[str, object], repo: Path, head: str) -> None:
    review = evidence["review_evidence"]
    assert isinstance(review, dict)
    review["head_sha"] = head
    artifacts = review["artifacts"]
    assert isinstance(artifacts, list) and len(artifacts) == 1
    artifact = artifacts[0]
    assert isinstance(artifact, dict)
    artifact["head_sha"] = head

    manifest_path = repo / str(review["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["head_sha"] = head
    artifact_path = repo / manifest["lanes"][0]["artifact_paths"][0]
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    review["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()


@pytest.fixture
def spec_revision_evidence(
    tmp_path: Path,
) -> tuple[dict[str, object], Path, object]:
    evidence, repo, config = sensitive_evidence(tmp_path)
    workflow = deepcopy(config.workflow)
    workflow["enforcement"]["sensitive_registry"] = {
        "paths": ["checks/**"],
        "specs": ["specs/GH*/**"],
    }
    config = PackConfig(repo, workflow, config.states, config.labels)
    base = _run(repo, "rev-parse", "HEAD")
    _run(repo, "update-ref", "refs/remotes/origin/main", base)
    product_path = "specs/GH97/product.md"
    (repo / product_path).write_text("# revised product\n", encoding="utf-8")
    head = _commit(repo, "revise spec")
    changed_paths = [product_path]
    classification = classify_sensitive_changes(
        config,
        repo,
        changed_paths,
        changed_paths,
        source="github_changed_files",
    )
    approval = {
        "lifecycle_state": "spec_approved",
        "state_source": "label",
        "state_trusted": True,
        "maintainer_actor": "maintainer",
        "approved_at": "2030-07-23T08:00:00+08:00",
        "approval_source": "github_pr_review",
        "approval_url": (
            "https://github.com/majiayu000/specrail/"
            "pull/718#pullrequestreview-1"
        ),
        "commit_oid": head,
        "artifact_paths": changed_paths,
        "spec_artifacts_sha256": spec_artifacts_sha256(repo, head, changed_paths),
    }
    evidence.update(
        {
            "base_sha": base,
            "default_base_sha": base,
            "head_sha": head,
            "gate_query_head_sha": head,
            "changed_files_count": 1,
            "changed_files_sha256": hashlib.sha256(
                json.dumps(changed_paths, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "sensitive_classification": {
                "source": "github_changed_files",
                "changed_paths": changed_paths,
                "spec_refs": classification["spec_refs"],
            },
            "sensitive_route": "spec_revision",
            "spec_approval": approval,
        }
    )
    evidence.pop("approved_spec")
    _bind_terminal_review(evidence, repo, head)
    return evidence, repo, config


def test_pr_gate_emits_exact_spec_revision_route_audit(
    spec_revision_evidence: tuple[dict[str, object], Path, object],
) -> None:
    evidence, repo, config = spec_revision_evidence

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "allowed", result
    approval = evidence["spec_approval"]
    assert isinstance(approval, dict)
    assert result["sensitive_route_audit"] == {
        "sensitive_route": "spec_revision",
        "linked_issue": evidence["linked_issue"],
        "artifact_paths": approval["artifact_paths"],
        "maintainer_actor": approval["maintainer_actor"],
        "approved_at": approval["approved_at"],
        "approval_source": approval["approval_source"],
        "approval_url": approval["approval_url"],
        "commit_oid": approval["commit_oid"],
        "spec_artifacts_sha256": approval["spec_artifacts_sha256"],
    }


def test_pr_gate_emits_distinct_approved_spec_route_audit(tmp_path: Path) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    approved = evidence["approved_spec"]
    assert isinstance(approved, dict)
    assert result["decision"] == "allowed"
    assert result["sensitive_route_audit"] == {
        "sensitive_route": "approved_spec",
        "linked_issue": evidence["linked_issue"],
        "artifact_paths": approved["spec_paths"],
        "maintainer_actor": approved["maintainer_actor"],
        "approved_at": approved["approved_at"],
        "state_source": approved["state_source"],
        "default_base_ref": approved["default_base_ref"],
        "default_base_sha": approved["default_base_sha"],
        "content_hashes": approved["content_hashes"],
    }


@pytest.mark.parametrize("missing", sorted(SPEC_APPROVAL_FIELDS))
def test_pr_gate_blocks_partial_spec_revision_audit_evidence(
    spec_revision_evidence: tuple[dict[str, object], Path, object],
    missing: str,
) -> None:
    evidence, repo, config = spec_revision_evidence
    approval = evidence["spec_approval"]
    assert isinstance(approval, dict)
    approval.pop(missing)

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert result["sensitive_route_audit"] is None
    assert "sensitive_enforcement" in result["missing"]


@pytest.mark.parametrize("forgery", ["mixed", "route_mismatch"])
def test_pr_gate_blocks_mixed_or_mismatched_spec_revision_route(
    spec_revision_evidence: tuple[dict[str, object], Path, object],
    forgery: str,
) -> None:
    evidence, repo, config = spec_revision_evidence
    if forgery == "mixed":
        evidence["approved_spec"] = {}
    else:
        evidence["sensitive_route"] = "approved_spec"

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert result["sensitive_route_audit"] is None


def test_pr_gate_blocks_sensitive_approved_spec_without_explicit_route(
    tmp_path: Path,
) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    evidence.pop("sensitive_route")

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert result["sensitive_route_audit"] is None
    assert any("sensitive_route=approved_spec" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    "missing_gate",
    ["checks", "review_threads", "human_authorization", "merge_state"],
)
def test_spec_revision_route_does_not_bypass_other_pr_gates(
    spec_revision_evidence: tuple[dict[str, object], Path, object],
    missing_gate: str,
) -> None:
    evidence, repo, config = spec_revision_evidence
    evidence.pop(missing_gate)

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] in {"blocked", "needs_human"}
    assert missing_gate in " ".join(result["missing"] + result["reasons"])
