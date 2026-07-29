#!/usr/bin/env python3
"""Evaluate compact, current-head PR merge-readiness evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from checks_availability import evaluate_checks_unavailable
from github_evidence_common import EvidenceError, combine_review_findings
from github_pr_evidence import parse_github_repo
from rejection_items import (
    add_prior_rejection_argument,
    apply_prior_rejection,
    finalize_items,
    item_from_reason,
    items_from_legacy,
    validate_review_attestation,
)
from review_json_gate import evaluate_review_gate
from sensitive_enforcement import classify_sensitive_changes, sensitive_registry
from specrail_lib import (
    PackConfig,
    SpecRailError,
    ci_component_coverage,
    load_pack,
    resolve_path,
    spec_packet_artifact_paths,
    validate_verification_profiles,
    verification_profiles,
)


CONTRACT_VERSION = 3
PROFILES = {"fastlane", "standard", "heavy"}
CLEAN_MERGE_STATES = {"CLEAN"}
SUCCESS_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
EVIDENCE_KEYS = {
    "base_ref",
    "base_sha",
    "changed_files",
    "changed_files_count",
    "changed_files_sha256",
    "checks",
    "checks_unavailable",
    "contract_version",
    "default_base_ref",
    "enforcement_sensitive",
    "gate_invocation_id",
    "gate_query_head_sha",
    "head_sha",
    "human_merge_authorization",
    "hosted_findings",
    "is_draft",
    "linked_issue",
    "merge_state",
    "pr",
    "profile",
    "prior_review_boundary",
    "repository",
    "review",
    "review_attestation",
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
NON_HUMAN_ACTORS = {
    "agent",
    "automation",
    "codex",
    "dependabot",
    "github-actions",
    "renovate",
    "self",
}
DEFAULT_PROFILE_POLICIES = {
    "fastlane": {
        "max_review_rounds": 1,
        "merge_authorization": "invocation",
    },
    "standard": {
        "max_review_rounds": 2,
        "merge_authorization": "invocation",
    },
    "heavy": {
        "max_review_rounds": 2,
        "merge_authorization": "explicit_human",
    },
}


def _profile_policy(
    config: PackConfig | None,
    profile: object,
) -> tuple[dict[str, Any], list[str]]:
    fallback = DEFAULT_PROFILE_POLICIES.get(str(profile), {})
    if config is None:
        return fallback, []
    if "verification_profiles" not in config.workflow:
        return fallback, []
    validation_errors = validate_verification_profiles(config)
    if validation_errors:
        return fallback, validation_errors
    try:
        _default, profiles = verification_profiles(config)
    except SpecRailError as exc:
        return fallback, [str(exc)]
    if str(profile) not in profiles:
        return fallback, [
            f"workflow.yaml: verification profile {profile!r} is not configured"
        ]
    return profiles[str(profile)], []


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


def _validate_checks(
    evidence: dict[str, Any],
    required_check_names: set[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return satisfied, ["checks"], reasons
    if not checks:
        return evaluate_checks_unavailable(evidence)
    if "checks_unavailable" in evidence:
        reasons.append(
            "checks_unavailable must not be present when checks are available"
        )
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
        if "url" in check and not _non_empty_string(check.get("url")):
            reasons.append(f"{prefix} url must be a non-empty string")
        if check.get("head_sha") != evidence.get("head_sha"):
            reasons.append(f"{prefix} head_sha must match the gated head")
        if check.get("status") != "COMPLETED":
            reasons.append(f"{prefix} status must be COMPLETED")
        if check.get("conclusion") not in SUCCESS_CONCLUSIONS:
            reasons.append(f"{prefix} conclusion is not successful")
    absent_checks = sorted((required_check_names or set()) - names)
    if absent_checks:
        reasons.append(
            "configured CI checks are missing: " + ", ".join(absent_checks)
        )
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
    linked_issue = evidence.get("linked_issue")
    spec_refs: list[str] = []
    if _positive_int(linked_issue) and sensitive_registry(config)["specs"]:
        packet = spec_packet_artifact_paths(config, int(linked_issue))
        spec_refs = [
            packet[name]
            for name in ("product_spec", "tech_spec", "task_plan")
        ]
    try:
        classification = classify_sensitive_changes(
            config,
            repo,
            paths,
            spec_refs,
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
    actor = authorization.get("actor")
    if _non_empty_string(actor):
        normalized_actor = str(actor).strip().casefold()
        if (
            normalized_actor in NON_HUMAN_ACTORS
            or normalized_actor.endswith("[bot]")
            or re.search(r"(?:^|[-_])(agent|automation|bot)$", normalized_actor)
        ):
            reasons.append("human_merge_authorization.actor must identify a human")
    authorized_at = authorization.get("authorized_at")
    if _non_empty_string(authorized_at):
        authorized_at_text = str(authorized_at)
        try:
            parsed_at = datetime.fromisoformat(
                authorized_at_text.replace("Z", "+00:00")
            )
        except ValueError:
            parsed_at = None
        if (
            authorized_at_text != authorized_at_text.strip()
            or parsed_at is None
            or parsed_at.tzinfo is None
            or parsed_at.utcoffset() is None
        ):
            reasons.append(
                "human_merge_authorization.authorized_at must be a valid "
                "timezone-aware timestamp"
            )
    if authorization.get("head_sha") != evidence.get("head_sha"):
        reasons.append("human_merge_authorization.head_sha must match the gated head")
    if authorization.get("invocation_id") != evidence.get("gate_invocation_id"):
        reasons.append(
            "human_merge_authorization.invocation_id must match the current gate invocation"
        )
    if required and not reasons and not missing:
        # This current-conversation input is invocation-bound evidence, never
        # persisted or reusable final merge authority; this gate stays advisory.
        satisfied.append("current-invocation human merge authorization validated")
    return satisfied, missing, reasons


def _review_diff(
    review: dict[str, Any],
    pr_base_sha: object,
    repo: Path | None,
) -> tuple[str, bytes | None, list[str]]:
    review_round = review.get("round")
    if review_round not in {1, 2}:
        return "", None, []
    if repo is None:
        return "", None, ["review requires an exact local checkout"]
    base = review.get("base_head_sha")
    head = review.get("head_sha")
    if not isinstance(base, str) or not SHA_RE.fullmatch(base):
        return "", None, []
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        return "", None, []
    if review_round == 1 and base != pr_base_sha:
        return "", None, [
            "round 1 review.base_head_sha must match PR evidence base_sha"
        ]
    prior_review = review.get("prior_review")
    if (
        review_round == 2
        and isinstance(prior_review, dict)
        and prior_review.get("base_head_sha") != pr_base_sha
    ):
        return "", None, [
            "round 2 prior_review.base_head_sha must match PR evidence base_sha"
        ]
    try:
        diff_range = f"{base}...{head}" if review_round == 1 else f"{base}..{head}"
        completed = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary", diff_range, "--"],
            cwd=repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return "", None, [f"cannot execute exact review diff: {exc}"]
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        return "", None, [f"exact review diff failed: {detail}"]
    return (
        completed.stdout.decode("utf-8", errors="replace"),
        completed.stdout,
        [],
    )


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
        legacy_reason = (
            "unsupported legacy evidence fields: "
            + ", ".join(unsupported)
            + "; rebuild evidence from GitHub PR current state"
        )
        return {
            "decision": "blocked",
            "pr": evidence.get("pr"),
            "linked_issue": evidence.get("linked_issue"),
            "head_sha": evidence.get("head_sha"),
            "profile": evidence.get("profile"),
            "enforcement_sensitive": evidence.get("enforcement_sensitive"),
            "sensitive_classification": evidence.get("sensitive_classification"),
            "review_decision": None,
            "unsupported_legacy_evidence": unsupported,
            "reasons": [legacy_reason],
            "satisfied": [],
            "missing": [],
            "rejection_items": finalize_items(
                items_from_legacy(
                    [],
                    [legacy_reason],
                    missing_category="missing_evidence_field",
                    reason_category="contract_violation",
                )
            ),
            "blocked_actions": ["merge"],
            "advisory_only": True,
            "verification_commands": [
                "python3 checks/pr_gate.py --repo . --evidence <evidence.json>",
                "python3 checks/check_workflow.py --repo .",
            ],
        }

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
    repository = evidence.get("repository")
    if _non_empty_string(repository):
        try:
            parse_github_repo(str(repository))
        except EvidenceError as exc:
            reasons.append(str(exc))
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
    if repo is not None:
        checkout_head = _current_checkout_head(repo)
        if checkout_head is None:
            reasons.append("PR gate requires a readable local checkout HEAD")
        elif checkout_head != evidence.get("head_sha"):
            reasons.append("PR gate requires an exact current-head checkout")

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

    if config is None and repo is not None:
        try:
            config = load_pack(resolve_path(repo, label="repository"))
        except SpecRailError as exc:
            reasons.append(str(exc))
    required_check_names: set[str] = set()
    if config is not None:
        try:
            required_check_names = set(ci_component_coverage(config))
        except SpecRailError as exc:
            reasons.append(str(exc))
    ci_satisfied, ci_missing, ci_reasons = _validate_checks(
        evidence,
        required_check_names,
    )
    satisfied.extend(ci_satisfied)
    missing.extend(ci_missing)
    reasons.extend(ci_reasons)
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
    if profile == "fastlane" and "review_attestation" in evidence:
        reasons.append("fastlane must not include review_attestation")
    if sensitive and profile != "heavy":
        reasons.append("sensitive changes must use the heavy profile")
    profile_policy, profile_policy_reasons = _profile_policy(config, profile)
    reasons.extend(profile_policy_reasons)

    review = evidence.get("review")
    review_result: dict[str, Any] | None = None
    if isinstance(review, dict):
        independent_required = profile_policy.get("requires_independent_review")
        att_missing, att_reasons = validate_review_attestation(
            review,
            evidence.get("review_attestation"),
            gate_invocation_id=evidence.get("gate_invocation_id"),
            required=(
                independent_required
                if isinstance(independent_required, bool)
                else profile in {"standard", "heavy"}
            ),
        )
        missing.extend(f"review: {field}" for field in att_missing)
        reasons.extend(f"review: {reason}" for reason in att_reasons)
        boundary = evidence.get("prior_review_boundary")
        if "prior_review_boundary" in evidence and not _non_empty_string(boundary):
            reasons.append("prior_review_boundary must be a non-empty string")
        try:
            semantic_review = combine_review_findings(
                review,
                evidence.get("hosted_findings", []),
                prior_review_boundary=(
                    str(boundary) if _non_empty_string(boundary) else None
                ),
            )
        except EvidenceError as exc:
            reasons.append(str(exc))
            semantic_review = review
        review_diff, review_diff_bytes, review_diff_reasons = _review_diff(
            semantic_review,
            evidence.get("base_sha"),
            repo,
        )
        reasons.extend(review_diff_reasons)
        review_result = evaluate_review_gate(
            semantic_review,
            review_diff,
            repo=repo,
            diff_bytes=review_diff_bytes,
            verify_diff=True,
            max_review_rounds=profile_policy.get("max_review_rounds"),
            requires_independent_review=profile_policy.get(
                "requires_independent_review"
            ),
            gate_invocation_id=evidence.get("gate_invocation_id"),
            _attestation_validated=True,
        )
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

    authorization_required = (
        profile_policy.get("merge_authorization") == "explicit_human"
    )
    auth_satisfied, auth_missing, auth_reasons = _validate_authorization(
        evidence,
        required=authorization_required,
    )
    satisfied.extend(auth_satisfied)
    missing.extend(auth_missing)
    reasons.extend(auth_reasons)

    deterministic_missing = [
        item
        for item in missing
        if not item.startswith("human_merge_authorization")
        and item != "human_review"
    ]
    blocking_reasons = [
        reason
        for reason in reasons
        if not authorization_required or reason not in auth_reasons
    ]
    if blocking_reasons or deterministic_missing:
        decision = "blocked"
    elif missing or (authorization_required and auth_reasons):
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
