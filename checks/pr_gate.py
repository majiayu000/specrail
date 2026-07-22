#!/usr/bin/env python3
"""Evaluate deterministic PR merge-readiness evidence.

The gate is intentionally offline. GitHub or threads adapters may collect the
evidence JSON, but this script only evaluates it and never writes remote state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evidence_content_binding import (
    content_bindings_match,
    validate_component_binding,
    validate_content_binding,
)
from github_evidence_common import EvidenceError
from pr_review_contract import evaluate_review_contract_with_items
from review_result_semantics import evaluate_review_evidence
from rejection_items import (
    add_prior_rejection_argument,
    apply_prior_rejection,
    finalize_items,
    item_from_missing,
    item_from_reason,
    items_from_legacy,
)
from runtime_tier_authorization import (
    AUTHORIZATION_TIERS,
    STANDARD_AUTO_TIERS,
    _valid_pr_tier_evidence,
)
from sensitive_enforcement import (
    evaluate_sensitive_evidence_with_items,
    sensitive_registry,
)
from specrail_lib import PackConfig, SpecRailError, load_pack, resolve_path


CHECK_PASS_CONCLUSIONS = {"SUCCESS"}
CLEAN_MERGE_STATES = {"CLEAN"}
MERGE_PATHS = {"gh_pr_merge", "api_fallback", "merged_by_other"}


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read evidence file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid evidence JSON {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("evidence JSON must be an object")
    return data


def _binding_payload(evidence: dict[str, Any]) -> dict[str, Any] | None:
    keys = ["content_binding_version", "snapshot", "content_hashes"]
    if not any(key in evidence for key in keys):
        return None
    return {key: evidence.get(key) for key in keys}


def _reusable_components(evidence: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    components: list[tuple[str, dict[str, Any]]] = []
    checks = evidence.get("checks")
    if isinstance(checks, list):
        components.extend(
            ("CI check", item) for item in checks if isinstance(item, dict)
        )
    review = evidence.get("review_evidence")
    artifacts = review.get("artifacts") if isinstance(review, dict) else None
    current_ids = review.get("current_artifact_ids") if isinstance(review, dict) else None
    if isinstance(artifacts, list):
        components.extend(
            ("review artifact", item)
            for item in artifacts
            if isinstance(item, dict)
            and isinstance(current_ids, list)
            and item.get("artifact_id") in current_ids
        )
    return components


def _content_binding_items(
    evidence: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Validate v1 components and their complete previous-head reuse audit."""

    payload = _binding_payload(evidence)
    audits = evidence.get("reused_components")
    components = _reusable_components(evidence)
    versioned_components = [
        (kind, item)
        for kind, item in components
        if any(
            key in item
            for key in [
                "content_binding_version",
                "covered_categories",
                "content_bindings",
            ]
        )
    ]
    if payload is None and not versioned_components and audits is None:
        return ["legacy component evidence uses current exact-head wrapper"], [], []
    if payload is None:
        return [], ["content_binding"], ["v1 component reuse requires current content binding"]
    try:
        current = validate_content_binding(payload)
    except EvidenceError as exc:
        return [], [], [f"current content binding is invalid: {exc}"]
    reasons: list[str] = []
    satisfied: list[str] = []
    if current["snapshot"]["head_sha"] != evidence.get("head_sha"):
        reasons.append("current content binding snapshot.head_sha must match head_sha")
    if not isinstance(audits, list):
        return satisfied, ["reused_components"], [
            *reasons,
            "v1 current wrapper requires reused_components audit list",
        ]

    audit_by_id: dict[str, dict[str, Any]] = {}
    for index, audit in enumerate(audits):
        if not isinstance(audit, dict):
            reasons.append(f"reused_components[{index}] must be an object")
            continue
        artifact_id = audit.get("artifact_id")
        if not _non_empty_string(artifact_id):
            reasons.append(f"reused_components[{index}].artifact_id must be non-empty")
        elif artifact_id in audit_by_id:
            reasons.append(f"duplicate reused component audit: {artifact_id}")
        else:
            audit_by_id[str(artifact_id)] = audit

    expected_reused: set[str] = set()
    for kind, component in components:
        component_id = component.get("artifact_id")
        component_head = component.get("head_sha")
        versioned = any(
            key in component
            for key in [
                "content_binding_version",
                "covered_categories",
                "content_bindings",
            ]
        )
        if not versioned:
            if _non_empty_string(component_head) and component_head != evidence.get("head_sha"):
                reasons.append(f"legacy {kind} head_sha must match current head")
            continue
        try:
            covered, original = validate_component_binding(component)
            matches = content_bindings_match(component, current["content_hashes"])
        except EvidenceError as exc:
            reasons.append(f"{kind} content binding is invalid: {exc}")
            continue
        if not matches:
            reasons.append(f"{kind} covered content bindings do not match current snapshot")
            continue
        if component_head is None or component_head == evidence.get("head_sha"):
            satisfied.append(f"current-head {kind} content bindings validated")
            continue
        if not _non_empty_string(component_head):
            reasons.append(f"reused {kind} head_sha must be non-empty")
            continue
        if not _non_empty_string(component_id):
            reasons.append(f"reused {kind} artifact_id must be non-empty")
            continue
        expected_reused.add(str(component_id))
        audit = audit_by_id.get(str(component_id))
        if audit is None:
            reasons.append(f"reused {kind} lacks audit: {component_id}")
            continue
        expected_current = {
            category: current["content_hashes"][category] for category in covered
        }
        expected = {
            "original_head_sha": component_head,
            "covered_categories": list(covered),
            "original_content_bindings": original,
            "current_content_bindings": expected_current,
            "collector_provenance": current["snapshot"],
        }
        for key, value in expected.items():
            if audit.get(key) != value:
                reasons.append(f"reused component audit {component_id}.{key} is invalid")
        if not _non_empty_string(audit.get("reason")):
            reasons.append(f"reused component audit {component_id}.reason must be non-empty")
        satisfied.append(f"reused {kind} coverage matched: {component_id}")
    extra = sorted(set(audit_by_id) - expected_reused)
    if extra:
        reasons.append("reused_components contains non-reused or unknown artifacts: " + ", ".join(extra))
    return satisfied, [], reasons


