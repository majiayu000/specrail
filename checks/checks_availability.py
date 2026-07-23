#!/usr/bin/env python3
"""Validate declarations that hosted CI checks cannot run for a pull request.

Hosted checks can be absent for two very different reasons. Either the run has
not finished or has failed, which a retry or a new review round can change, or
the repository never triggers a workflow for this pull request at all, which no
number of rounds can change.

This module only evaluates an explicit, collector-provided declaration of the
second case. It never inspects GitHub or workflow files, never infers the state,
and never turns a missing declaration into a pass. Acceptance is always recorded
as a degraded outcome so a downgrade cannot be read as a passing CI run.
"""

from __future__ import annotations

from typing import Any


CHECKS_UNAVAILABLE_REASONS = {"hosted_ci_not_triggered_for_base"}

ALLOWED_FIELDS = {
    "reason",
    "base_ref",
    "default_base_ref",
    "workflow_trigger_evidence",
    "local_verification",
    "verified",
}


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def evaluate_checks_unavailable(
    evidence: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Return (satisfied, missing, reasons) for an empty ``checks`` list.

    Callers pass the whole PR evidence object. When the declaration is absent or
    fails any validation, ``checks`` is reported missing exactly as before.
    """

    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    declaration = evidence.get("checks_unavailable")
    if declaration is None:
        missing.append("checks")
        reasons.append("CI/check evidence is missing")
        return satisfied, missing, reasons

    if not isinstance(declaration, dict):
        reasons.append("checks_unavailable must be an object")
        missing.append("checks")
        return satisfied, missing, reasons

    unknown_fields = sorted(set(declaration) - ALLOWED_FIELDS)
    if unknown_fields:
        reasons.append(
            "checks_unavailable contains unsupported fields: "
            + ", ".join(unknown_fields)
        )

    reason_value = declaration.get("reason")
    if reason_value not in CHECKS_UNAVAILABLE_REASONS:
        reasons.append(
            "checks_unavailable.reason must be one of: "
            + ", ".join(sorted(CHECKS_UNAVAILABLE_REASONS))
        )

    base_ref = declaration.get("base_ref")
    default_base_ref = declaration.get("default_base_ref")

    if not _non_empty_string(base_ref):
        missing.append("checks_unavailable.base_ref")
    elif _non_empty_string(evidence.get("base_ref")) and base_ref != evidence["base_ref"]:
        reasons.append("checks_unavailable.base_ref must match base_ref")

    if not _non_empty_string(default_base_ref):
        missing.append("checks_unavailable.default_base_ref")
    elif (
        _non_empty_string(evidence.get("default_base_ref"))
        and default_base_ref != evidence["default_base_ref"]
    ):
        reasons.append("checks_unavailable.default_base_ref must match default_base_ref")

    if (
        _non_empty_string(base_ref)
        and _non_empty_string(default_base_ref)
        and base_ref == default_base_ref
    ):
        reasons.append(
            "checks_unavailable requires base_ref to differ from default_base_ref"
        )

    if not _non_empty_string(declaration.get("workflow_trigger_evidence")):
        missing.append("checks_unavailable.workflow_trigger_evidence")

    local_verification = declaration.get("local_verification")
    if not isinstance(local_verification, list) or not local_verification:
        missing.append("checks_unavailable.local_verification")
    elif not all(_non_empty_string(item) for item in local_verification):
        reasons.append(
            "checks_unavailable.local_verification entries must be non-empty strings"
        )

    if declaration.get("verified") is not True:
        reasons.append("checks_unavailable.verified must be true")

    if missing or reasons:
        missing.append("checks")
        return satisfied, missing, reasons

    satisfied.append(
        "degraded: hosted checks unavailable "
        f"({reason_value}; base_ref {base_ref} differs from "
        f"default_base_ref {default_base_ref}); accepted "
        f"{len(local_verification)} local verification command(s)"
    )
    return satisfied, missing, reasons
