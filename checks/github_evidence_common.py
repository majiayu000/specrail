"""Shared errors for read-only GitHub evidence adapters."""

from __future__ import annotations

import hashlib
import json
from typing import Any


CONTENT_CATEGORIES = ("code_inputs", "spec_files", "pr_metadata")
STATUS_CONTEXT_STATES = {"SUCCESS", "FAILURE", "ERROR", "PENDING", "EXPECTED"}


class EvidenceError(ValueError):
    """Raised when GitHub evidence cannot be collected or normalized."""


def json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def json_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be a JSON array")
    return value


def trusted_ci_coverage(config: Any, check_name: str) -> tuple[str, ...] | None:
    """Return coverage declared by the current repository workflow config."""
    if not isinstance(check_name, str) or not check_name.strip():
        raise EvidenceError("check name must be a non-empty string")
    if config is None:
        return None
    workflow = getattr(config, "workflow", None)
    if not isinstance(workflow, dict):
        raise EvidenceError("workflow configuration must be an object")
    evidence = workflow.get("evidence", {})
    if not isinstance(evidence, dict):
        raise EvidenceError("workflow.yaml: evidence must be a mapping")
    configured = evidence.get("ci_component_coverage", {})
    if not isinstance(configured, dict):
        raise EvidenceError(
            "workflow.yaml: evidence.ci_component_coverage must be a mapping"
        )
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_name, raw_categories in configured.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise EvidenceError("configured CI check name must be a non-empty string")
        if raw_name != raw_name.strip():
            raise EvidenceError("configured CI check name must not have outer whitespace")
        if not isinstance(raw_categories, list) or not raw_categories:
            raise EvidenceError(
                f"configured CI coverage for {raw_name} must be a non-empty list"
            )
        if any(category not in CONTENT_CATEGORIES for category in raw_categories):
            raise EvidenceError(
                f"configured CI coverage for {raw_name} contains an unknown category"
            )
        if len(set(raw_categories)) != len(raw_categories):
            raise EvidenceError(
                f"configured CI coverage for {raw_name} must not contain duplicates"
            )
        normalized[raw_name] = tuple(raw_categories)
    return normalized.get(check_name.strip())


def _rollup_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        return value["nodes"]
    raise EvidenceError("statusCheckRollup must be a list or nodes object")


def _normalize_status_context(item: dict[str, Any]) -> tuple[str, str]:
    state = str(item.get("state") or "").upper()
    if state not in STATUS_CONTEXT_STATES:
        return "", ""
    if state == "SUCCESS":
        return "COMPLETED", "SUCCESS"
    if state in {"PENDING", "EXPECTED"}:
        return "IN_PROGRESS", ""
    return "COMPLETED", state


def normalize_checks(
    value: Any,
    content_binding: dict[str, Any] | None = None,
    head_sha: str | None = None,
    config: Any = None,
) -> list[dict[str, Any]]:
    """Normalize GitHub check rollups and attach trusted v1 coverage."""

    hashes = None
    if content_binding is not None:
        from evidence_content_binding import (  # Avoid a module import cycle.
            build_component_binding,
            validate_content_binding,
        )

        hashes = validate_content_binding(content_binding)["content_hashes"]
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(_rollup_items(value), start=1):
        if not isinstance(item, dict):
            raise EvidenceError(f"statusCheckRollup item #{index} must be an object")
        name = str(
            item.get("name")
            or item.get("context")
            or item.get("workflowName")
            or f"check #{index}"
        )
        status = str(item.get("status") or "").upper()
        conclusion = str(item.get("conclusion") or "").upper()
        if not status and not conclusion:
            status, conclusion = _normalize_status_context(item)
        if not status and conclusion == "SUCCESS":
            status = "COMPLETED"
        check = {"name": name, "status": status, "conclusion": conclusion}
        url = item.get("detailsUrl") or item.get("targetUrl")
        if isinstance(url, str) and url.strip():
            check["url"] = url.strip()
        coverage = trusted_ci_coverage(config, name) if hashes is not None else None
        if hashes is not None and coverage is not None:
            if not isinstance(head_sha, str) or not head_sha.strip():
                raise EvidenceError("v1 CI check requires the current head SHA")
            check.update(build_component_binding(coverage, hashes))
            check["artifact_id"] = "github-check:" + hashlib.sha256(
                json.dumps(
                    item,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            check["head_sha"] = head_sha.strip()
        checks.append(check)
    return checks


def normalize_reviews(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise EvidenceError("reviews must be a list")
    latest_by_author: dict[str, dict[str, str]] = {}
    author_order: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise EvidenceError(f"review item #{index} must be an object")
        state = str(item.get("state") or "").upper()
        if not state:
            continue
        raw_author = item.get("author")
        if isinstance(raw_author, dict):
            raw_author = raw_author.get("login")
        author = (
            raw_author.strip()
            if isinstance(raw_author, str) and raw_author.strip()
            else f"review #{index}"
        )
        if author not in latest_by_author:
            author_order.append(author)
        latest_by_author[author] = {"author": author, "state": state}
    return [latest_by_author[author] for author in author_order]
