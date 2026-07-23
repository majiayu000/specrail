"""Route-aware validation for enforcement-sensitive runtime items."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from spec_revision_evidence import validate_spec_revision_evidence
from specrail_lib import PackConfig, SpecRailError


SENSITIVE_ROUTES = {"approved_spec", "spec_revision"}


def _local_evidence_path(
    reference: Any,
    *,
    repo: Path | None,
    label: str,
    errors: list[str],
) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        return None
    value = reference.strip()
    if urlparse(value).scheme:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if repo is None:
        errors.append(
            f"{label}: relative spec_approval_evidence requires a repository checkout"
        )
        return None
    root = repo.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append(
            f"{label}: relative spec_approval_evidence must stay inside the repository"
        )
        return None
    return resolved


def _load_evidence(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label}: spec_approval_evidence file does not exist: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{label}: cannot read spec_approval_evidence {path}: {exc}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(
            f"{label}: spec_approval_evidence is not valid JSON {path}: {exc.msg}"
        )
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label}: spec_approval_evidence JSON must be an object: {path}")
        return None
    return payload


def validate_runtime_sensitive_route(
    item: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    repo: Path | None,
    config: PackConfig | None,
    repository: Any,
) -> dict[str, Any] | None:
    """Validate one checkpoint item's route and return verified approval audit."""

    route = item.get("sensitive_route")
    approved_reference = item.get("approved_spec_evidence")
    revision_reference = item.get("spec_approval_evidence")
    if item.get("enforcement_sensitive") is not True:
        if route is not None or approved_reference is not None or revision_reference is not None:
            errors.append(
                f"{label}: sensitive route evidence requires enforcement_sensitive=true"
            )
        return None

    if route not in SENSITIVE_ROUTES:
        errors.append(
            f"{label}: enforcement-sensitive item requires sensitive_route "
            "approved_spec or spec_revision"
        )
        return None

    if route == "approved_spec":
        if not isinstance(approved_reference, str) or not approved_reference.strip():
            errors.append(
                f"{label}: approved_spec route requires approved_spec_evidence"
            )
        if revision_reference is not None:
            errors.append(
                f"{label}: approved_spec route must not include spec_approval_evidence"
            )
        return None

    if approved_reference is not None:
        errors.append(
            f"{label}: spec_revision route must not include approved_spec_evidence"
        )
    path = _local_evidence_path(
        revision_reference, repo=repo, label=label, errors=errors
    )
    if path is None:
        errors.append(
            f"{label}: spec_revision route requires local machine-readable "
            "spec_approval_evidence"
        )
        return None
    payload = _load_evidence(path, label, errors)
    if payload is None:
        return None
    if repo is None or config is None:
        errors.append(
            f"{label}: spec_revision route requires a repository checkout for "
            "exact-head validation"
        )
        return None

    issue = item.get("issue")
    head_sha = item.get("head_sha")
    identity_error_count = len(errors)
    if payload.get("sensitive_route") != route:
        errors.append(f"{label}: spec_approval_evidence sensitive_route must match item")
    if payload.get("linked_issue") != issue:
        errors.append(f"{label}: spec_approval_evidence linked_issue must match item issue")
    if payload.get("head_sha") != head_sha:
        errors.append(f"{label}: spec_approval_evidence head_sha must match item head_sha")
    if not isinstance(repository, str) or not repository.strip():
        errors.append(f"{label}: checkpoint repo must identify the repository")
    elif payload.get("repository") != repository.strip():
        errors.append(
            f"{label}: spec_approval_evidence repository must match checkpoint repo"
        )
    if len(errors) > identity_error_count:
        return None

    try:
        return validate_spec_revision_evidence(
            config,
            repo,
            payload,
            repository=repository.strip(),
            issue=issue,
            gated_head_sha=head_sha,
            classification=payload.get("sensitive_classification"),
        )
    except SpecRailError as exc:
        errors.append(f"{label}: {exc}")
        return None
