"""Shared errors for read-only GitHub evidence adapters."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Any

from schema_validation import (
    InstanceMismatch,
    SchemaDefinitionError,
    load_json_schema,
    validate_instance,
)
from rejection_items import finalize_items, item_from_reason


STATUS_CONTEXT_STATES = {"SUCCESS", "FAILURE", "ERROR", "PENDING", "EXPECTED"}
OUTCOME_LABELS = {"duplicate", "abandoned", "security_private"}


class EvidenceError(ValueError):
    """Raised when GitHub evidence cannot be collected or normalized."""


def _schema_mismatch_errors(
    schema: dict[str, Any],
    value: Any,
    path: str,
) -> list[str]:
    try:
        validate_instance(schema, value, path)
    except SchemaDefinitionError:
        raise
    except InstanceMismatch as exc:
        fallback = str(exc)
    else:
        return []

    errors: list[str] = []
    properties = schema.get("properties", {})
    if isinstance(value, dict) and isinstance(properties, dict):
        errors.extend(
            f"{path}.{field}: missing required field"
            for field in schema.get("required", [])
            if field not in value
        )
        additional = schema.get("additionalProperties", True)
        extra_fields = sorted(set(value) - set(properties))
        if additional is False:
            errors.extend(
                f"{path}.{field}: additional property is not allowed"
                for field in extra_fields
            )
        for field, child in properties.items():
            if field in value and isinstance(child, dict):
                errors.extend(
                    _schema_mismatch_errors(
                        child,
                        value[field],
                        f"{path}.{field}",
                    )
                )
        if isinstance(additional, dict):
            for field in extra_fields:
                errors.extend(
                    _schema_mismatch_errors(
                        additional,
                        value[field],
                        f"{path}.{field}",
                    )
                )
    items = schema.get("items")
    if isinstance(value, list) and isinstance(items, dict):
        for index, item in enumerate(value):
            errors.extend(
                _schema_mismatch_errors(items, item, f"{path}[{index}]")
            )
    return list(dict.fromkeys(errors or [fallback]))


def _issue_schema_errors(
    schema: dict[str, Any],
    evidence: dict[str, Any],
) -> list[str]:
    return _schema_mismatch_errors(schema, evidence, "issue evidence")


def json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def json_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be a JSON array")
    return value


def valid_testable_plan(value: Any) -> bool:
    """Return whether compact Issue-body plan evidence is complete."""
    if not isinstance(value, dict):
        return False
    items = value.get("items")
    digest = value.get("body_sha256")
    return (
        value.get("source") == "issue_body_checklist"
        and isinstance(items, list)
        and bool(items)
        and all(isinstance(item, str) and bool(item.strip()) for item in items)
        and isinstance(digest, str)
        and len(digest) == 64
        and set(digest.lower()) <= set("0123456789abcdef")
    )


def issue_route_evidence_errors(
    repo: Path,
    evidence: dict[str, Any],
    issue: int | None,
    github_repo: str | None,
    *,
    require_collector: bool = False,
    cli_state: str | None = None,
) -> list[str]:
    """Validate collector-shaped Issue evidence and bind it to this invocation."""
    if not require_collector and "issue" not in evidence and "repository" not in evidence:
        return []
    errors: list[str] = []
    try:
        schema = load_json_schema(repo / "schemas" / "issue_evidence.schema.json")
        errors.extend(_issue_schema_errors(schema, evidence))
    except SchemaDefinitionError as exc:
        errors.append(str(exc))
    if evidence.get("issue") != issue:
        errors.append(
            f"issue evidence number must match --issue {issue}; "
            f"got {evidence.get('issue')!r}"
        )
    repository = evidence.get("repository")
    if not github_repo:
        errors.append("collector Issue evidence requires --github-repo OWNER/REPO")
    elif repository != github_repo:
        errors.append(
            f"issue evidence repository must match --github-repo {github_repo}; "
            f"got {repository!r}"
        )
    if cli_state is not None and cli_state != evidence.get("state"):
        errors.append(
            f"--state {cli_state} conflicts with collector state "
            f"{evidence.get('state')!r}"
        )
    labels = evidence.get("labels")
    if isinstance(labels, list):
        label_set = {label for label in labels if isinstance(label, str)}
        state = evidence.get("state")
        trusted = evidence.get("state_trusted")
        source = evidence.get("state_source")
        if source == "label" and trusted is True and state not in label_set:
            errors.append("trusted label state must be present in issue evidence labels")
        if source != "label" and trusted is True:
            errors.append("state_trusted=true requires state_source=label")
        expected_outcomes = sorted(label_set & OUTCOME_LABELS)
        if evidence.get("outcomes") != expected_outcomes:
            errors.append("issue evidence outcomes must exactly match outcome labels")
    plan = evidence.get("testable_plan")
    if isinstance(plan, dict) and plan.get("body_sha256") != evidence.get("body_sha256"):
        errors.append("testable_plan.body_sha256 must match issue evidence body_sha256")
    return errors


def valid_security_evidence(
    repo: Path,
    approved_revision: Any,
    expected_spec_paths: list[str],
) -> bool:
    """Bind the current heavy spec packet to an approved immutable revision."""
    if (
        not isinstance(approved_revision, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40}", approved_revision)
        or not expected_spec_paths
    ):
        return False
    ancestry = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", approved_revision, "HEAD"],
        check=False,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        return False
    for path in expected_spec_paths:
        approved = subprocess.run(
            ["git", "-C", str(repo), "show", f"{approved_revision}:{path}"],
            check=False,
            capture_output=True,
        )
        try:
            current = (repo / path).read_bytes()
        except OSError:
            return False
        if approved.returncode != 0 or approved.stdout != current:
            return False
    return True


def blocked_route_result(
    route: str,
    current_state: str | None,
    args: Any,
    reasons: list[str],
    item_category: str = "invalid_state",
) -> dict[str, Any]:
    """Build the compact fail-closed route result used by early exits."""
    return {
        "decision": "blocked",
        "route": route,
        "profile": getattr(args, "profile", None) or "standard",
        "mode": args.mode,
        "current_state": current_state,
        "issue": args.issue,
        "pr": args.pr,
        "reasons": reasons,
        "satisfied": [],
        "missing": [],
        "rejection_items": finalize_items(
            item_from_reason(reason, item_category) for reason in reasons
        ),
        "required_artifacts": [],
        "human_gates": [],
        "allowed_actions": [],
        "blocked_actions": [route],
        "verification_commands": ["python3 checks/check_workflow.py --repo ."],
    }


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
