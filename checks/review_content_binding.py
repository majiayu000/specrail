"""Trusted sidecar validation for reusable terminal review artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evidence_content_binding import (
    load_content_binding_evidence,
    validate_component_binding,
    validate_content_binding,
)
from github_evidence_common import EvidenceError


def is_versioned_review(artifact: dict[str, Any]) -> bool:
    return any(
        key in artifact
        for key in [
            "content_binding_version",
            "covered_categories",
            "content_bindings",
            "content_binding_evidence",
        ]
    )


def load_review_content_binding(
    repo: Path, artifact: dict[str, Any],
) -> dict[str, Any] | None:
    if not is_versioned_review(artifact):
        return None
    pr = artifact.get("pr")
    head = artifact.get("head_sha")
    if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
        raise EvidenceError("review artifact pr must identify its content binding evidence")
    if not isinstance(head, str) or not head:
        raise EvidenceError("review artifact head_sha must identify its content binding evidence")
    return load_content_binding_evidence(
        repo,
        artifact.get("content_binding_evidence"),
        expected_pr=pr,
        expected_head_sha=head,
    )


def artifact_binding_errors(
    artifact: dict[str, Any],
    *,
    expected_head_sha: str | None,
    current_binding: dict[str, Any] | None,
    original_binding: dict[str, Any] | None,
    enforcement_sensitive: bool,
) -> list[str]:
    """Validate legacy exact-head or sidecar-authenticated v1 review evidence."""

    if not is_versioned_review(artifact):
        if expected_head_sha is not None and artifact.get("head_sha") != expected_head_sha:
            return ["legacy review artifact head_sha must match the expected final head"]
        return []
    errors: list[str] = []
    try:
        covered, component_hashes = validate_component_binding(artifact)
    except EvidenceError as exc:
        return [f"review content binding is invalid: {exc}"]
    if original_binding is None:
        return ["v1 review artifact requires trusted collector binding evidence sidecar"]
    try:
        original = validate_content_binding(original_binding)
    except EvidenceError as exc:
        return [f"review collector binding evidence is invalid: {exc}"]
    original_hashes = original["content_hashes"]
    mismatched = [key for key in covered if component_hashes[key] != original_hashes[key]]
    if mismatched:
        errors.append(
            "review artifact content bindings must match its collector sidecar: "
            + ", ".join(mismatched)
        )
    if current_binding is None:
        if expected_head_sha is None and not enforcement_sensitive:
            return errors
        return [*errors, "v1 review artifact requires the current content binding"]
    try:
        current = validate_content_binding(current_binding)
    except EvidenceError as exc:
        return [*errors, f"review content binding is invalid: {exc}"]
    if expected_head_sha is not None and current["snapshot"]["head_sha"] != expected_head_sha:
        errors.append("current content binding snapshot.head_sha must match the expected final head")
    if any(original_hashes[key] != current["content_hashes"][key] for key in covered):
        errors.append("review artifact covered content bindings do not match the current snapshot")
    if enforcement_sensitive:
        missing = sorted({"code_inputs", "spec_files"} - set(covered))
        if missing:
            errors.append(
                "enforcement-sensitive review must cover actual code_inputs and spec_files"
            )
        if artifact.get("review_source") != "independent_lane":
            errors.append("enforcement-sensitive review must remain an independent terminal review")
    return errors
