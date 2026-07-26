#!/usr/bin/env python3
"""Evaluate merge authorization and the reduced fastlane evidence profile."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from pr_evidence_items import _check_items
from rejection_items import finalize_items, item_from_missing, item_from_reason
from schema_validation import SpecRailError, load_json_schema, validate_instance


AUTH_MODES = {"auto", "review"}
MERGE_READY_VERDICTS = {"clean", "non_blocking"}


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _parse_timestamp(value: Any) -> datetime | None:
    if not _non_empty_string(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _signal(signal_type: str, signal: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "signal_type": signal_type,
        "signal": signal,
        "reason": reason,
    }


def evaluate_merge_authorization(
    evidence: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]]]:
    """Validate review-mode or run-scoped auto merge authorization."""

    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    signals: list[dict[str, Any]] = []

    auth_mode = evidence.get("auth_mode", "review")
    if auth_mode not in AUTH_MODES:
        reasons.append("auth_mode must be auto or review")
        signals.append(
            _signal(
                "auth_mode",
                {"auth_mode": auth_mode},
                "unsupported authorization mode",
            )
        )
        return satisfied, missing, reasons, signals

    head_sha = evidence.get("head_sha")
    review_completed_at = _parse_timestamp(evidence.get("review_completed_at"))
    gate_started_at = _parse_timestamp(evidence.get("gate_started_at"))
    if review_completed_at is None:
        missing.append("review_completed_at")
        if evidence.get("review_completed_at") is not None:
            reasons.append(
                "review_completed_at must be a timezone-aware ISO-8601 timestamp"
            )
    if gate_started_at is None:
        missing.append("gate_started_at")
        if evidence.get("gate_started_at") is not None:
            reasons.append(
                "gate_started_at must be a timezone-aware ISO-8601 timestamp"
            )
    if (
        review_completed_at is not None
        and gate_started_at is not None
        and review_completed_at > gate_started_at
    ):
        reasons.append("review must complete at or before authorization gate start")

    if auth_mode == "review":
        if evidence.get("run_authorization") is not None:
            reasons.append("run_authorization is valid only in auth_mode auto")
        authorization = evidence.get("human_authorization")
        if not isinstance(authorization, dict):
            missing.append("human_authorization")
            signals.append(
                _signal(
                    "merge_authorization",
                    {"auth_mode": "review", "present": False},
                    "per-PR human authorization is missing",
                )
            )
            return satisfied, missing, reasons, signals

        for key in ["actor", "source", "head_sha", "authorized_at"]:
            if not _non_empty_string(authorization.get(key)):
                missing.append(f"human_authorization.{key}")
        if not _positive_int(authorization.get("pr")):
            missing.append("human_authorization.pr")
        elif authorization.get("pr") != evidence.get("pr"):
            reasons.append(
                "human_authorization.pr must match the gated pr"
            )
        if authorization.get("head_sha") != head_sha:
            reasons.append(
                "human_authorization.head_sha must match the current head_sha"
            )
        authorized_at = _parse_timestamp(authorization.get("authorized_at"))
        if authorized_at is None:
            reasons.append(
                "human_authorization.authorized_at must be a timezone-aware "
                "ISO-8601 timestamp"
            )
        if (
            authorized_at is not None
            and review_completed_at is not None
            and authorized_at < review_completed_at
        ):
            reasons.append(
                "human_authorization.authorized_at must be at or after "
                "review_completed_at"
            )
        if not missing and not reasons:
            satisfied.append(
                "review-mode human authorization is bound to the reviewed exact head"
            )
        signals.append(
            _signal(
                "merge_authorization",
                {
                    "auth_mode": "review",
                    "head_sha": authorization.get("head_sha"),
                    "authorized_at": authorization.get("authorized_at"),
                },
                (
                    "per-PR human authorization validated"
                    if not missing and not reasons
                    else "per-PR human authorization rejected"
                ),
            )
        )
        return satisfied, missing, reasons, signals

    if evidence.get("human_authorization") is not None:
        reasons.append(
            "auth_mode auto uses run_authorization, not synthesized "
            "human_authorization"
        )
    authorization = evidence.get("run_authorization")
    if not isinstance(authorization, dict):
        missing.append("run_authorization")
        signals.append(
            _signal(
                "merge_authorization",
                {"auth_mode": "auto", "present": False},
                "run-scoped standing authorization is missing",
            )
        )
        return satisfied, missing, reasons, signals

    for key in [
        "actor",
        "source",
        "repository",
        "run_id",
        "decision",
        "authorized_at",
    ]:
        if not _non_empty_string(authorization.get(key)):
            missing.append(f"run_authorization.{key}")
    if authorization.get("decision") != "authorize_auto_run":
        reasons.append(
            "run_authorization.decision must be authorize_auto_run"
        )
    if authorization.get("repository") != evidence.get("repository"):
        reasons.append(
            "run_authorization.repository must match the gated repository"
        )
    if authorization.get("run_id") != evidence.get("run_id"):
        reasons.append("run_authorization.run_id must match the active run_id")
    authorized_at = _parse_timestamp(authorization.get("authorized_at"))
    if authorized_at is None:
        reasons.append(
            "run_authorization.authorized_at must be a timezone-aware "
            "ISO-8601 timestamp"
        )
    if (
        authorized_at is not None
        and gate_started_at is not None
        and authorized_at > gate_started_at
    ):
        reasons.append(
            "run_authorization.authorized_at must be at or before gate_started_at"
        )
    if not missing and not reasons:
        satisfied.append(
            "auto-mode standing authorization is bound to the repository and run"
        )
    signals.append(
        _signal(
            "merge_authorization",
            {
                "auth_mode": "auto",
                "repository": authorization.get("repository"),
                "run_id": authorization.get("run_id"),
                "authorized_at": authorization.get("authorized_at"),
            },
            (
                "run-scoped standing authorization validated"
                if not missing and not reasons
                else "run-scoped standing authorization rejected"
            ),
        )
    )
    return satisfied, missing, reasons, signals


def evaluate_fastlane_gate(evidence: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the complete reduced evidence set for a fastlane PR."""

    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    signals: list[dict[str, Any]] = []

    if _positive_int(evidence.get("pr")):
        satisfied.append(f"pr: {evidence['pr']}")
    else:
        missing.append("pr")
    if evidence.get("state") != "OPEN":
        reasons.append("PR state must be OPEN")
    else:
        satisfied.append("PR state is OPEN")
    if evidence.get("is_draft") is not False:
        reasons.append("draft PR cannot merge")
    else:
        satisfied.append("PR is not draft")
    if evidence.get("pr_tier") != "fastlane":
        reasons.append("fastlane gate requires pr_tier fastlane")
    else:
        satisfied.append("pr_tier: fastlane")
    tier_evidence = evidence.get("pr_tier_evidence")
    if not isinstance(tier_evidence, dict):
        missing.append("pr_tier_evidence")
    else:
        changed_lines = tier_evidence.get("changed_lines")
        touched_paths = tier_evidence.get("touched_paths")
        if (
            not isinstance(changed_lines, int)
            or isinstance(changed_lines, bool)
            or changed_lines < 0
            or changed_lines > 50
        ):
            reasons.append(
                "pr_tier_evidence.changed_lines must be between 0 and 50"
            )
        if (
            not isinstance(touched_paths, list)
            or not touched_paths
            or not all(_non_empty_string(path) for path in touched_paths)
        ):
            reasons.append(
                "pr_tier_evidence.touched_paths must be a non-empty path list"
            )
    if evidence.get("enforcement_sensitive") is not False:
        reasons.append("fastlane changes must not be enforcement-sensitive")
    protected_paths = evidence.get("protected_paths")
    if not isinstance(protected_paths, list):
        missing.append("protected_paths")
    elif protected_paths:
        reasons.append("fastlane changes must not touch protected paths")

    head_sha = evidence.get("head_sha")
    if not _non_empty_string(head_sha):
        missing.append("head_sha")
    checks_head_sha = evidence.get("checks_head_sha")
    if checks_head_sha != head_sha:
        reasons.append("checks_head_sha must match the current head_sha")
    check_satisfied, check_missing, check_reasons = _check_items(evidence)
    satisfied.extend(check_satisfied)
    missing.extend(check_missing)
    reasons.extend(check_reasons)
    signals.append(
        _signal(
            "ci",
            {
                "head_sha": checks_head_sha,
                "check_count": (
                    len(evidence["checks"])
                    if isinstance(evidence.get("checks"), list)
                    else 0
                ),
            },
            (
                "repository-required CI is green at the exact head"
                if not check_missing and not check_reasons
                and checks_head_sha == head_sha
                else "repository-required CI evidence rejected"
            ),
        )
    )

    focused_tests = evidence.get("focused_tests")
    if not isinstance(focused_tests, dict):
        missing.append("focused_tests")
    else:
        focused_reasons: list[str] = []
        if not _non_empty_string(focused_tests.get("command")):
            focused_reasons.append("focused_tests.command must be a non-empty string")
        if focused_tests.get("passed") is not True:
            focused_reasons.append("focused_tests.passed must be true")
        if focused_tests.get("head_sha") != head_sha:
            focused_reasons.append(
                "focused_tests.head_sha must match the current head_sha"
            )
        if focused_reasons:
            reasons.extend(focused_reasons)
        else:
            satisfied.append("focused tests passed at the exact head")
    signals.append(
        _signal(
            "focused_tests",
            {
                "command": (
                    focused_tests.get("command")
                    if isinstance(focused_tests, dict)
                    else None
                ),
                "head_sha": (
                    focused_tests.get("head_sha")
                    if isinstance(focused_tests, dict)
                    else None
                ),
            },
            (
                "focused tests are green at the exact head"
                if isinstance(focused_tests, dict)
                and _non_empty_string(focused_tests.get("command"))
                and focused_tests.get("passed") is True
                and focused_tests.get("head_sha") == head_sha
                else "focused test evidence rejected"
            ),
        )
    )

    review = evidence.get("independent_review")
    if not isinstance(review, dict):
        missing.append("independent_review")
    else:
        if review.get("review_source") != "independent_lane":
            reasons.append(
                "independent_review.review_source must be independent_lane"
            )
        if review.get("review_execution") != "local":
            reasons.append("independent_review.review_execution must be local")
        if review.get("head_sha") != head_sha:
            reasons.append(
                "independent_review.head_sha must match the current head_sha"
            )
        if review.get("status") != "completed":
            reasons.append("independent_review.status must be completed")
        if review.get("verdict") not in MERGE_READY_VERDICTS:
            reasons.append(
                "independent_review.verdict must be clean or non_blocking"
            )
        tier_attestation = review.get("tier_attestation")
        if not isinstance(tier_attestation, dict):
            missing.append("independent_review.tier_attestation")
        elif (
            tier_attestation.get("pr_tier") != "fastlane"
            or tier_attestation.get("attested") is not True
            or not _non_empty_string(tier_attestation.get("basis"))
        ):
            reasons.append(
                "independent_review.tier_attestation must independently "
                "attest fastlane eligibility"
            )
        if _parse_timestamp(review.get("review_completed_at")) is None:
            reasons.append(
                "independent_review.review_completed_at must be a "
                "timezone-aware ISO-8601 timestamp"
            )
        evidence = {
            **evidence,
            "review_completed_at": review.get("review_completed_at"),
        }
    signals.append(
        _signal(
            "independent_review",
            {
                "head_sha": (
                    review.get("head_sha") if isinstance(review, dict) else None
                ),
                "review_source": (
                    review.get("review_source")
                    if isinstance(review, dict)
                    else None
                ),
                "verdict": (
                    review.get("verdict") if isinstance(review, dict) else None
                ),
            },
            (
                "independent exact-head review is merge-ready"
                if isinstance(review, dict)
                and review.get("head_sha") == head_sha
                and review.get("review_source") == "independent_lane"
                and review.get("review_execution") == "local"
                and review.get("status") == "completed"
                and review.get("verdict") in MERGE_READY_VERDICTS
                else "independent exact-head review evidence rejected"
            ),
        )
    )
    tier_attestation = (
        review.get("tier_attestation") if isinstance(review, dict) else None
    )
    signals.append(
        _signal(
            "tier_eligibility",
            {
                "changed_lines": (
                    tier_evidence.get("changed_lines")
                    if isinstance(tier_evidence, dict)
                    else None
                ),
                "touched_paths": (
                    tier_evidence.get("touched_paths")
                    if isinstance(tier_evidence, dict)
                    else None
                ),
                "enforcement_sensitive": evidence.get("enforcement_sensitive"),
                "protected_paths": protected_paths,
                "reviewer_attested": (
                    tier_attestation.get("attested")
                    if isinstance(tier_attestation, dict)
                    else None
                ),
            },
            (
                "fastlane eligibility is independently substantiated"
                if isinstance(tier_evidence, dict)
                and isinstance(tier_evidence.get("changed_lines"), int)
                and not isinstance(tier_evidence.get("changed_lines"), bool)
                and 0 <= tier_evidence["changed_lines"] <= 50
                and isinstance(tier_evidence.get("touched_paths"), list)
                and bool(tier_evidence["touched_paths"])
                and all(
                    _non_empty_string(path)
                    for path in tier_evidence["touched_paths"]
                )
                and evidence.get("enforcement_sensitive") is False
                and protected_paths == []
                and isinstance(tier_attestation, dict)
                and tier_attestation.get("pr_tier") == "fastlane"
                and tier_attestation.get("attested") is True
                and _non_empty_string(tier_attestation.get("basis"))
                else "fastlane eligibility evidence rejected"
            ),
        )
    )

    merge_state = evidence.get("merge_state")
    if merge_state != "CLEAN":
        reasons.append("merge_state must be CLEAN")
    else:
        satisfied.append("merge_state: CLEAN")
    signals.append(
        _signal(
            "merge_state",
            {"merge_state": merge_state},
            (
                "merge state is clean"
                if merge_state == "CLEAN"
                else "merge state is not clean"
            ),
        )
    )

    auth_satisfied, auth_missing, auth_reasons, auth_signals = (
        evaluate_merge_authorization(evidence)
    )
    satisfied.extend(auth_satisfied)
    missing.extend(auth_missing)
    reasons.extend(auth_reasons)
    signals.extend(auth_signals)

    deterministic_missing = [
        item
        for item in missing
        if not item.startswith("human_authorization")
    ]
    if reasons or deterministic_missing:
        decision = "blocked"
    elif any(item.startswith("human_authorization") for item in missing):
        decision = "needs_human"
    else:
        decision = "allowed"
    items = [
        *(item_from_missing(item) for item in missing),
        *(item_from_reason(item, "invalid_evidence_value") for item in reasons),
    ]
    return {
        "decision": decision,
        "pr": evidence.get("pr"),
        "head_sha": evidence.get("head_sha"),
        "pr_tier": evidence.get("pr_tier"),
        "auth_mode": evidence.get("auth_mode", "review"),
        "reasons": sorted(set(reasons)),
        "satisfied": sorted(set(satisfied)),
        "missing": sorted(set(missing)),
        "signals": signals,
        "rejection_items": (
            [] if decision == "allowed" else finalize_items(items)
        ),
        "blocked_actions": [] if decision == "allowed" else ["merge"],
    }


def _load_evidence(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read evidence file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid evidence JSON {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("fastlane evidence must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the deterministic fastlane merge gate."
    )
    parser.add_argument("--repo", default=".", help="SpecRail repository root")
    parser.add_argument("--evidence", required=True, help="Fastlane evidence JSON")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args()
    try:
        repo = Path(args.repo).resolve()
        evidence = _load_evidence(Path(args.evidence))
        schema = load_json_schema(
            repo / "schemas" / "fastlane_gate_evidence.schema.json"
        )
        validate_instance(schema, evidence, "fastlane_gate_evidence")
        result = evaluate_fastlane_gate(evidence)
    except (SpecRailError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"decision: {result['decision']}")
        for reason in result["reasons"]:
            print(f"- {reason}")
        for item in result["missing"]:
            print(f"- missing: {item}")
    return 0 if result["decision"] == "allowed" else 1


if __name__ == "__main__":
    sys.exit(main())
