"""Shared errors for read-only GitHub evidence adapters."""

from __future__ import annotations

from typing import Any


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


def normalize_checks(value: Any) -> list[dict[str, Any]]:
    """Normalize the current GitHub check rollup."""
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
