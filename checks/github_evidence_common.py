"""Shared errors for read-only GitHub evidence adapters."""

from __future__ import annotations

from typing import Any


TRUSTED_CI_COVERAGE = {
    "workflow-check": ("code_inputs", "spec_files"),
    "lint": ("code_inputs",),
}


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


def trusted_ci_coverage(check_name: str) -> tuple[str, ...] | None:
    """Return repo-owned reusable coverage; unknown checks stay legacy."""
    if not isinstance(check_name, str) or not check_name.strip():
        raise EvidenceError("check name must be a non-empty string")
    return TRUSTED_CI_COVERAGE.get(check_name.strip())
