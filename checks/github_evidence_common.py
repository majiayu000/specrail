"""Shared errors for read-only GitHub evidence adapters."""

from __future__ import annotations

from typing import Any


CONTENT_CATEGORIES = ("code_inputs", "spec_files", "pr_metadata")


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
