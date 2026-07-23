from __future__ import annotations

import hashlib
import json
from pathlib import Path
from shutil import copyfile

import pytest

from runtime_ledger_test_support import ROOT, clean_checkpoint
from runtime_ledger_gate import evaluate_checkpoint
from evidence_content_binding import build_content_binding_evidence


CURRENT_HEAD = "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"
PREVIOUS_HEAD = "1234567890abcdef1234567890abcdef12345678"
HASHES = {
    "code_inputs": "a" * 64,
    "spec_files": "b" * 64,
    "pr_metadata": "c" * 64,
}
SNAPSHOT = {
    "head_sha": CURRENT_HEAD,
    "base_tree_oid": "d" * 40,
    "algorithm": "sha256",
    "normalization": "specrail-v1",
    "collector": "github_pr_evidence",
}


def _v1_checkpoint(tmp_path: Path) -> dict[str, object]:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    artifact = json.loads(
        (ROOT / "tests/fixtures/gh143-review-artifact-pr718.json").read_text(
            encoding="utf-8"
        )
    )
    artifact.update(
        {
            "head_sha": PREVIOUS_HEAD,
            "content_binding_version": 1,
            "covered_categories": ["code_inputs", "spec_files"],
            "content_bindings": {
                "code_inputs": HASHES["code_inputs"],
                "spec_files": HASHES["spec_files"],
            },
        }
    )
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(exist_ok=True)
    for name in ["review_result.schema.json", "content_binding_evidence.schema.json"]:
        copyfile(ROOT / "schemas" / name, schema_dir / name)
    sidecar = build_content_binding_evidence(artifact["pr"], {
        "content_binding_version": 1,
        "snapshot": {**SNAPSHOT, "head_sha": PREVIOUS_HEAD},
        "content_hashes": HASHES,
    })
    sidecar_path = tmp_path / "artifacts/content-bindings/review.json"
    sidecar_path.parent.mkdir(parents=True)
    sidecar_raw = json.dumps(sidecar, sort_keys=True).encode("utf-8")
    sidecar_path.write_bytes(sidecar_raw)
    artifact["content_binding_evidence"] = {
        "artifact_id": sidecar["artifact_id"],
        "path": sidecar_path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(sidecar_raw).hexdigest(),
    }
    artifact_path = tmp_path / "review.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    audit = {
        "artifact_id": artifact["artifact_id"],
        "original_head_sha": PREVIOUS_HEAD,
        "covered_categories": ["code_inputs", "spec_files"],
        "original_content_bindings": dict(artifact["content_bindings"]),
        "current_content_bindings": {
            "code_inputs": HASHES["code_inputs"],
            "spec_files": HASHES["spec_files"],
        },
        "collector_provenance": SNAPSHOT,
        "reason": "all covered inputs match the current snapshot",
    }
    item.update(  # type: ignore[union-attr]
        {
            "content_binding_version": 1,
            "snapshot": SNAPSHOT,
            "content_hashes": HASHES,
            "reused_components": [audit],
        }
    )
    review = item["review"]  # type: ignore[index]
    review["evidence"] = str(artifact_path)  # type: ignore[index]
    review["head_sha"] = PREVIOUS_HEAD  # type: ignore[index]
    gate_result = {
        "decision": "allowed",
        "pr": item["pr"],  # type: ignore[index]
        "head_sha": CURRENT_HEAD,
        "enforcement_sensitive": False,
        "content_binding_version": 1,
        "snapshot": SNAPSHOT,
        "content_hashes": HASHES,
        "reused_components": [audit],
    }
    gate_path = tmp_path / "pr-gate.json"
    gate_path.write_text(json.dumps(gate_result), encoding="utf-8")
    item["pr_gate"]["evidence"] = str(gate_path)  # type: ignore[index]
    return checkpoint


def _use_current_head_legacy_review(checkpoint: dict[str, object]) -> None:
    item = checkpoint["items"][0]  # type: ignore[index]
    artifact_path = Path(item["review"]["evidence"])  # type: ignore[index]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    for key in [
        "content_binding_version",
        "covered_categories",
        "content_bindings",
        "content_binding_evidence",
    ]:
        artifact.pop(key)
    artifact["head_sha"] = CURRENT_HEAD
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    item["review"]["head_sha"] = CURRENT_HEAD  # type: ignore[index]


def test_runtime_allows_previous_head_component_with_matching_v1_bindings(
    tmp_path: Path,
) -> None:
    result = evaluate_checkpoint(_v1_checkpoint(tmp_path), repo=tmp_path)

    assert result["decision"] in {"allowed", "warn"}, result["errors"]


