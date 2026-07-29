#!/usr/bin/env python3
"""Shared compact-contract helpers for SpecRail gates.

Every rejecting gate emits a machine-readable ``rejection_items`` array so a
caller can fix all defects in one round. Items are deterministic, deduplicated,
and comparable across rounds via ``--prior-rejection`` payloads. This module
also owns the shared review-attestation and issue-label validators so the
18-file checker budget does not hide helper files below the top level.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from specrail_lib import (
    ISSUE_STATES,
    PackConfig,
    SpecRailError,
    label_groups,
    state_map,
)


CATEGORIES = frozenset(
    {
        "missing_artifact",
        "invalid_state",
        "missing_evidence_field",
        "invalid_evidence_value",
        "contract_violation",
        "config_error",
    }
)

_PLACEHOLDER_VALUES = frozenset(
    {"", "n/a", "na", "unknown", "none", "null", "-", "tbd", "todo"}
)
_NON_SUBSTANTIVE_VALUES = _PLACEHOLDER_VALUES | frozenset(
    {
        "coming soon",
        "pending",
        "placeholder",
        "to be decided",
        "to be defined",
        "to be determined",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")

_ITEM_ID_SUFFIX_RE = re.compile(r"#\d+$")


class RejectionItemError(ValueError):
    """Raised when a gate tries to build an invalid rejection item."""


ATTESTATION_COMMON_FIELDS = {
    "artifact_id",
    "head_sha",
    "invocation_id",
    "lane_id",
    "reviewer_actor",
    "review_sha256",
}
ATTESTATION_PRIOR_FIELDS = {"prior_artifact_id", "prior_head_sha"}
DEFAULT_OUTCOME_LABELS = {"duplicate", "abandoned", "security_private"}
HOSTED_FINDING_FIELDS = {
    "_created_at",
    "_last_edited_at",
    "_original_head_sha",
    "_review_head_sha",
    "_review_id",
    "_review_submitted_at",
    "_subject_type",
    "fix_paths",
    "id",
    "line",
    "origin",
    "outdated",
    "path",
    "severity",
    "status",
    "summary",
}
HOSTED_FINDING_REQUIRED = {
    "fix_paths",
    "id",
    "origin",
    "outdated",
    "severity",
    "status",
    "summary",
}


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def canonical_review_sha256(review: dict[str, Any]) -> str:
    """Hash the complete raw review using the canonical JSON representation."""

    payload = json.dumps(
        review,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_review_attestation(
    review: dict[str, Any],
    attestation: dict[str, Any] | None,
    *,
    gate_invocation_id: str | None,
    required: bool,
) -> tuple[list[str], list[str]]:
    """Return (missing, reasons) for one current host-injected attestation."""

    missing: list[str] = []
    reasons: list[str] = []
    if not required:
        if attestation is not None:
            reasons.append("self_review must not include review_attestation")
        return missing, reasons
    if not isinstance(attestation, dict):
        return ["review_attestation"], reasons
    if not _non_empty(gate_invocation_id):
        missing.append("gate_invocation_id")

    allowed = ATTESTATION_COMMON_FIELDS | ATTESTATION_PRIOR_FIELDS
    unknown = sorted(set(attestation) - allowed)
    absent = sorted(ATTESTATION_COMMON_FIELDS - set(attestation))
    if unknown:
        reasons.append(
            "review_attestation contains unsupported fields: "
            + ", ".join(unknown)
        )
    missing.extend(f"review_attestation.{field}" for field in absent)
    for field in (
        "artifact_id",
        "invocation_id",
        "lane_id",
        "reviewer_actor",
        "review_sha256",
    ):
        if field in attestation and not _non_empty(attestation.get(field)):
            reasons.append(f"review_attestation.{field} must be non-empty")
    if attestation.get("head_sha") != review.get("head_sha"):
        reasons.append("review_attestation.head_sha must match review head_sha")
    if attestation.get("artifact_id") != review.get("artifact_id"):
        reasons.append("review_attestation.artifact_id must match review")
    if _non_empty(gate_invocation_id) and (
        attestation.get("invocation_id") != gate_invocation_id
    ):
        reasons.append(
            "review_attestation.invocation_id must match gate invocation"
        )
    try:
        expected_digest = canonical_review_sha256(review)
    except (TypeError, ValueError):
        reasons.append("review artifact must be JSON-serializable")
    else:
        if attestation.get("review_sha256") != expected_digest:
            reasons.append(
                "review_attestation.review_sha256 must match canonical review"
            )

    prior = review.get("prior_review")
    if review.get("round") == 2 and isinstance(prior, dict):
        expected = {
            "prior_artifact_id": prior.get("artifact_id"),
            "prior_head_sha": prior.get("head_sha"),
        }
        for field, value in expected.items():
            if attestation.get(field) != value:
                reasons.append(
                    f"review_attestation.{field} must match prior review"
                )
    elif set(attestation) & ATTESTATION_PRIOR_FIELDS:
        reasons.append("round 1 review_attestation must not bind prior review")
    return missing, reasons


def validate_hosted_findings(value: Any) -> list[str]:
    """Validate the closed server-canonical hosted finding evidence layer."""

    if not isinstance(value, list):
        return ["hosted_findings must be an array"]
    reasons: list[str] = []
    seen: set[str] = set()
    for index, finding in enumerate(value, start=1):
        prefix = f"hosted finding #{index}"
        if not isinstance(finding, dict):
            reasons.append(f"{prefix} must be an object")
            continue
        unknown = sorted(set(finding) - HOSTED_FINDING_FIELDS)
        missing = sorted(HOSTED_FINDING_REQUIRED - set(finding))
        if unknown:
            reasons.append(
                f"{prefix} contains unsupported fields: {', '.join(unknown)}"
            )
        reasons.extend(f"{prefix} missing {field}" for field in missing)
        for field in (
            "_created_at",
            "_review_id",
            "_review_submitted_at",
            "id",
            "summary",
        ):
            if field in finding and not _non_empty(finding[field]):
                reasons.append(f"{prefix} {field} must be non-empty")
        finding_id = finding.get("id")
        if _non_empty(finding_id):
            if str(finding_id) in seen:
                reasons.append(f"{prefix} id must be unique")
            seen.add(str(finding_id))
        if finding.get("origin") != "hosted":
            reasons.append(f"{prefix} origin must be hosted")
        if finding.get("severity") not in {"P0", "P1", "P2", "P3"}:
            reasons.append(f"{prefix} severity is invalid")
        if finding.get("status") not in {"resolved", "unresolved"}:
            reasons.append(f"{prefix} status is invalid")
        if (
            "_subject_type" in finding
            and finding.get("_subject_type") not in {"FILE", "LINE"}
        ):
            reasons.append(f"{prefix} _subject_type is invalid")
        if not isinstance(finding.get("outdated"), bool):
            reasons.append(f"{prefix} outdated must be a boolean")
        paths = finding.get("fix_paths")
        if (
            not isinstance(paths, list)
            or not paths
            or not all(_non_empty(path) for path in paths)
        ):
            reasons.append(f"{prefix} fix_paths must contain non-empty strings")
        for field in (
            "_original_head_sha",
            "_review_head_sha",
        ):
            if field in finding and (
                not isinstance(finding[field], str)
                or re.fullmatch(r"[0-9a-fA-F]{40}", finding[field]) is None
            ):
                reasons.append(f"{prefix} {field} must be a 40-character Git SHA")
        if "_last_edited_at" in finding and finding["_last_edited_at"] is not None:
            if not _non_empty(finding["_last_edited_at"]):
                reasons.append(f"{prefix} _last_edited_at must be non-empty or null")
        if "path" in finding and not _non_empty(finding.get("path")):
            reasons.append(f"{prefix} path must be non-empty")
        if "line" in finding and (
            not isinstance(finding["line"], int)
            or isinstance(finding["line"], bool)
            or finding["line"] <= 0
        ):
            reasons.append(f"{prefix} line must be positive")
    return reasons


def validate_issue_labels(
    config: PackConfig | None,
    labels: list[str],
) -> tuple[str | None, list[str]]:
    """Return the single workflow state and outcomes, rejecting conflicts."""

    if config is None:
        state_labels = set(ISSUE_STATES)
        outcome_labels = DEFAULT_OUTCOME_LABELS
    else:
        groups = label_groups(config)
        states = state_map(config)
        terminal = {
            name
            for name, body in states.items()
            if isinstance(body, dict) and body.get("terminal") is True
        }
        state_labels = (
            set(groups.get("readiness", []))
            | set(groups.get("lifecycle", []))
            | terminal
            | ({"parked"} if "parked" in states else set())
        )
        outcome_labels = set(groups.get("outcome", []))

    state_matches = sorted(set(labels) & state_labels)
    outcome_matches = sorted(set(labels) & outcome_labels)
    if len(state_matches) > 1:
        raise SpecRailError(
            f"conflicting state labels: {', '.join(state_matches)}"
        )
    if len(outcome_matches) > 1:
        raise SpecRailError(
            f"conflicting outcome labels: {', '.join(outcome_matches)}"
        )
    if state_matches and outcome_matches:
        combined = sorted(set(state_matches) | set(outcome_matches))
        raise SpecRailError(
            f"conflicting terminal/readiness labels: {', '.join(combined)}"
        )
    return (state_matches[0] if state_matches else None), outcome_matches


def _compact_text(value: str) -> str:
    # Re-decompose after NFKC so a combining mark cannot hide in a composed
    # character before the category filter removes M* code points.
    normalized = unicodedata.normalize(
        "NFD",
        unicodedata.normalize("NFKC", value).casefold(),
    )
    characters: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if not character.isspace() and category[0] not in {"C", "M", "P", "S", "Z"}:
            characters.append(character)
    return "".join(characters)


_NON_SUBSTANTIVE_STRINGS = tuple(
    sorted(
        {
            compact
            for value in _NON_SUBSTANTIVE_VALUES
            if (compact := _compact_text(value))
        }
    )
)


def is_substantive_text(value: Any) -> bool:
    """Reject text composed only of declared placeholders and separators."""
    if not isinstance(value, str):
        return False
    compact = _compact_text(value)
    if not compact:
        return False
    reachable = {0}
    for start in range(len(compact)):
        if start not in reachable:
            continue
        for placeholder in _NON_SUBSTANTIVE_STRINGS:
            end = start + len(placeholder)
            if compact[start:end] == placeholder:
                reachable.add(end)
    return len(compact) not in reachable


def _slug(text: str) -> str:
    return _WHITESPACE_RE.sub("-", text.strip())


def make_item(category: str, subject: str, expected: str, found: str) -> dict[str, str]:
    """Build one validated rejection item with a stable ``item_id``."""

    if category not in CATEGORIES:
        allowed = ", ".join(sorted(CATEGORIES))
        raise RejectionItemError(
            f"rejection item category must be one of: {allowed}; got {category!r}"
        )
    for name, value in [("subject", subject), ("expected", expected), ("found", found)]:
        if not isinstance(value, str) or not value.strip():
            raise RejectionItemError(f"rejection item {name} must be a non-empty string")
    for name, value in [("expected", expected), ("found", found)]:
        if value.strip().lower() in _PLACEHOLDER_VALUES:
            raise RejectionItemError(
                f"rejection item {name} must be a concrete value description; "
                f"got placeholder {value!r}"
            )
    return {
        "item_id": f"{category}:{_slug(subject)}",
        "category": category,
        "expected": expected.strip(),
        "found": found.strip(),
    }


def item_from_missing(entry: str, category: str = "missing_evidence_field") -> dict[str, str]:
    """Convert one legacy ``missing`` entry into a rejection item."""

    return make_item(category, entry, f"{entry} present", "absent")


def _concrete_found(observed: str) -> str:
    """Normalize placeholder observations into a concrete ``found`` description.

    Legacy validators report values like ``...; got None`` or ``...; got ''``;
    passing those raw into :func:`make_item` trips the placeholder guard and
    degrades the whole result to one ``config_error``.
    """

    text = observed.strip()
    if text.lower() in _PLACEHOLDER_VALUES:
        return f"placeholder value {text!r} reported"
    return text


def item_from_reason(reason: str, category: str = "contract_violation") -> dict[str, str]:
    """Convert one legacy ``reasons`` entry into a rejection item."""

    requirement, sep, observed = reason.partition("; got ")
    if sep and requirement.strip() and observed.strip():
        return make_item(category, requirement, requirement, _concrete_found(observed))
    return make_item(
        category,
        reason,
        f"requirement satisfied: {reason}",
        f"requirement violated: {reason}",
    )


def items_from_legacy(
    missing: Iterable[str] = (),
    reasons: Iterable[str] = (),
    *,
    missing_category: str = "missing_evidence_field",
    reason_category: str = "contract_violation",
) -> list[dict[str, str]]:
    """Convert legacy missing/reasons string lists into rejection items."""

    items = [item_from_missing(entry, missing_category) for entry in missing]
    items.extend(item_from_reason(reason, reason_category) for reason in reasons)
    return items


def _validate_item_shape(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        raise RejectionItemError("rejection item must be an object")
    for key in ["item_id", "category", "expected", "found"]:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RejectionItemError(f"rejection item requires non-empty {key}")
    if item["category"] not in CATEGORIES:
        allowed = ", ".join(sorted(CATEGORIES))
        raise RejectionItemError(
            f"rejection item category must be one of: {allowed}; got {item['category']!r}"
        )
    return {key: item[key] for key in ["item_id", "category", "expected", "found"]}


def finalize_items(items: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicate and deterministically order rejection items.

    Items sharing an ``item_id`` with identical ``(expected, found)`` merge into
    one entry. Differing pairs are all kept: the group is sorted by
    ``(expected, found)`` and each entry gets a ``#1``, ``#2``... suffix, so the
    output is independent of input order and loses no comparison data.
    """

    groups: dict[str, dict[str, Any]] = {}
    for raw in items:
        item = _validate_item_shape(raw)
        group = groups.setdefault(
            item["item_id"], {"category": item["category"], "pairs": set()}
        )
        group["pairs"].add((item["expected"], item["found"]))

    output: list[dict[str, str]] = []
    for item_id in groups:
        category = groups[item_id]["category"]
        pairs = sorted(groups[item_id]["pairs"])
        if len(pairs) == 1:
            expected, found = pairs[0]
            output.append(
                {
                    "item_id": item_id,
                    "category": category,
                    "expected": expected,
                    "found": found,
                }
            )
            continue
        for index, (expected, found) in enumerate(pairs, start=1):
            output.append(
                {
                    "item_id": f"{item_id}#{index}",
                    "category": category,
                    "expected": expected,
                    "found": found,
                }
            )
    return sorted(output, key=lambda entry: entry["item_id"])