def _check_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        missing.append("checks")
        reasons.append("CI/check evidence is missing")
        return satisfied, missing, reasons

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


def _tier_substantiation_reference(evidence: dict[str, Any]) -> str | None:
    """GH-143 defense in depth: standard_auto needs an independent reference.

    Self-reported pr_tier_evidence alone never satisfies the authorization
    item; the evidence must also reference independent substantiation —
    either a ci_tier_check artifact reference or a tier_attestation_ref
    pointing at review evidence whose review_source is independent_lane.
    """
    ci_tier_check = evidence.get("ci_tier_check")
    if isinstance(ci_tier_check, dict) and _non_empty_string(
        ci_tier_check.get("evidence")
    ):
        return "ci_tier_check artifact reference"
    if _non_empty_string(evidence.get("tier_attestation_ref")):
        review_evidence = evidence.get("review_evidence")
        review_source = (
            review_evidence.get("review_source")
            if isinstance(review_evidence, dict)
            else None
        )
        if review_source == "independent_lane":
            return "tier_attestation_ref backed by independent_lane review evidence"
    return None


def _authorization_item(
    evidence: dict[str, Any],
    *,
    enforcement_sensitive: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """GH-143 B-007: tier-scoped authorization or per-PR human authorization.

    standard_auto on a non-sensitive fastlane/standard PR with tier evidence
    plus an independent substantiation reference satisfies the authorization
    item. Every other case (heavy, sensitive, missing tier evidence or
    substantiation, out-of-set authorization_tier) keeps the existing
    human_authorization requirement.
    """
    reasons: list[str] = []
    tier = evidence.get("authorization_tier")
    if tier is not None and tier not in AUTHORIZATION_TIERS:
        allowed = ", ".join(sorted(AUTHORIZATION_TIERS))
        reasons.append(f"authorization_tier must be one of: {allowed}")
        tier = None
    if tier == "standard_auto":
        pr_tier = evidence.get("pr_tier")
        substantiation = _tier_substantiation_reference(evidence)
        if (
            pr_tier in STANDARD_AUTO_TIERS
            and _valid_pr_tier_evidence(evidence.get("pr_tier_evidence"))
            and not enforcement_sensitive
            and substantiation is not None
        ):
            return (
                [
                    f"tier authorization: standard_auto (pr_tier={pr_tier}), "
                    f"substantiated by {substantiation}"
                ],
                [],
                reasons,
            )
    authorization = evidence.get("human_authorization")
    if not isinstance(authorization, dict):
        return [], ["human_authorization"], reasons
    missing = []
    for key in ["actor", "source"]:
        if not _non_empty_string(authorization.get(key)):
            missing.append(f"human_authorization.{key}")
    if missing:
        return [], missing, reasons
    return (
        [f"human authorization from {authorization['actor']} via {authorization['source']}"],
        [],
        reasons,
    )


def evaluate_pr_gate(
    evidence: dict[str, Any],
    repo: Path | None = None,
    config: PackConfig | None = None,
) -> dict[str, Any]:
    """Evaluate merge-readiness evidence and return a stable decision object."""

    reasons: list[str] = []
    satisfied: list[str] = []
    missing: list[str] = []
    items: list[dict[str, str]] = []
    sensitive_classification: dict[str, Any] | None = None
    sensitive_reasons: list[str] = []

    if _positive_int(evidence.get("pr")):
        satisfied.append(f"pr: {evidence['pr']}")
    else:
        missing.append("pr")
        items.append(item_from_missing("pr"))

    state = str(evidence.get("state") or "").upper()
    if state == "OPEN":
        satisfied.append("PR state is OPEN")
    elif state:
        reasons.append(f"PR state must be OPEN; got {state}")
        items.append(
            item_from_reason(
                f"PR state must be OPEN; got {state}", "invalid_evidence_value"
            )
        )
    else:
        missing.append("state")
        items.append(item_from_missing("state"))

    if evidence.get("is_draft") is False:
        satisfied.append("PR is not draft")
    elif "is_draft" not in evidence:
        missing.append("is_draft")
        items.append(item_from_missing("is_draft"))
    else:
        reasons.append("draft PR cannot merge")
        items.append(
            item_from_reason("draft PR cannot merge", "invalid_evidence_value")
        )

    if _non_empty_string(evidence.get("head_sha")):
        satisfied.append(f"head_sha: {evidence['head_sha']}")
    else:
        missing.append("head_sha")
        items.append(item_from_missing("head_sha"))

    if _positive_int(evidence.get("linked_issue")):
        satisfied.append(f"linked_issue: {evidence['linked_issue']}")
    else:
        missing.append("linked_issue")
        items.append(item_from_missing("linked_issue"))

    merge_state = str(evidence.get("merge_state") or "").upper()
    if merge_state in CLEAN_MERGE_STATES:
        satisfied.append(f"merge_state: {merge_state}")
    elif merge_state:
        reasons.append(f"merge_state must be CLEAN; got {merge_state}")
        items.append(
            item_from_reason(
                f"merge_state must be CLEAN; got {merge_state}",
                "invalid_evidence_value",
            )
        )
    else:
        missing.append("merge_state")
        items.append(item_from_missing("merge_state"))

    for checker in [
        _check_items,
        _issue_reference_items,
        _merge_record_items,
        _content_binding_items,
    ]:
        checker_satisfied, checker_missing, checker_reasons = checker(evidence)
        satisfied.extend(checker_satisfied)
        missing.extend(checker_missing)
        reasons.extend(checker_reasons)
        items.extend(
            items_from_legacy(
                checker_missing,
                checker_reasons,
                missing_category="missing_evidence_field",
                reason_category="invalid_evidence_value",
            )
        )

    review_satisfied, review_missing, review_reasons, review_items = (
        evaluate_review_contract_with_items(
            evidence,
            repo,
        )
    )
    satisfied.extend(review_satisfied)
    missing.extend(review_missing)
    reasons.extend(review_reasons)
    items.extend(review_items)

    has_sensitive_evidence = any(
        key in evidence
        for key in [
            "enforcement_sensitive",
            "sensitive_classification",
            "approved_spec",
        ]
    )
    if config is None and repo is not None:
        config = load_pack(resolve_path(repo, label="repository"))
    if config is not None:
        registry = sensitive_registry(config)
        has_sensitive_evidence = has_sensitive_evidence or bool(
            registry["paths"] or registry["specs"]
        )
    if has_sensitive_evidence:
        if repo is None:
            sensitive_reasons.append(
                "repository checkout is required to revalidate enforcement-sensitive evidence"
            )
            items.extend(
                item_from_reason(reason, "config_error")
                for reason in sensitive_reasons
            )
        elif config is None:
            sensitive_reasons.append(
                "workflow configuration is required to revalidate enforcement-sensitive evidence"
            )
            items.extend(
                item_from_reason(reason, "config_error")
                for reason in sensitive_reasons
            )
        else:
            sensitive_classification, sensitive_satisfied, sensitive_reasons, sensitive_items = (
                evaluate_sensitive_evidence_with_items(
                    config,
                    resolve_path(repo, label="repository"),
                    evidence,
                    expected_source="github_changed_files",
                    issue=evidence.get("linked_issue"),
                    expected_base_ref=evidence.get("base_ref"),
                    expected_base_head=evidence.get("base_sha"),
                )
            )
            satisfied.extend(sensitive_satisfied)
            items.extend(sensitive_items)
        if sensitive_reasons:
            reasons.extend(sensitive_reasons)
            missing.append("sensitive_enforcement")
            items.append(item_from_missing("sensitive_enforcement"))

    enforcement_sensitive_flag = bool(
        evidence.get("enforcement_sensitive") is True
        or (
            sensitive_classification
            and sensitive_classification.get("enforcement_sensitive")
        )
    )
    if enforcement_sensitive_flag:
        sensitive_review = evaluate_review_evidence(
            evidence.get("review_evidence"),
            expected_pr=evidence.get("pr"),
            expected_head_sha=evidence.get("head_sha"),
            current_binding=_binding_payload(evidence),
            enforcement_sensitive=True,
            repo=repo,
        )
        satisfied.extend(sensitive_review["satisfied"])
        review_reasons = [
            *sensitive_review["errors"],
            *sensitive_review["blocking_reasons"],
        ]
        reasons.extend(review_reasons)
        items.extend(
            item_from_reason(reason, "contract_violation")
            for reason in review_reasons
        )
    auth_satisfied, auth_missing, auth_reasons = _authorization_item(
        evidence, enforcement_sensitive=enforcement_sensitive_flag
    )
    satisfied.extend(auth_satisfied)
    missing.extend(auth_missing)
    reasons.extend(auth_reasons)
    items.extend(item_from_missing(entry) for entry in auth_missing)
    items.extend(
        item_from_reason(reason, "invalid_evidence_value") for reason in auth_reasons
    )

    deterministic_missing = [item for item in missing if not item.startswith("human_authorization")]
    if reasons or deterministic_missing:
        decision = "blocked"
    elif auth_missing:
        decision = "needs_human"
    else:
        decision = "allowed"

    blocked_actions = []
    if decision in {"blocked", "needs_human"}:
        blocked_actions.append("merge")
    if decision == "blocked":
        blocked_actions.append("final_approval")

    return {
        "decision": decision,
        "pr": evidence.get("pr"),
        "linked_issue": evidence.get("linked_issue"),
        "issue_reference": evidence.get("issue_reference"),
        "head_sha": evidence.get("head_sha"),
        "review_source": evidence.get("review_source"),
        "gate_query_completed_at": evidence.get("gate_query_completed_at"),
        "gate_query_head_sha": evidence.get("gate_query_head_sha"),
        "content_binding_version": evidence.get("content_binding_version"),
        "snapshot": evidence.get("snapshot"),
        "content_hashes": evidence.get("content_hashes"),
        "reused_components": evidence.get("reused_components"),
        "enforcement_sensitive": enforcement_sensitive_flag,
        "sensitive_classification": sensitive_classification,
        "reasons": sorted(set(reasons)),
        "satisfied": sorted(set(satisfied)),
        "missing": sorted(set(missing)),
        "rejection_items": [] if decision == "allowed" else finalize_items(items),
        "blocked_actions": blocked_actions,
        "verification_commands": [
            "python3 checks/pr_gate.py --repo . --evidence <evidence.json>",
            "python3 checks/check_workflow.py --repo .",
        ],
    }


def print_gate_human(result: dict[str, Any]) -> None:
    print(f"decision: {result['decision']}")
    if result.get("pr"):
        print(f"pr: {result['pr']}")
    if result.get("linked_issue"):
        print(f"linked_issue: GH-{result['linked_issue']}")
    if result.get("head_sha"):
        print(f"head_sha: {result['head_sha']}")
    if result["reasons"]:
        print("reasons:")
        for reason in result["reasons"]:
            print(f"- {reason}")
    if result["missing"]:
        print("missing:")
        for item in result["missing"]:
            print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate SpecRail PR merge-readiness evidence."
    )
    parser.add_argument("--repo", default=".", help="Repository root, kept for CLI symmetry")
    parser.add_argument("--evidence", required=True, help="PR evidence JSON file")
    parser.add_argument(
        "--mode",
        default="dry_run",
        choices=["dry_run", "advisory", "required"],
        help="Evaluation enforcement mode",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    add_prior_rejection_argument(parser)
    args = parser.parse_args()

    try:
        evidence = _load_json(Path(args.evidence))
        repo = resolve_path(Path(args.repo), label="repository")
        result = evaluate_pr_gate(evidence, repo=repo, config=load_pack(repo))
    except ValueError as exc:
        result = {
            "decision": "blocked",
            "pr": None,
            "linked_issue": None,
            "head_sha": None,
            "reasons": [str(exc)],
            "satisfied": [],
            "missing": [],
            "rejection_items": finalize_items(
                [item_from_reason(str(exc), "config_error")]
            ),
            "blocked_actions": ["merge", "final_approval"],
            "verification_commands": ["python3 checks/pr_gate.py --repo . --evidence <evidence.json>"],
        }

    result = apply_prior_rejection(
        result, args.prior_rejection, blocked_actions=["merge", "final_approval"]
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_gate_human(result)

    if result["decision"] == "blocked":
        return 1
    if result["decision"] == "needs_human" and args.mode == "required":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
