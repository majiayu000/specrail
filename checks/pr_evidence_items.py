#!/usr/bin/env python3
"""Deterministic validators for individual PR gate evidence fields.

Extracted from ``pr_gate.py`` so each evidence family stays readable and the
gate entrypoint keeps its size budget. Every validator returns the same
``(satisfied, missing, reasons)`` triple the gate aggregates.
"""

from __future__ import annotations

from typing import Any

from checks_availability import evaluate_checks_unavailable


CHECK_PASS_CONCLUSIONS = {"SUCCESS"}
MERGE_PATHS = {"gh_pr_merge", "api_fallback", "merged_by_other"}


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _check_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        if isinstance(checks, list):
            return evaluate_checks_unavailable(evidence)
        missing.append("checks")
        reasons.append("CI/check evidence is missing")
        return satisfied, missing, reasons

    if "checks_unavailable" in evidence:
        reasons.append("checks_unavailable must not be declared when checks are present")

    for index, item in enumerate(checks, start=1):
        if not isinstance(item, dict):
            reasons.append(f"check #{index} is not an object")
            continue
        name = str(item.get("name") or f"check #{index}")
        status = str(item.get("status") or "").upper()
        conclusion = str(item.get("conclusion") or "").upper()
        if status != "COMPLETED":
            reasons.append(f"{name} is not completed: {status or 'missing status'}")
            continue
        if conclusion not in CHECK_PASS_CONCLUSIONS:
            reasons.append(f"{name} did not pass: {conclusion or 'missing conclusion'}")
            continue
        satisfied.append(f"check passed: {name}")
    return satisfied, missing, reasons


def _issue_reference_items(
    evidence: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    if "issue_reference" not in evidence:
        return satisfied, missing, reasons
    relation = evidence["issue_reference"]
    if not isinstance(relation, dict):
        reasons.append("issue_reference must be an object")
        return satisfied, missing, reasons

    allowed_fields = {
        "number",
        "kind",
        "source",
        "verified",
        "state",
        "url",
        "closing_issue_numbers",
    }
    unknown_fields = sorted(set(relation) - allowed_fields)
    if unknown_fields:
        reasons.append(
            "issue_reference contains unsupported fields: " + ", ".join(unknown_fields)
        )

    number = relation.get("number")
    if not _positive_int(number):
        missing.append("issue_reference.number")
    elif number != evidence.get("linked_issue"):
        reasons.append("issue_reference.number must match linked_issue")

    if relation.get("verified") is not True:
        reasons.append("issue_reference.verified must be true")

    closing_issue_numbers = relation.get("closing_issue_numbers")
    valid_closing_numbers = isinstance(closing_issue_numbers, list) and all(
        _positive_int(item) for item in closing_issue_numbers
    )
    if not valid_closing_numbers:
        reasons.append("issue_reference.closing_issue_numbers must be a list of positive integers")
        closing_issue_numbers = []
    elif len(set(closing_issue_numbers)) != len(closing_issue_numbers):
        reasons.append("issue_reference.closing_issue_numbers must not contain duplicates")

    kind = relation.get("kind")
    source = relation.get("source")
    if kind == "partial":
        if source != "pr_body":
            reasons.append("issue_reference partial source must be pr_body")
        if relation.get("state") != "OPEN":
            reasons.append("issue_reference partial state must be OPEN")
        if _positive_int(number) and number in closing_issue_numbers:
            reasons.append("issue_reference partial target must not be closing")
    elif kind == "closing":
        if source != "closingIssuesReferences":
            reasons.append(
                "issue_reference closing source must be closingIssuesReferences"
            )
        if _positive_int(number) and number not in closing_issue_numbers:
            reasons.append(
                "issue_reference closing target must appear in closing_issue_numbers"
            )
    else:
        reasons.append("issue_reference.kind must be one of: closing, partial")

    if not missing and not reasons:
        satisfied.append(f"issue_reference: verified {kind} GH-{number}")
    return satisfied, missing, reasons


def _merge_record_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    record = evidence.get("merge_record")
    if record is None:
        return satisfied, missing, reasons
    if not isinstance(record, dict):
        reasons.append("merge_record must be an object")
        return satisfied, missing, reasons

    merge_path = record.get("merge_path")
    if not _non_empty_string(merge_path):
        missing.append("merge_record.merge_path")
    elif merge_path not in MERGE_PATHS:
        allowed = ", ".join(sorted(MERGE_PATHS))
        reasons.append(f"merge_record.merge_path must be one of: {allowed}")
    else:
        satisfied.append(f"merge_path: {merge_path}")

    if record.get("remote_confirmed") is not True:
        reasons.append(
            "merge_record.remote_confirmed must be true: confirm the merge "
            "outcome via a remote query (gh pr view --json merged,mergeCommit) "
            "before recording success or failure"
        )
    elif not _non_empty_string(record.get("merge_commit_sha")):
        missing.append("merge_record.merge_commit_sha")
    else:
        satisfied.append(f"merge remotely confirmed: {record['merge_commit_sha']}")

    outcome = record.get("branch_deletion_outcome")
    if outcome is not None and not _non_empty_string(outcome):
        reasons.append("merge_record.branch_deletion_outcome must be a non-empty string or null")

    return satisfied, missing, reasons
