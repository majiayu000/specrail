#!/usr/bin/env python3
"""Evaluate compact, current-head PR merge-readiness evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from rejection_items import (
    add_prior_rejection_argument,
    apply_prior_rejection,
    finalize_items,
    item_from_reason,
    items_from_legacy,
)
from review_json_gate import evaluate_review_gate
from sensitive_enforcement import classify_sensitive_changes
from specrail_lib import PackConfig, SpecRailError, load_pack, resolve_path


CONTRACT_VERSION = 3
PROFILES = {"fastlane", "standard", "heavy"}
CLEAN_MERGE_STATES = {"CLEAN"}
SUCCESS_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
EVIDENCE_KEYS = {
    "base_sha",
    "changed_files",
    "changed_files_count",
    "changed_files_sha256",
    "checks",
    "contract_version",
    "enforcement_sensitive",
    "gate_invocation_id",
    "gate_query_head_sha",
    "head_sha",
    "human_merge_authorization",
    "is_draft",
    "linked_issue",
    "merge_state",
    "pr",
    "profile",
    "repository",
    "review",
    "sensitive_classification",
    "state",
}
LEGACY_EVIDENCE_FIELDS = {
    "approved_spec",
    "content_binding_version",
    "content_hashes",
    "gate_started_at",
    "human_authorization",
    "issue_reference",
    "lane_failures",
    "merge_dispatched_at",
    "merge_head_sha",
    "pr_tier",
    "pr_tier_evidence",
    "reused_components",
    "review_completed_at",
    "review_evidence",
    "review_execution",
    "review_source",
    "review_threads",
    "reviews",
    "round_cap_authorizations",
    "runtime_checkpoint",
    "self_review_authorization",
    "sensitive_route",
    "snapshot",
    "spec_approval",
    "tier_attestation",
    "tier_dispute",
}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read evidence file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid evidence JSON {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("evidence JSON must be an object")
    return value


def _current_checkout_head(repo: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _changed_files_digest(paths: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(paths, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_checks(checks: Any, head_sha: Any) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    if not isinstance(checks, list) or not checks:
        return satisfied, ["checks"], reasons
    names: set[str] = set()
    for index, check in enumerate(checks, start=1):
        prefix = f"check #{index}"
        if not isinstance(check, dict):
            reasons.append(f"{prefix} must be an object")
            continue
        unknown = sorted(set(check) - {"name", "status", "conclusion", "head_sha", "url"})
        if unknown:
            reasons.append(f"{prefix} contains unsupported fields: {', '.join(unknown)}")
        name = check.get("name")
        if not _non_empty_string(name):
            reasons.append(f"{prefix} name must be a non-empty string")
        elif str(name) in names:
            reasons.append(f"duplicate CI check name: {name}")
        else:
            names.add(str(name))
        if check.get("head_sha") != head_sha:
            reasons.append(f"{prefix} head_sha must match the gated head")
        if check.get("status") != "COMPLETED":
            reasons.append(f"{prefix} status must be COMPLETED")
        if check.get("conclusion") not in SUCCESS_CONCLUSIONS:
            reasons.append(f"{prefix} conclusion is not successful")
    if not reasons:
        satisfied.append(f"{len(checks)} current-head CI checks passed")
    return satisfied, missing, reasons


def _validate_sensitive(
    evidence: dict[str, Any],
    *,
    repo: Path | None,
    config: PackConfig | None,
) -> tuple[bool, dict[str, Any] | None, list[str], list[str]]:
    satisfied: list[str] = []
    reasons: list[str] = []
    reported = evidence.get("sensitive_classification")
    if repo is None or config is None:
        if evidence.get("enforcement_sensitive") is True:
            reasons.append("heavy evidence requires repository-owned sensitive classification")
        return bool(evidence.get("enforcement_sensitive")), None, satisfied, reasons
    paths = evidence.get("changed_files")
    if not isinstance(paths, list):
        reasons.append("changed_files must be an array")
        return False, None, satisfied, reasons
    try:
        classification = classify_sensitive_changes(
            config,
            repo,
            paths,
            paths,
            source="github_changed_files",
        )
    except SpecRailError as exc:
        reasons.append(str(exc))
        return False, None, satisfied, reasons
    computed = bool(classification["enforcement_sensitive"])
    if reported != classification:
        reasons.append(
            "sensitive_classification conflicts with repository registry calculation"
        )
    if evidence.get("enforcement_sensitive") is not computed:
        reasons.append("enforcement_sensitive conflicts with repository sensitive registry")
    if computed:
        satisfied.append("sensitive paths classified as heavy")
        checkout_head = _current_checkout_head(repo)
        if checkout_head != evidence.get("head_sha"):
            reasons.append("sensitive PR gate requires an exact current-head checkout")
    else:
        satisfied.append("changed files do not match the sensitive registry")
    return computed, classification, satisfied, reasons


def _validate_authorization(
    evidence: dict[str, Any],
    *,
    required: bool,
) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    authorization = evidence.get("human_merge_authorization")
    if authorization is None:
        if required:
            missing.append("human_merge_authorization")
        return satisfied, missing, reasons
    if not isinstance(authorization, dict):
        return satisfied, missing, ["human_merge_authorization must be an object"]
    required_fields = {"actor", "authorized_at", "head_sha", "invocation_id"}
    unknown = sorted(set(authorization) - required_fields)
    absent = sorted(required_fields - set(authorization))
    if unknown:
        reasons.append(
            "human_merge_authorization contains unsupported fields: "
            + ", ".join(unknown)
        )
    missing.extend(f"human_merge_authorization.{field}" for field in absent)
    for field in ("actor", "authorized_at", "invocation_id"):
        if field in authorization and not _non_empty_string(authorization.get(field)):
            reasons.append(f"human_merge_authorization.{field} must be non-empty")
    if authorization.get("head_sha") != evidence.get("head_sha"):
        reasons.append("human_merge_authorization.head_sha must match the gated head")
    if authorization.get("invocation_id") != evidence.get("gate_invocation_id"):
        reasons.append(
            "human_merge_authorization.invocation_id must match the current gate invocation"
        )
    if not reasons and not missing:
        satisfied.append("current-invocation human merge authorization validated")
    return satisfied, missing, reasons


def evaluate_pr_gate(
    evidence: dict[str, Any],
    repo: Path | None = None,
    config: PackConfig | None = None,
) -> dict[str, Any]:
    """Evaluate all compact PR evidence without granting merge authority."""

    reasons: list[str] = []
    missing: list[str] = []
    satisfied: list[str] = []
    unsupported: list[str] = []
    for key in sorted(set(evidence) - EVIDENCE_KEYS):
        if key in LEGACY_EVIDENCE_FIELDS:
            unsupported.append(key)
        else:
            reasons.append(f"unknown PR evidence field: {key}")
    if unsupported:
        reasons.append(
            "unsupported legacy evidence fields: " + ", ".join(unsupported)
        )

    required = {
        "base_sha",
        "changed_files",
        "changed_files_count",
        "changed_files_sha256",
        "checks",
        "contract_version",
        "enforcement_sensitive",
        "gate_invocation_id",
        "gate_query_head_sha",
        "head_sha",
        "is_draft",
        "linked_issue",
        "merge_state",
        "pr",
        "profile",
        "repository",
        "review",
        "sensitive_classification",
        "state",
    }
    missing.extend(sorted(required - set(evidence)))
    if evidence.get("contract_version") != CONTRACT_VERSION:
        reasons.append(
            f"contract_version must be {CONTRACT_VERSION}; rebuild evidence from GitHub"
        )
    for field in ("repository", "gate_invocation_id"):
        if field in evidence and not _non_empty_string(evidence.get(field)):
            reasons.append(f"{field} must be a non-empty string")
    for field in ("pr", "linked_issue"):
        if field in evidence and not _positive_int(evidence.get(field)):
            reasons.append(f"{field} must be a positive integer")
    for field in ("base_sha", "head_sha", "gate_query_head_sha"):
        if field in evidence and (
            not isinstance(evidence.get(field), str)
            or not SHA_RE.fullmatch(str(evidence.get(field)))
        ):
            reasons.append(f"{field} must be a 40-character Git SHA")
    if (
        "head_sha" in evidence
        and "gate_query_head_sha" in evidence
        and evidence.get("head_sha") != evidence.get("gate_query_head_sha")
    ):
        reasons.append("gate_query_head_sha must match the gated head")

    if str(evidence.get("state") or "").upper() != "OPEN":
        reasons.append(f"PR state must be OPEN; got {evidence.get('state')!r}")
    if evidence.get("is_draft") is not False:
        reasons.append("draft PR cannot merge")
    if str(evidence.get("merge_state") or "").upper() not in CLEAN_MERGE_STATES:
        reasons.append(f"merge_state must be CLEAN; got {evidence.get('merge_state')!r}")

    changed_files = evidence.get("changed_files")
    if isinstance(changed_files, list) and all(
        _non_empty_string(path) for path in changed_files
    ):
        normalized = sorted(str(path) for path in changed_files)
        if normalized != changed_files or len(set(normalized)) != len(normalized):
            reasons.append("changed_files must be sorted and unique")
        if evidence.get("changed_files_count") != len(normalized):
            reasons.append("changed_files_count does not match changed_files")
        if evidence.get("changed_files_sha256") != _changed_files_digest(normalized):
            reasons.append("changed_files_sha256 does not match changed_files")
    elif "changed_files" in evidence:
        reasons.append("changed_files must contain non-empty path strings")

    ci_satisfied, ci_missing, ci_reasons = _validate_checks(
        evidence.get("checks"), evidence.get("head_sha")
    )
    satisfied.extend(ci_satisfied)
    missing.extend(ci_missing)
    reasons.extend(ci_reasons)

    if config is None and repo is not None:
        try:
            config = load_pack(resolve_path(repo, label="repository"))
        except SpecRailError as exc:
            reasons.append(str(exc))
    sensitive, classification, sensitive_satisfied, sensitive_reasons = _validate_sensitive(
        evidence,
        repo=repo,
        config=config,
    )
    satisfied.extend(sensitive_satisfied)
    reasons.extend(sensitive_reasons)

    profile = evidence.get("profile")
    if profile not in PROFILES:
        reasons.append("profile must be fastlane, standard, or heavy")
    if sensitive and profile != "heavy":
        reasons.append("sensitive changes must use the heavy profile")

    review = evidence.get("review")
    review_result: dict[str, Any] | None = None
    if isinstance(review, dict):
        review_result = evaluate_review_gate(review, "", verify_diff=False)
        if review.get("repository") != evidence.get("repository"):
            reasons.append("review.repository must match PR evidence")
        if review.get("pr") != evidence.get("pr"):
            reasons.append("review.pr must match PR evidence")
        if review.get("head_sha") != evidence.get("head_sha"):
            reasons.append("review.head_sha must match the gated head")
        if review.get("profile") != profile:
            reasons.append("review.profile must match PR evidence")
        if review_result["decision"] == "blocked":
            reasons.extend(
                f"review: {reason}"
                for reason in [*review_result["missing"], *review_result["reasons"]]
            )
            if review_result["blocking_findings"]:
                reasons.append(
                    "current unresolved P0/P1 findings: "
                    + ", ".join(review_result["blocking_findings"])
                )
        elif review_result["decision"] == "needs_human":
            missing.append("human_review")
        else:
            satisfied.append("compact current-head review passed")
    elif "review" in evidence:
        reasons.append("review must be an object")

    auth_satisfied, auth_missing, auth_reasons = _validate_authorization(
        evidence,
        required=profile == "heavy",
    )
    satisfied.extend(auth_satisfied)
    missing.extend(auth_missing)
    reasons.extend(auth_reasons)

    deterministic_missing = [
        item
        for item in missing
        if item not in {"human_merge_authorization", "human_review"}
    ]
    if reasons or deterministic_missing:
        decision = "blocked"
    elif missing:
        decision = "needs_human"
    else:
        decision = "allowed"
    rejection_items = (
        []
        if decision == "allowed"
        else finalize_items(
            items_from_legacy(
                sorted(set(missing)),
                sorted(set(reasons)),
                missing_category="missing_evidence_field",
                reason_category="contract_violation",
            )
        )
    )
    return {
        "decision": decision,
        "pr": evidence.get("pr"),
        "linked_issue": evidence.get("linked_issue"),
        "head_sha": evidence.get("head_sha"),
        "profile": profile,
        "enforcement_sensitive": sensitive,
        "sensitive_classification": classification,
        "review_decision": review_result.get("decision") if review_result else None,
        "unsupported_legacy_evidence": unsupported,
        "reasons": sorted(set(reasons)),
        "satisfied": sorted(set(satisfied)),
        "missing": sorted(set(missing)),
        "rejection_items": rejection_items,
        "blocked_actions": [] if decision == "allowed" else ["merge"],
        "advisory_only": True,
        "verification_commands": [
            "python3 checks/pr_gate.py --repo . --evidence <evidence.json>",
            "python3 checks/check_workflow.py --repo .",
        ],
    }


def print_gate_human(result: dict[str, Any]) -> None:
    print(f"decision: {result['decision']}")
    for name in ("reasons", "missing"):
        if result[name]:
            print(f"{name}:")
            for item in result[name]:
                print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate compact SpecRail PR evidence without writing GitHub state."
    )
    parser.add_argument("--repo", default=".", help="Repository checkout")
    parser.add_argument("--evidence", required=True, help="PR evidence JSON")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    add_prior_rejection_argument(parser)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        result = evaluate_pr_gate(
            _load_json(Path(args.evidence) if Path(args.evidence).is_absolute() else repo / args.evidence),
            repo,
        )
    except (ValueError, SpecRailError) as exc:
        result = {
            "decision": "blocked",
            "reasons": [str(exc)],
            "missing": [],
            "rejection_items": finalize_items(
                [item_from_reason(str(exc), "config_error")]
            ),
            "blocked_actions": ["merge"],
            "advisory_only": True,
        }
    result = apply_prior_rejection(
        result,
        args.prior_rejection,
        blocked_actions=["merge"],
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_gate_human(result)
    return 0 if result["decision"] == "allowed" else 1


if __name__ == "__main__":
    sys.exit(main())