def load_prior_rejection(
    path: str | Path,
) -> tuple[list[dict[str, str]] | None, dict[str, str] | None]:
    """Load a prior rejection payload; fail closed into a config_error item."""

    expected = "readable prior rejection payload containing rejection_items[]"
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        return None, make_item(
            "config_error",
            "prior_rejection",
            expected,
            f"cannot read prior rejection file {path}: {exc}",
        )
    except json.JSONDecodeError as exc:
        return None, make_item(
            "config_error",
            "prior_rejection",
            expected,
            f"invalid prior rejection JSON {path}: {exc.msg}",
        )
    if not isinstance(data, dict) or not isinstance(data.get("rejection_items"), list):
        return None, make_item(
            "config_error",
            "prior_rejection",
            expected,
            f"prior rejection payload {path} lacks a rejection_items list",
        )
    items: list[dict[str, str]] = []
    for index, entry in enumerate(data["rejection_items"]):
        if not isinstance(entry, dict):
            return None, make_item(
                "config_error",
                "prior_rejection",
                expected,
                f"prior rejection payload {path} has a non-object entry at "
                f"rejection_items[{index}]",
            )
        items.append(
            {
                "item_id": str(entry.get("item_id") or ""),
                "category": str(entry.get("category") or ""),
                "expected": str(entry.get("expected") or ""),
                "found": str(entry.get("found") or ""),
            }
        )
    return items, None