@pytest.mark.parametrize(
    "missing",
    [
        "content_binding_version",
        "snapshot",
        "content_hashes",
        "reused_components",
        "all",
    ],
)
def test_runtime_requires_item_to_copy_every_loaded_pr_gate_binding_field(
    tmp_path: Path,
    missing: str,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    _use_current_head_legacy_review(checkpoint)
    item = checkpoint["items"][0]  # type: ignore[index]
    binding_keys = [
        "content_binding_version",
        "snapshot",
        "content_hashes",
        "reused_components",
    ]
    omitted = binding_keys if missing == "all" else [missing]
    for key in omitted:
        item.pop(key)  # type: ignore[union-attr]

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    for key in omitted:
        assert any(
            f"must copy current pr_gate {key} exactly" in error
            for error in result["errors"]
        )


@pytest.mark.parametrize(
    "changed",
    [
        "content_binding_version",
        "snapshot",
        "content_hashes",
        "reused_components",
    ],
)
def test_runtime_requires_exact_loaded_pr_gate_binding_values(
    tmp_path: Path,
    changed: str,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    if changed == "content_binding_version":
        item[changed] = 2  # type: ignore[index]
    elif changed == "snapshot":
        item[changed] = {  # type: ignore[index]
            **item[changed],  # type: ignore[index]
            "collector": "caller_supplied",
        }
    elif changed == "content_hashes":
        item[changed] = {  # type: ignore[index]
            **item[changed],  # type: ignore[index]
            "pr_metadata": "f" * 64,
        }
    else:
        item[changed][0]["reason"] = "different runtime claim"  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any(
        f"must copy current pr_gate {changed} exactly" in error
        for error in result["errors"]
    )


def test_runtime_v1_review_sidecar_requires_repository_root(tmp_path: Path) -> None:
    result = evaluate_checkpoint(_v1_checkpoint(tmp_path))

    assert result["decision"] == "blocked"
    assert any("requires repository root" in error for error in result["errors"])


def test_runtime_blocks_previous_head_component_with_binding_mismatch(
    tmp_path: Path,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    artifact_path = Path(checkpoint["items"][0]["review"]["evidence"])  # type: ignore[index]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["content_bindings"]["spec_files"] = "f" * 64
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any("must match its collector sidecar" in error for error in result["errors"])


def test_runtime_keeps_legacy_previous_head_review_exact(
    tmp_path: Path,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    artifact_path = Path(checkpoint["items"][0]["review"]["evidence"])  # type: ignore[index]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    for key in [
        "content_binding_version",
        "covered_categories",
        "content_bindings",
        "content_binding_evidence",
    ]:
        artifact.pop(key)
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any("legacy review artifact head_sha" in error for error in result["errors"])


def test_runtime_blocks_pr_gate_reuse_audit_that_differs_from_item(
    tmp_path: Path,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    item["reused_components"][0]["reason"] = "tampered runtime audit"  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any("reused_components" in error for error in result["errors"])


def test_runtime_sensitive_reuse_requires_code_and_spec_coverage(
    tmp_path: Path,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    item["enforcement_sensitive"] = True  # type: ignore[index]
    artifact_path = Path(item["review"]["evidence"])  # type: ignore[index]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["covered_categories"] = ["code_inputs"]
    artifact["content_bindings"] = {"code_inputs": HASHES["code_inputs"]}
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    item["pr_gate"]["enforcement_sensitive"] = True  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any("code_inputs and spec_files" in error for error in result["errors"])


@pytest.mark.parametrize(
    "field",
    ["content_binding_extra", "covered_categories", "original_content_bindings"],
)
def test_runtime_v1_binding_rejects_unknown_item_field(
    tmp_path: Path, field: str
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    checkpoint["items"][0][field] = "undeclared"  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any(
        f"unknown v1 runtime item field {field!r}" in error
        for error in result["errors"]
    )


def test_runtime_legacy_item_keeps_extension_compatibility() -> None:
    checkpoint = clean_checkpoint()
    checkpoint["items"][0]["content_binding_extra"] = "legacy metadata"  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] in {"allowed", "warn"}, result["errors"]
    assert not any("unknown v1 runtime item field" in error for error in result["errors"])


def test_runtime_v1_reuse_rejects_duplicate_coverage(tmp_path: Path) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    audit = checkpoint["items"][0]["reused_components"][0]  # type: ignore[index]
    audit["covered_categories"] = ["code_inputs", "code_inputs"]
    audit["original_content_bindings"] = {"code_inputs": HASHES["code_inputs"]}
    audit["current_content_bindings"] = {"code_inputs": HASHES["code_inputs"]}

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any("coverage has duplicates" in error for error in result["errors"])


def test_runtime_v1_reuse_rejects_coverage_binding_key_mismatch(
    tmp_path: Path,
) -> None:
    checkpoint = _v1_checkpoint(tmp_path)
    audit = checkpoint["items"][0]["reused_components"][0]  # type: ignore[index]
    audit["current_content_bindings"].pop("spec_files")

    result = evaluate_checkpoint(checkpoint, repo=tmp_path)

    assert result["decision"] == "blocked"
    assert any(
        "current_content_bindings keys must equal coverage" in error
        for error in result["errors"]
    )
