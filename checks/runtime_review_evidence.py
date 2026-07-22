"""Runtime loading of schema-backed terminal review evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evidence_content_binding import CONTENT_BINDING_VERSION
from github_evidence_common import EvidenceError
from review_content_binding import load_review_content_binding
from review_result_semantics import validate_review_artifact
from specrail_lib import SpecRailError, validate_instance


_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/review_result.schema.json"
_schema_cache: dict[str, Any] | None = None


def _schema() -> dict[str, Any]:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema_cache


def load_review_artifact_payload(
    raw_item: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    repo: Path | None = None,
    required: bool = False,
) -> dict[str, Any] | None:
    review = raw_item.get("review")
    reference = review.get("evidence") if isinstance(review, dict) else None
    if not isinstance(reference, str) or not reference.strip() or reference.startswith(("https://", "http://")):
        if required:
            errors.append(f"{label}: review.evidence must be a local machine-readable artifact path")
        return None
    path = Path(reference).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if required:
            errors.append(f"{label}: cannot load review artifact {path}: {exc}")
        return None
    if not isinstance(payload, dict):
        if required:
            errors.append(f"{label}: review artifact JSON must be an object: {path}")
        return None
    try:
        validate_instance(_schema(), payload, f"{label}: review artifact")
    except SpecRailError as exc:
        errors.append(str(exc))
        return None
    original_binding = None
    if payload.get("content_binding_version") == CONTENT_BINDING_VERSION:
        if repo is None:
            errors.append(f"{label}: v1 review artifact sidecar validation requires repository root")
        else:
            try:
                original_binding = load_review_content_binding(repo, payload)
            except EvidenceError as exc:
                errors.append(f"{label}: review artifact sidecar: {exc}")
    semantic = validate_review_artifact(
        payload,
        expected_pr=raw_item.get("pr"),
        expected_head_sha=raw_item.get("head_sha"),
        expected_lane=review.get("reviewer_lane"),
        current_binding={
            key: raw_item.get(key)
            for key in ["content_binding_version", "snapshot", "content_hashes"]
        }
        if raw_item.get("content_binding_version") == CONTENT_BINDING_VERSION
        else None,
        original_binding=original_binding,
        enforcement_sensitive=raw_item.get("enforcement_sensitive") is True,
    )
    errors.extend(
        f"{label}: review artifact: {message}"
        for message in [*semantic["errors"], *semantic["blocking_reasons"]]
    )
    return payload
