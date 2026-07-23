from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from route_gate_test_support import write_sensitive_pack  # noqa: E402
from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402
from runtime_ledger_test_support import clean_checkpoint  # noqa: E402
from schema_validation import load_json_schema  # noqa: E402
from runtime_sensitive_routes import validate_runtime_sensitive_route  # noqa: E402
from spec_revision_evidence import spec_artifacts_sha256  # noqa: E402
from specrail_lib import InstanceMismatch, load_pack, validate_instance  # noqa: E402


def _revision_evidence(repo: Path, head: str) -> dict[str, object]:
    paths = ["specs/GH999/product.md", "specs/GH999/tech.md"]
    return {
        "repository": "example/consumer",
        "linked_issue": 999,
        "head_sha": head,
        "enforcement_sensitive": True,
        "sensitive_route": "spec_revision",
        "sensitive_classification": {
            "source": "github_changed_files",
            "changed_paths": paths,
            "matched_paths": [],
            "matched_specs": paths,
            "registry_configured": True,
            "enforcement_sensitive": True,
        },
        "spec_approval": {
            "lifecycle_state": "spec_approved",
            "state_source": "label",
            "state_trusted": True,
            "maintainer_actor": "maintainer",
            "approved_at": "2026-07-22T02:00:00Z",
            "approval_source": "github_pr_review",
            "approval_url": (
                "https://github.com/example/consumer/pull/177#pullrequestreview-1"
            ),
            "commit_oid": head,
            "artifact_paths": paths,
            "spec_artifacts_sha256": spec_artifacts_sha256(repo, head, paths),
        },
    }


def _revision_checkpoint(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    repo = tmp_path / "consumer"
    head = write_sensitive_pack(repo)
    workflow = repo / "workflow.yaml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "    specs: []", "    specs:\n      - specs/GH*/**"
        ),
        encoding="utf-8",
    )
    evidence_path = repo / ".specrail" / "spec-approval.json"
    evidence_path.parent.mkdir()
    evidence_path.write_text(
        json.dumps(_revision_evidence(repo, head)), encoding="utf-8"
    )
    checkpoint = clean_checkpoint()
    checkpoint["repo"] = "example/consumer"
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item.update(
        {
            "issue": 999,
            "state": "running",
            "head_sha": head,
            "enforcement_sensitive": True,
            "sensitive_route": "spec_revision",
            "spec_approval_evidence": ".specrail/spec-approval.json",
        }
    )
    return checkpoint, repo, evidence_path


def _schema() -> dict[str, object]:
    return load_json_schema(ROOT / "schemas" / "runtime_checkpoint.schema.json")


def test_spec_revision_runtime_item_revalidates_exact_head_approval(
    tmp_path: Path,
) -> None:
    checkpoint, repo, _ = _revision_checkpoint(tmp_path)

    result = evaluate_checkpoint(checkpoint, repo=repo, config=load_pack(repo))

    assert result["decision"] == "allowed"
    assert result["errors"] == []
    validate_instance(_schema(), checkpoint)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("head", "head_sha must match"),
        ("digest", "does not match gated-head artifacts"),
        ("issue", "linked_issue must match"),
    ],
)
def test_spec_revision_runtime_item_fails_closed_on_bound_evidence_drift(
    tmp_path: Path, mutation: str, message: str
) -> None:
    checkpoint, repo, evidence_path = _revision_checkpoint(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if mutation == "head":
        evidence["head_sha"] = "f" * 40
    elif mutation == "digest":
        evidence["spec_approval"]["spec_artifacts_sha256"] = "0" * 64
    else:
        evidence["linked_issue"] = 998
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result = evaluate_checkpoint(checkpoint, repo=repo, config=load_pack(repo))

    assert result["decision"] == "blocked"
    assert any(message in error for error in result["errors"])


def test_route_validation_is_not_skipped_by_an_earlier_same_label_error(
    tmp_path: Path,
) -> None:
    checkpoint, repo, evidence_path = _revision_checkpoint(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["spec_approval"]["spec_artifacts_sha256"] = "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    errors = ["item #1: unrelated earlier validation error"]

    validate_runtime_sensitive_route(
        item,
        "item #1",
        errors,
        repo=repo,
        config=load_pack(repo),
        repository=checkpoint["repo"],
    )

    assert errors[0].endswith("unrelated earlier validation error")
    assert any("does not match gated-head artifacts" in error for error in errors[1:])


def test_spec_revision_runtime_item_rejects_mixed_route_evidence(
    tmp_path: Path,
) -> None:
    checkpoint, repo, _ = _revision_checkpoint(tmp_path)
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item["approved_spec_evidence"] = "artifacts/approved-spec.json"

    result = evaluate_checkpoint(checkpoint, repo=repo, config=load_pack(repo))

    assert result["decision"] == "blocked"
    assert any("must not include approved_spec_evidence" in e for e in result["errors"])
    with pytest.raises(InstanceMismatch, match="anyOf"):
        validate_instance(_schema(), checkpoint)


def test_spec_revision_runtime_item_rejects_relative_evidence_escape(
    tmp_path: Path,
) -> None:
    checkpoint, repo, evidence_path = _revision_checkpoint(tmp_path)
    escaped = repo.parent / "escaped-spec-approval.json"
    escaped.write_bytes(evidence_path.read_bytes())
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item["spec_approval_evidence"] = "../escaped-spec-approval.json"

    result = evaluate_checkpoint(checkpoint, repo=repo, config=load_pack(repo))

    assert result["decision"] == "blocked"
    assert any("must stay inside the repository" in e for e in result["errors"])


def test_spec_revision_runtime_item_rejects_remote_evidence_url(
    tmp_path: Path,
) -> None:
    checkpoint, repo, _ = _revision_checkpoint(tmp_path)
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item["spec_approval_evidence"] = "https://example.invalid/spec-approval.json"

    result = evaluate_checkpoint(checkpoint, repo=repo, config=load_pack(repo))

    assert result["decision"] == "blocked"
    assert any("requires local machine-readable" in e for e in result["errors"])


def test_sensitive_runtime_item_requires_an_explicit_matching_route() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item["state"] = "running"
    item["enforcement_sensitive"] = True
    item["approved_spec_evidence"] = "artifacts/approved-spec.json"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("requires sensitive_route" in error for error in result["errors"])
    with pytest.raises(InstanceMismatch, match="sensitive_route.*missing required"):
        validate_instance(_schema(), checkpoint)


def test_approved_spec_route_preserves_legacy_evidence_requirement() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item.update(
        {
            "state": "running",
            "enforcement_sensitive": True,
            "sensitive_route": "approved_spec",
            "approved_spec_evidence": "artifacts/approved-spec.json",
        }
    )

    assert evaluate_checkpoint(checkpoint)["decision"] == "allowed"
    validate_instance(_schema(), checkpoint)

    missing = copy.deepcopy(checkpoint)
    missing_item = missing["items"][0]
    assert isinstance(missing_item, dict)
    missing_item.pop("approved_spec_evidence")
    assert evaluate_checkpoint(missing)["decision"] == "blocked"


def test_non_sensitive_legacy_checkpoint_remains_valid() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item["state"] = "running"

    assert evaluate_checkpoint(checkpoint)["decision"] == "allowed"
    validate_instance(_schema(), checkpoint)
