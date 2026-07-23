"""Terminal review, resolver, and ordering contract for the offline PR gate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from rejection_items import items_from_legacy
from review_json_gate import validate_exact_git_diff
from review_result_semantics import (
    ReviewSemanticError,
    evaluate_review_evidence,
    load_review_manifest,
)


ACTIVE_CHANGE_REQUESTS = {"CHANGES_REQUESTED"}
REVIEW_SOURCES = {"independent_lane", "self_review"}
LANE_FAILURE_KINDS = {"usage_limit", "crash", "zero_output", "closed", "other"}
BLOCKED_RESOLVER_ROLES = {"implementer", "orchestrator", "coordinator", "unknown"}
ROUND_CAP_AUTHORIZATION_FIELDS = {
    "authorization_id",
    "pr",
    "prior_head_sha",
    "target_head_sha",
    "review_round",
    "decision",
    "actor",
    "source",
    "authorized_at",
    "authorized_human_maintainer",
}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_timestamp(value: Any) -> datetime | None:
    if not _nonempty(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _trusted_round_diff_reasons(repo: Path, round_audit: Any) -> list[str]:
    if not isinstance(round_audit, dict) or round_audit.get("policy") != "bounded_diff_v1":
        return []
    rounds = round_audit.get("rounds")
    if not isinstance(rounds, list):
        return []
    reasons: list[str] = []
    for index, item in enumerate(rounds, start=1):
        review_round = item.get("review_round") if isinstance(item, dict) else None
        if not _positive_int(review_round) or review_round < 2:
            continue
        reasons.extend(
            f"trusted review round {index}: {reason}"
            for reason in validate_exact_git_diff(
                repo,
                item.get("base_head_sha"),
                item.get("head_sha"),
                item.get("diff_sha256"),
            )
        )
    return reasons


def _round_cap_authorization_items(
    evidence: dict[str, Any],
    round_audit: Any,
    artifacts: Any,
) -> tuple[list[str], list[str], list[str]]:
    authorizations = evidence.get("round_cap_authorizations")
    if round_audit is None:
        if authorizations is None:
            return [], [], []
        return [], [], [
            "round_cap_authorizations require a trusted bounded_diff_v1 round_audit"
        ]
    if not isinstance(round_audit, dict):
        return [], [], ["trusted review_evidence.round_audit must be an object"]
    if round_audit.get("policy") != "bounded_diff_v1" or round_audit.get("cap") != 3:
        return [], [], ["trusted round_audit policy/cap must be bounded_diff_v1/3"]
    rounds = round_audit.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        return [], [], ["trusted round_audit.rounds must be a non-empty list"]
    if round_audit.get("total_rounds") != len(rounds):
        return [], [], ["trusted round_audit.total_rounds must match rounds"]

    if authorizations is None:
        authorizations = []
    if not isinstance(authorizations, list):
        return [], [], ["round_cap_authorizations must be a list"]

    reasons: list[str] = []
    artifacts_by_id = {
        item.get("artifact_id"): item
        for item in artifacts if isinstance(item, dict) and _nonempty(item.get("artifact_id"))
    } if isinstance(artifacts, list) else {}
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(authorizations, start=1):
        if not isinstance(item, dict):
            reasons.append(f"round_cap_authorizations[{index}] must be an object")
            continue
        unknown = sorted(set(item) - ROUND_CAP_AUTHORIZATION_FIELDS)
        missing_fields = sorted(ROUND_CAP_AUTHORIZATION_FIELDS - set(item))
        if unknown:
            reasons.append(
                f"round_cap_authorizations[{index}] contains unsupported fields: "
                + ", ".join(unknown)
            )
        if missing_fields:
            reasons.append(
                f"round_cap_authorizations[{index}] is missing fields: "
                + ", ".join(missing_fields)
            )
        authorization_id = item.get("authorization_id")
        if not _nonempty(authorization_id):
            reasons.append(
                f"round_cap_authorizations[{index}].authorization_id is required"
            )
            continue
        if authorization_id in by_id:
            reasons.append(
                f"round cap authorization_id is reused: {authorization_id}"
            )
            continue
        by_id[str(authorization_id)] = item

    used_ids: set[str] = set()
    satisfied: list[str] = []
    missing: list[str] = []
    for index, current_round in enumerate(rounds):
        if not isinstance(current_round, dict):
            reasons.append(f"trusted round_audit.rounds[{index + 1}] must be an object")
            continue
        review_round = current_round.get("review_round")
        if not _positive_int(review_round) or review_round <= 3:
            continue
        authorization_id = current_round.get("escalation_authorization_id")
        if not _nonempty(authorization_id):
            missing.append(
                f"review_evidence.round_audit.rounds[{index + 1}]."
                "escalation_authorization_id"
            )
            reasons.append(
                f"review round {review_round} exceeds cap 3 without exact authorization"
            )
            continue
        authorization_key = str(authorization_id)
        authorization = by_id.get(authorization_key)
        if authorization is None:
            missing.append(
                f"round_cap_authorizations[{authorization_key}]"
            )
            reasons.append(
                f"review round {review_round} references missing round cap authorization "
                f"{authorization_key}"
            )
            continue
        if authorization_key in used_ids:
            reasons.append(
                f"round cap authorization_id is reused across rounds: {authorization_key}"
            )
            continue
        used_ids.add(authorization_key)
        prior_round = rounds[index - 1] if index > 0 else None
        prior_head = prior_round.get("head_sha") if isinstance(prior_round, dict) else None
        expected = {
            "pr": evidence.get("pr"),
            "prior_head_sha": prior_head,
            "target_head_sha": current_round.get("head_sha"),
            "review_round": review_round,
            "decision": "continue_once",
            "authorized_human_maintainer": True,
        }
        for field, expected_value in expected.items():
            if authorization.get(field) != expected_value:
                reasons.append(
                    f"round cap authorization {authorization_key}.{field} must equal "
                    f"trusted round binding {expected_value!r}"
                )
        for field in ["actor", "source"]:
            if not _nonempty(authorization.get(field)):
                reasons.append(
                    f"round cap authorization {authorization_key}.{field} is required"
                )
        authorized_at = _parse_timestamp(authorization.get("authorized_at"))
        if authorized_at is None:
            reasons.append(
                f"round cap authorization {authorization_key}.authorized_at must be a "
                "timezone-aware ISO-8601 timestamp"
            )
        target = artifacts_by_id.get(current_round.get("artifact_id"))
        review_started_at = _parse_timestamp(
            target.get("review_started_at") if isinstance(target, dict) else None
        )
        if authorized_at is not None and (
            review_started_at is None or authorized_at > review_started_at
        ):
            reasons.append(
                f"round cap authorization {authorization_key} must precede target review start"
            )
        if not any(
            reason.startswith(f"round cap authorization {authorization_key}")
            for reason in reasons
        ):
            satisfied.append(
                f"review round {review_round} has exact one-time maintainer authorization: "
                f"{authorization_key}"
            )

    unused_ids = sorted(set(by_id) - used_ids)
    if unused_ids:
        reasons.append(
            "round cap authorizations are not bound to an over-cap manifest round: "
            + ", ".join(unused_ids)
        )
    return satisfied, missing, reasons


def _scope_binds_pr(scope: Any, pr: Any) -> bool:
    if not _nonempty(scope) or not isinstance(pr, int) or isinstance(pr, bool):
        return False
    return re.search(rf"\bPR\s*#?\s*{pr}(?!\d)", str(scope), re.IGNORECASE) is not None


def _current_binding(evidence: dict[str, Any]) -> dict[str, Any] | None:
    keys = ["content_binding_version", "snapshot", "content_hashes"]
    if not any(key in evidence for key in keys):
        return None
    return {key: evidence.get(key) for key in keys}


def _enforcement_sensitive(evidence: dict[str, Any]) -> bool:
    classification = evidence.get("sensitive_classification")
    return bool(
        evidence.get("enforcement_sensitive") is True
        or (
            isinstance(classification, dict)
            and classification.get("enforcement_sensitive") is True
        )
    )


def _github_review_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    reasons: list[str] = []
    reviews = evidence.get("reviews", [])
    if not isinstance(reviews, list):
        return satisfied, [], ["reviews must be a list"]
    for index, review in enumerate(reviews, start=1):
        if not isinstance(review, dict):
            reasons.append(f"review #{index} is not an object")
            continue
        if str(review.get("state") or "").upper() in ACTIVE_CHANGE_REQUESTS:
            reasons.append(f"changes requested by {review.get('author') or f'review #{index}'}")
    if not reasons:
        satisfied.append("no active changes-requested review evidence")
    return satisfied, [], reasons


def _verified_reviewer_resolver(
    thread: dict[str, Any],
    review_evidence: dict[str, Any],
) -> bool:
    resolved_by = thread.get("resolved_by")
    original_author = thread.get("original_author")
    original_comment_id = thread.get("original_comment_id")
    lane_id = thread.get("lane_id")
    if (
        not _nonempty(lane_id)
        or not _nonempty(original_author)
        or not _nonempty(original_comment_id)
    ):
        return False
    roster = review_evidence.get("lane_roster", [])
    raw_current_ids = review_evidence.get("current_artifact_ids", [])
    current_ids = {
        item for item in raw_current_ids
        if isinstance(item, str) and item
    } if isinstance(raw_current_ids, list) else set()
    raw_artifacts = review_evidence.get("artifacts", [])
    artifacts = raw_artifacts if isinstance(raw_artifacts, list) else []
    lanes = [
        lane for lane in roster
        if isinstance(lane, dict) and lane.get("lane_id") == lane_id
    ] if isinstance(roster, list) else []
    if len(lanes) != 1:
        return False
    lane = lanes[0]
    producer_identity = lane.get("producer_identity")
    successor_of = lane.get("successor_of")
    if not successor_of:
        if producer_identity != original_author:
            return False
        if resolved_by == original_author:
            return True
    elif successor_of != thread.get("successor_of"):
        return False

    mapped_login = thread.get("resolver_role_source") == "explicit_map"
    if successor_of and not mapped_login:
        return False
    if resolved_by != producer_identity and not mapped_login:
        return False
    re_review_artifact_id = thread.get("re_review_artifact_id")
    verified_re_review = any(
        isinstance(artifact, dict)
        and artifact.get("artifact_id") == re_review_artifact_id
        and artifact.get("artifact_id") in current_ids
        and artifact.get("reviewer_lane") == lane_id
        and artifact.get("producer_identity") == producer_identity
        and artifact.get("status") == "completed"
        and artifact.get("verdict") in {"clean", "non_blocking"}
        for artifact in artifacts
    )
    if not verified_re_review:
        return False
    if not successor_of:
        return producer_identity == original_author

    cursor = successor_of
    visited: set[str] = set()
    while _nonempty(cursor) and cursor not in visited:
        visited.add(str(cursor))
        predecessors = [
            candidate for candidate in roster
            if isinstance(candidate, dict) and candidate.get("lane_id") == cursor
        ]
        if not predecessors:
            return mapped_login and cursor == original_author
        if len(predecessors) != 1:
            return False
        predecessor = predecessors[0]
        if predecessor.get("producer_identity") == original_author:
            original_lanes = [
                candidate for candidate in roster
                if (
                    isinstance(candidate, dict)
                    and candidate.get("producer_identity") == original_author
                )
            ]
            return len(original_lanes) == 1
        cursor = predecessor.get("successor_of")
    return False


def _thread_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    threads = evidence.get("review_threads")
    if not isinstance(threads, list):
        return satisfied, ["review_threads"], ["review thread evidence is missing"]
    review_evidence = evidence.get("review_evidence")
    if not isinstance(review_evidence, dict):
        review_evidence = {}
    unresolved: list[str] = []
    for index, thread in enumerate(threads, start=1):
        if not isinstance(thread, dict):
            unresolved.append(f"thread #{index}")
            continue
        identifier = str(thread.get("url") or thread.get("id") or f"thread #{index}")
        if thread.get("is_resolved") is not True:
            unresolved.append(identifier)
            continue
        if not _nonempty(thread.get("resolved_by")):
            missing.append(f"review_threads[{index}].resolved_by")
        role = thread.get("resolver_role")
        if not _nonempty(role):
            missing.append(f"review_threads[{index}].resolver_role")
            continue
        if role == "human":
            if thread.get("authorized_human_maintainer") is True:
                satisfied.append(
                    f"review thread resolved by human authorized maintainer: {identifier}"
                )
            else:
                reasons.append(
                    f"actionable review thread human resolver lacks maintainer authorization: {identifier}"
                )
        elif role == "reviewer_lane":
            if _verified_reviewer_resolver(thread, review_evidence):
                satisfied.append(f"review thread resolved by verified reviewer lane: {identifier}")
            else:
                reasons.append(
                    f"actionable review thread resolver lacks original/successor re-review evidence: {identifier}"
                )
        elif role in BLOCKED_RESOLVER_ROLES:
            reasons.append(f"review thread resolved by forbidden {role}: {identifier}")
        else:
            reasons.append(f"review thread resolver_role is unsupported: {role}")
    if unresolved:
        reasons.append("unresolved review threads: " + ", ".join(unresolved))
    else:
        satisfied.append("no unresolved active review threads")
    return satisfied, missing, reasons


def _self_review_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = ["review_source: self_review"]
    missing: list[str] = []
    reasons: list[str] = []
    failures = evidence.get("lane_failures")
    if not isinstance(failures, list) or not failures:
        reasons.append("self_review requires recorded lane_failures")
    else:
        for index, failure in enumerate(failures, start=1):
            if not isinstance(failure, dict):
                continue
            if failure.get("pr") != evidence.get("pr"):
                reasons.append(f"lane_failures[{index}].pr must match pr")
            if failure.get("head_sha") != evidence.get("head_sha"):
                reasons.append(f"lane_failures[{index}].head_sha must match head_sha")
    authorization = evidence.get("self_review_authorization")
    if not isinstance(authorization, dict):
        return satisfied, ["self_review_authorization"], [
            *reasons,
            "self_review requires explicit self_review_authorization",
        ]
    for key in ["actor", "source", "scope"]:
        if not _nonempty(authorization.get(key)):
            missing.append(f"self_review_authorization.{key}")
    scope = authorization.get("scope")
    if _nonempty(scope) and (
        not _scope_binds_pr(scope, evidence.get("pr"))
        or not _nonempty(evidence.get("head_sha"))
        or str(evidence["head_sha"]) not in str(scope)
    ):
        reasons.append("self_review_authorization.scope must bind the same PR and head_sha")
    review_evidence = evidence.get("review_evidence")
    if not isinstance(review_evidence, dict) or review_evidence.get("human_final_review_required") is not True:
        reasons.append("self_review requires human_final_review_required=true")
    if not missing:
        satisfied.append(
            f"self-review authorization from {authorization['actor']} via {authorization['source']}"
        )
    return satisfied, missing, reasons


def _source_and_lane_items(
    evidence: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    source = evidence.get("review_source")
    execution = evidence.get("review_execution")
    review_evidence = evidence.get("review_evidence")
    if not _nonempty(source):
        return satisfied, ["review_source"], ["review_source evidence is missing"]
    if source not in REVIEW_SOURCES:
        return satisfied, missing, [
            f"review_source must be one of: {', '.join(sorted(REVIEW_SOURCES))}"
        ]
    if not isinstance(review_evidence, dict):
        return satisfied, ["review_evidence"], [
            "review_source alone cannot prove terminal review evidence"
        ]
    if review_evidence.get("review_source") != source:
        reasons.append("review_source must be derived from review_evidence")
    if not _nonempty(execution):
        missing.append("review_execution")
        reasons.append("primary review execution evidence is missing")
    elif review_evidence.get("review_execution") != execution:
        reasons.append("review_execution must be derived from review_evidence")
    elif execution != "local":
        reasons.append("hosted review is supplemental only; primary review must be local")
    else:
        satisfied.append("review_execution: local")
    if source == "independent_lane":
        satisfied.append("review_source: independent_lane")
    else:
        nested_satisfied, nested_missing, nested_reasons = _self_review_items(evidence)
        satisfied.extend(nested_satisfied)
        missing.extend(nested_missing)
        reasons.extend(nested_reasons)

    failures = evidence.get("lane_failures")
    if not isinstance(failures, list):
        return satisfied, [*missing, "lane_failures"], [*reasons, "lane_failures must be a list"]
    for index, failure in enumerate(failures, start=1):
        if not isinstance(failure, dict):
            reasons.append(f"lane_failures[{index}] must be an object")
            continue
        for key in ["lane_id", "failure_kind", "observed_marker"]:
            if not _nonempty(failure.get(key)):
                missing.append(f"lane_failures[{index}].{key}")
        kind = failure.get("failure_kind")
        if _nonempty(kind) and kind not in LANE_FAILURE_KINDS:
            reasons.append(f"lane_failures[{index}].failure_kind is unsupported: {kind}")
    satisfied.append(
        f"lane failures recorded: {len(failures)}" if failures else "no lane failures recorded"
    )
    return satisfied, missing, reasons


def _terminal_items(
    evidence: dict[str, Any], repo: Path | None = None,
) -> tuple[list[str], list[str], list[str]]:
    review_evidence = evidence.get("review_evidence")
    result = evaluate_review_evidence(
        review_evidence,
        expected_pr=evidence.get("pr"),
        expected_head_sha=evidence.get("head_sha"),
        current_binding=_current_binding(evidence),
        repo=repo,
        enforcement_sensitive=_enforcement_sensitive(evidence),
    )
    missing = [] if isinstance(review_evidence, dict) else ["review_evidence"]
    return result["satisfied"], missing, [
        *result["errors"],
        *result["blocking_reasons"],
    ]


def _manifest_trust_items(
    evidence: dict[str, Any],
    repo: Path | None,
) -> tuple[list[str], list[str], list[str]]:
    embedded = evidence.get("review_evidence")
    if not isinstance(embedded, dict):
        return [], ["review_evidence"], []
    if repo is None:
        if embedded.get("round_audit") is not None:
            return [], [], [
                "bounded round audit requires repository-safe manifest reload"
            ]
        return [], [], []
    manifest_path = embedded.get("manifest_path")
    if not _nonempty(manifest_path):
        return [], ["review_evidence.manifest_path"], []
    try:
        trusted = load_review_manifest(
            repo,
            str(manifest_path),
            expected_pr=evidence.get("pr"),
            expected_head_sha=evidence.get("head_sha"),
            current_binding=_current_binding(evidence),
            enforcement_sensitive=_enforcement_sensitive(evidence),
        )
    except ReviewSemanticError as exc:
        return [], [], [f"review manifest trust validation failed: {exc}"]

    def artifacts_without_paths(value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [
            {key: item for key, item in artifact.items() if key != "artifact_path"}
            if isinstance(artifact, dict)
            else artifact
            for artifact in value
        ]

    mismatches: list[str] = []
    for key in [
        "manifest_sha256",
        "pr",
        "head_sha",
        "review_source",
        "review_execution",
        "review_completed_at",
        "human_final_review_required",
        "lane_roster",
        "current_artifact_ids",
        "round_audit",
        "errors",
        "blocking_reasons",
    ]:
        if embedded.get(key) != trusted.get(key):
            mismatches.append(f"review_evidence.{key} differs from trusted manifest")
    if artifacts_without_paths(embedded.get("artifacts")) != artifacts_without_paths(
        trusted.get("artifacts")
    ):
        mismatches.append("review_evidence.artifacts differ from trusted manifest")
    cap_satisfied, cap_missing, cap_reasons = _round_cap_authorization_items(
        evidence,
        trusted.get("round_audit"),
        trusted.get("artifacts"),
    )
    diff_reasons = _trusted_round_diff_reasons(repo, trusted.get("round_audit"))
    if mismatches:
        return [], cap_missing, [*mismatches, *diff_reasons, *cap_reasons]
    return [
        "review manifest revalidated from repository-safe paths",
        *cap_satisfied,
    ], cap_missing, [*diff_reasons, *cap_reasons]


def _ordering_items(evidence: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    if "gate_completed_at" in evidence:
        reasons.append("gate_completed_at alias is unsupported; use canonical gate_query_completed_at")

    review_evidence = evidence.get("review_evidence")
    manifest_completed_at = (
        review_evidence.get("review_completed_at")
        if isinstance(review_evidence, dict)
        else None
    )
    if not _nonempty(manifest_completed_at):
        missing.append("review_evidence.review_completed_at")
    elif evidence.get("review_completed_at") != manifest_completed_at:
        reasons.append(
            "review_completed_at must match trusted review_evidence.review_completed_at"
        )

    fields = ["review_completed_at", "gate_started_at", "gate_query_completed_at"]
    times: dict[str, datetime] = {}
    for field in fields:
        parsed = _parse_timestamp(evidence.get(field))
        if parsed is None:
            missing.append(field)
            if evidence.get(field) is not None:
                reasons.append(f"{field} must be a timezone-aware ISO-8601 timestamp")
        else:
            times[field] = parsed
    if all(field in times for field in fields):
        if times["review_completed_at"] > times["gate_started_at"]:
            reasons.append("review must complete at or before gate start")
        else:
            satisfied.append("review completed before gate start")
        if times["gate_started_at"] > times["gate_query_completed_at"]:
            reasons.append("gate_started_at must be at or before gate_query_completed_at")
        else:
            satisfied.append("gate start precedes gate query completion")

    head_sha = evidence.get("head_sha")
    gate_head_sha = evidence.get("gate_query_head_sha")
    if not _nonempty(gate_head_sha):
        missing.append("gate_query_head_sha")
    elif gate_head_sha != head_sha:
        reasons.append("gate_query_head_sha must match head_sha")
    else:
        satisfied.append("gate_query_head_sha matches head_sha")

    merge_time = evidence.get("merge_dispatched_at")
    merge_head = evidence.get("merge_head_sha")
    if (merge_time is None) != (merge_head is None):
        missing.append("merge_ordering_pair")
        reasons.append("merge_dispatched_at and merge_head_sha must be provided together")
    elif merge_time is not None:
        parsed_merge = _parse_timestamp(merge_time)
        if parsed_merge is None:
            reasons.append("merge_dispatched_at must be a timezone-aware ISO-8601 timestamp")
        elif "gate_query_completed_at" in times and times["gate_query_completed_at"] >= parsed_merge:
            reasons.append("gate query must complete before merge dispatch")
        else:
            satisfied.append("merge dispatch ordered after gate query")
        if merge_head != gate_head_sha:
            reasons.append("merge_head_sha must match gate_query_head_sha")
        else:
            satisfied.append("merge_head_sha matches gate_query_head_sha")
    return satisfied, missing, reasons


def evaluate_review_contract(
    evidence: dict[str, Any],
    repo: Path | None = None,
) -> tuple[list[str], list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []
    for checker in [
        _github_review_items,
        _thread_items,
        _source_and_lane_items,
        _ordering_items,
    ]:
        nested_satisfied, nested_missing, nested_reasons = checker(evidence)
        satisfied.extend(nested_satisfied)
        missing.extend(nested_missing)
        reasons.extend(nested_reasons)
    nested_satisfied, nested_missing, nested_reasons = _terminal_items(evidence, repo)
    satisfied.extend(nested_satisfied)
    missing.extend(nested_missing)
    reasons.extend(nested_reasons)
    trust_satisfied, trust_missing, trust_reasons = _manifest_trust_items(evidence, repo)
    satisfied.extend(trust_satisfied)
    missing.extend(trust_missing)
    reasons.extend(trust_reasons)
    return satisfied, missing, reasons


def evaluate_review_contract_with_items(
    evidence: dict[str, Any],
    repo: Path | None = None,
) -> tuple[list[str], list[str], list[str], list[dict[str, str]]]:
    """Companion to evaluate_review_contract that also emits rejection items."""

    satisfied, missing, reasons = evaluate_review_contract(evidence, repo)
    items = items_from_legacy(
        missing,
        reasons,
        missing_category="missing_evidence_field",
        reason_category="contract_violation",
    )
    return satisfied, missing, reasons, items