def _base_item_id(item_id: str | None) -> str:
    """Strip a ``#N`` conflict suffix so ids compare stably across rounds."""

    return _ITEM_ID_SUFFIX_RE.sub("", item_id or "")


def repeat_rejection(
    current: Iterable[dict[str, str]], prior: Iterable[dict[str, str]]
) -> list[str]:
    """Return item_ids rejected identically (id+expected+found) in both rounds.

    Conflict suffixes (``#1``/``#2``) are stripped before comparison: an item
    suffixed in round one because of a same-id conflict still counts as a
    repeat when it survives unsuffixed after the conflicting sibling is fixed.
    """

    prior_triples = {
        (_base_item_id(item.get("item_id")), item.get("expected"), item.get("found"))
        for item in prior
    }
    return sorted(
        {
            item["item_id"]
            for item in current
            if (
                _base_item_id(item.get("item_id")),
                item.get("expected"),
                item.get("found"),
            )
            in prior_triples
        }
    )


def add_prior_rejection_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prior-rejection",
        help="Prior round rejection payload JSON used to detect repeat rejections",
    )


def apply_prior_rejection(
    result: dict[str, Any],
    prior_path: str | None,
    *,
    blocked_actions: Iterable[str] = (),
) -> dict[str, Any]:
    """Compare this round's rejection_items against a prior payload.

    An unusable prior payload becomes a blocking ``config_error`` item (B-006)
    and blocks the caller-declared ``blocked_actions`` so the JSON stays
    self-consistent. Identical repeated items surface as a
    ``repeat_rejection`` section (B-005).
    """

    if not prior_path:
        return result
    prior_items, error_item = load_prior_rejection(prior_path)
    if error_item is not None:
        items = list(result.get("rejection_items") or [])
        items.append(error_item)
        result["rejection_items"] = finalize_items(items)
        result["decision"] = "blocked"
        merged_blocked = set(result.get("blocked_actions") or [])
        merged_blocked.update(blocked_actions)
        result["blocked_actions"] = sorted(merged_blocked)
        reasons = list(result.get("reasons") or [])
        reasons.append(f"--prior-rejection payload is unusable: {error_item['found']}")
        result["reasons"] = reasons
        return result
    repeats = repeat_rejection(result.get("rejection_items") or [], prior_items or [])
    if repeats:
        result["repeat_rejection"] = {"item_ids": repeats}
    return result
