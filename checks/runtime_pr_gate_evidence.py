"""Load and bind local PR-gate evidence to runtime checkpoint items."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pr_gate import evaluate_pr_gate
from runtime_tier_authorization import FASTLANE_SELF_REVIEW_BASIS
from specrail_lib import PackConfig


def resolve_local_evidence_path(reference: Any) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        return None
    normalized = reference.strip()
    if normalized.startswith(("https://", "http://")):
        return None
    return Path(normalized).expanduser()


def load_local_json(
    path: Path,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label}: evidence file does not exist: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{label}: cannot read evidence file {path}: {exc}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: evidence file is not valid JSON {path}: {exc.msg}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label}: evidence file JSON must be an object: {path}")
        return None
    return payload


def validate_pr_gate_artifact(
    raw_item: dict[str, Any],
    evidence: Any,
    label: str,
    errors: list[str],
    repo: Path | None,
    config: PackConfig | None,
) -> dict[str, Any] | None:
    authorization = raw_item.get("self_review_authorization")
    fastlane_self_review = (
        isinstance(authorization, dict)
        and authorization.get("basis") == FASTLANE_SELF_REVIEW_BASIS
    )
    path = resolve_local_evidence_path(evidence)
    if path is None:
        if raw_item.get("enforcement_sensitive") is True or fastlane_self_review:
            errors.append(
                f"{label}: sensitive or fastlane self-review item requires "
                "local machine-readable pr_gate evidence"
            )
        return None
    payload = load_local_json(path, f"{label}: pr_gate", errors)
    if payload is None:
        return None

    result = (
        payload
        if "decision" in payload
        else evaluate_pr_gate(payload, repo=repo, config=config)
    )
    if result.get("decision") != "allowed":
        reasons = result.get("reasons")
        detail = f": {reasons}" if reasons else ""
        errors.append(f"{label}: pr_gate evidence decision must be allowed{detail}")

    item_pr = raw_item.get("pr")
    if item_pr and result.get("pr") and result.get("pr") != item_pr:
        errors.append(f"{label}: pr_gate evidence pr must match item pr")
    item_head = raw_item.get("head_sha")
    if item_head and result.get("head_sha") and result.get("head_sha") != item_head:
        errors.append(f"{label}: pr_gate evidence head_sha must match item head_sha")

    binding_keys = [
        "content_binding_version",
        "snapshot",
        "content_hashes",
        "reused_components",
    ]
    result_has_binding = (
        result.get("content_binding_version") == 1
        or any(result.get(key) is not None for key in binding_keys[1:])
    )
    if result_has_binding or any(key in raw_item for key in binding_keys):
        for key in binding_keys:
            if key not in raw_item or raw_item.get(key) != result.get(key):
                errors.append(
                    f"{label}: runtime item must copy current pr_gate {key} exactly"
                )

    if fastlane_self_review:
        for key in [
            "review_source",
            "pr_tier",
            "pr_tier_evidence",
            "enforcement_sensitive",
        ]:
            if key not in raw_item or raw_item.get(key) != result.get(key):
                errors.append(
                    f"{label}: fastlane runtime item must copy current pr_gate "
                    f"{key} exactly"
                )
    elif raw_item.get("enforcement_sensitive") is True and result.get(
        "enforcement_sensitive"
    ) is not True:
        errors.append(
            f"{label}: sensitive item requires enforcement-sensitive pr_gate evidence"
        )
    return result
