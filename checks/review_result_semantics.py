"""Shared semantic validation for terminal review artifacts and manifests."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from github_evidence_common import EvidenceError
from review_content_binding import (
    artifact_binding_errors,
    evaluate_review_evidence,
    load_review_content_binding,
    load_review_json as _load_manifest_json,
)
from review_round_semantics import validate_bounded_rounds
from schema_validation import validate_instance
from specrail_lib import SpecRailError, resolve_path, resolve_repo_path


REVIEW_STATUSES = {"completed", "pending", "failed", "cancelled", "superseded"}
TERMINAL_STATUSES = REVIEW_STATUSES - {"pending"}
REVIEW_VERDICTS = {"clean", "non_blocking", "changes_requested", "blocking"}
MERGE_READY_VERDICTS = {"clean", "non_blocking"}
REVIEW_SOURCES = {"independent_lane", "self_review"}
REVIEW_EXECUTIONS = {"hosted", "local"}
FINDING_SEVERITIES = {"critical", "important", "suggestion", "nit"}
PRIOR_FINDING_STATUSES = {"resolved", "unresolved", "obsolete"}
REVIEW_MODES = {"full", "resumed", "diff_only"}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DIFF_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
GATE_STATUSES = {"gated", "unavailable"}
UNGATED_DISCLOSURE_MARKER = "SpecRail gate status: unavailable"
SUMMARY_HEADING_RE = re.compile(r"^## Summary\s*$", re.MULTILINE)
H2_HEADING_RE = re.compile(r"^##\s+[^\n]+$", re.MULTILINE)
DEGRADED_POSITIVE_CLAIM_RE = re.compile(
    r"\b(?:this|the)\s+(?:review|result)\s+"
    r"(?:is|was|remains|has\s+been)\s+"
    r"(?!(?:not|never)\b)(?:[\w-]+\s+){0,2}"
    r"(?:SpecRail[- ]gated|verified|merge[- ]ready)\b"
    r"|\b(?:SpecRail[- ]gated|verified|merge[- ]ready)\s+"
    r"(?:review|result)\b",
    re.IGNORECASE,
)


class ReviewSemanticError(SpecRailError):
    """Raised when a manifest cannot be trusted or parsed."""


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _summary_section(body: str) -> str | None:
    heading = SUMMARY_HEADING_RE.search(body)
    if heading is None:
        return None
    next_heading = H2_HEADING_RE.search(body, heading.end())
    end = next_heading.start() if next_heading is not None else len(body)
    return body[heading.end() : end]


def _published_review_texts(artifact: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    body = artifact.get("body")
    if isinstance(body, str):
        texts.append(body)
    comments = artifact.get("comments")
    if isinstance(comments, list):
        for comment in comments:
            if isinstance(comment, dict) and isinstance(comment.get("body"), str):
                texts.append(comment["body"])
    return texts


def validate_degraded_review_provenance(
    artifact: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Validate the bidirectional degraded-review status/auth/body contract."""

    satisfied: list[str] = []
    errors: list[str] = []
    gate_status = artifact.get("gate_status")
    has_gate_status = "gate_status" in artifact
    gate_authorization = artifact.get("gate_authorization")
    has_gate_authorization = "gate_authorization" in artifact
    body = artifact.get("body")
    body_text = body if isinstance(body, str) else ""
    marker_present = UNGATED_DISCLOSURE_MARKER in body_text

    if has_gate_status:
        if gate_status not in GATE_STATUSES:
            allowed = ", ".join(sorted(GATE_STATUSES))
            errors.append(f"gate_status must be one of: {allowed}")
        else:
            satisfied.append(f"gate_status: {gate_status}")

    if gate_status == "unavailable":
        if _nonempty(gate_authorization):
            satisfied.append("gate_authorization present")
        else:
            errors.append(
                "gate_status unavailable requires a non-empty gate_authorization"
            )

        summary = _summary_section(body_text)
        summary_has_marker = (
            summary is not None
            and UNGATED_DISCLOSURE_MARKER in summary
        )
        if summary_has_marker:
            satisfied.append("body discloses unavailable SpecRail gate")
            if any(
                DEGRADED_POSITIVE_CLAIM_RE.search(text)
                for text in _published_review_texts(artifact)
            ):
                errors.append(
                    "gate_status unavailable published review text must not claim "
                    "the review is SpecRail-gated, verified, or merge-ready"
                )
        elif body_text:
            errors.append(
                "gate_status unavailable requires the ## Summary marker: "
                f"{UNGATED_DISCLOSURE_MARKER}"
            )
    else:
        if has_gate_authorization:
            errors.append(
                "gate_authorization is allowed only when gate_status is unavailable"
            )
        if marker_present:
            errors.append(
                "the unavailable disclosure marker requires gate_status unavailable"
            )

    return satisfied, errors


def parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not _nonempty(value):
        errors.append(f"{field} must be a non-empty timezone-aware ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be a timezone-aware ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must be a timezone-aware ISO-8601 timestamp")
        return None
    return parsed


def _validate_finding(
    finding: Any,
    index: int,
    errors: list[str],
) -> dict[str, Any] | None:
    label = f"findings[{index}]"
    if not isinstance(finding, dict):
        errors.append(f"{label} must be an object")
        return None
    normalized: dict[str, Any] = {}
    for key in ["id", "summary"]:
        if not _nonempty(finding.get(key)):
            errors.append(f"{label}.{key} must be a non-empty string")
        else:
            normalized[key] = str(finding[key]).strip()
    severity = finding.get("severity")
    if severity not in FINDING_SEVERITIES:
        errors.append(f"{label}.severity must be one of: {', '.join(sorted(FINDING_SEVERITIES))}")
    else:
        normalized["severity"] = severity
    if not isinstance(finding.get("actionable"), bool):
        errors.append(f"{label}.actionable must be a boolean")
    else:
        normalized["actionable"] = finding["actionable"]
    return normalized


def _validate_prior_finding(
    finding: Any,
    index: int,
    errors: list[str],
) -> dict[str, Any] | None:
    label = f"prior_findings[{index}]"
    if not isinstance(finding, dict):
        errors.append(f"{label} must be an object")
        return None
    normalized: dict[str, Any] = {}
    for key in ["id", "source_head_sha", "summary"]:
        if not _nonempty(finding.get(key)):
            errors.append(f"{label}.{key} must be a non-empty string")
        else:
            normalized[key] = str(finding[key]).strip()
    status = finding.get("status")
    if status not in PRIOR_FINDING_STATUSES:
        errors.append(
            f"{label}.status must be one of: {', '.join(sorted(PRIOR_FINDING_STATUSES))}"
        )
    else:
        normalized["status"] = status
    closure_evidence = finding.get("closure_evidence")
    if status in {"resolved", "obsolete"} and not _nonempty(closure_evidence):
        errors.append(f"{label}.closure_evidence is required for {status}")
    elif _nonempty(closure_evidence):
        normalized["closure_evidence"] = str(closure_evidence).strip()
    return normalized


def _validate_bounded_prior_finding(
    finding: Any, index: int, errors: list[str]
) -> dict[str, Any] | None:
    label = f"prior_findings[{index}]"
    if not isinstance(finding, dict):
        errors.append(f"{label} must be an object")
        return None
    allowed = {"finding_id", "source_artifact_id", "status", "evidence_pointer"}
    if set(finding) != allowed:
        errors.append(f"{label} must contain only: {', '.join(sorted(allowed))}")
    normalized: dict[str, Any] = {}
    for key in ["finding_id", "source_artifact_id"]:
        if not _nonempty(finding.get(key)):
            errors.append(f"{label}.{key} must be a non-empty string")
        else:
            normalized[key] = str(finding[key]).strip()
    status = finding.get("status")
    if status not in PRIOR_FINDING_STATUSES:
        errors.append(f"{label}.status must be one of: {', '.join(sorted(PRIOR_FINDING_STATUSES))}")
    else:
        normalized["status"] = status
    pointer = finding.get("evidence_pointer")
    patterns = {
        "thread": re.compile(r"^PRRT_[A-Za-z0-9_-]+$"),
        "comment": re.compile(r"^PRRC_[A-Za-z0-9_-]+$"),
        "artifact": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
        "commit": SHA_RE,
    }
    if not isinstance(pointer, dict) or set(pointer) != {"kind", "value"}:
        errors.append(f"{label}.evidence_pointer must contain only kind and value")
    else:
        kind, value = pointer.get("kind"), pointer.get("value")
        if kind not in patterns or not _nonempty(value) or not patterns.get(kind, re.compile("$")).fullmatch(str(value)):
            errors.append(f"{label}.evidence_pointer must use a typed stable ID")
        else:
            normalized["evidence_pointer"] = dict(pointer)
    return normalized


def validate_review_artifact(
    artifact: Any,
    *,
    expected_pr: int | None = None,
    expected_head_sha: str | None = None,
    expected_lane: str | None = None,
    expected_producer: str | None = None,
    current_binding: dict[str, Any] | None = None,
    original_binding: dict[str, Any] | None = None,
    enforcement_sensitive: bool = False,
) -> dict[str, Any]:
    """Validate one v2 artifact without deciding final merge authority."""

    errors: list[str] = []
    blockers: list[str] = []
    if not isinstance(artifact, dict):
        return {"valid": False, "errors": ["review artifact must be an object"], "blocking_reasons": []}

    required_strings = [
        "artifact_id",
        "reviewer_lane",
        "producer_identity",
        "review_source",
        "review_execution",
        "head_sha",
        "review_started_at",
        "status",
        "verdict",
        "body",
    ]
    for key in required_strings:
        if not _nonempty(artifact.get(key)):
            errors.append(f"{key} must be a non-empty string")
    if not _positive_int(artifact.get("pr")):
        errors.append("pr must be a positive integer")
    if expected_pr is not None and artifact.get("pr") != expected_pr:
        errors.append(f"pr must match manifest PR {expected_pr}")
    errors.extend(
        artifact_binding_errors(
            artifact,
            expected_head_sha=expected_head_sha,
            current_binding=current_binding,
            original_binding=original_binding,
            enforcement_sensitive=enforcement_sensitive,
        )
    )
    if expected_lane is not None and artifact.get("reviewer_lane") != expected_lane:
        errors.append("reviewer_lane must match its manifest lane")
    if expected_producer is not None and artifact.get("producer_identity") != expected_producer:
        errors.append("producer_identity must match its manifest lane")

    source = artifact.get("review_source")
    if source not in REVIEW_SOURCES:
        errors.append(f"review_source must be one of: {', '.join(sorted(REVIEW_SOURCES))}")
    execution = artifact.get("review_execution")
    if execution not in REVIEW_EXECUTIONS:
        errors.append(
            f"review_execution must be one of: {', '.join(sorted(REVIEW_EXECUTIONS))}"
        )
    elif execution == "hosted":
        errors.append("hosted review is supplemental only and cannot satisfy primary review")
    status = artifact.get("status")
    if status not in REVIEW_STATUSES:
        errors.append(f"status must be one of: {', '.join(sorted(REVIEW_STATUSES))}")
    verdict = artifact.get("verdict")
    if verdict not in REVIEW_VERDICTS:
        errors.append(f"verdict must be one of: {', '.join(sorted(REVIEW_VERDICTS))}")

    _, degraded_errors = validate_degraded_review_provenance(artifact)
    errors.extend(degraded_errors)

    started = parse_timestamp(artifact.get("review_started_at"), "review_started_at", errors)
    completed = None
    if status == "pending" and artifact.get("review_completed_at") is None:
        completed = None
    else:
        completed = parse_timestamp(
            artifact.get("review_completed_at"), "review_completed_at", errors
        )
    if started is not None and completed is not None and started > completed:
        errors.append("review_started_at must be at or before review_completed_at")

    if not isinstance(artifact.get("human_final_review_required"), bool):
        errors.append("human_final_review_required must be a boolean")
    elif source == "self_review" and artifact["human_final_review_required"] is not True:
        errors.append("self_review requires human_final_review_required=true")

    findings = artifact.get("findings")
    normalized_findings: list[dict[str, Any]] = []
    if not isinstance(findings, list):
        errors.append("findings must be a list")
    else:
        for index, finding in enumerate(findings):
            normalized = _validate_finding(finding, index, errors)
            if normalized is not None:
                normalized_findings.append(normalized)
        ids = [item.get("id") for item in normalized_findings if item.get("id")]
        if len(ids) != len(set(ids)):
            errors.append("findings IDs must be unique")

    bounded = artifact.get("round_policy_version") == 1
    if "round_policy_version" in artifact and not bounded:
        errors.append("round_policy_version must be 1")
    if bounded:
        review_round, review_mode = artifact.get("review_round"), artifact.get("review_mode")
        if not _positive_int(review_round):
            errors.append("bounded review_round must be a positive integer")
        if review_mode not in REVIEW_MODES:
            errors.append(f"bounded review_mode must be one of: {', '.join(sorted(REVIEW_MODES))}")
        if _positive_int(review_round) and review_round >= 2:
            if review_mode not in {"resumed", "diff_only"}:
                errors.append("bounded review_round >= 2 requires resumed or diff_only mode")
            if not SHA_RE.fullmatch(str(artifact.get("base_head_sha", ""))):
                errors.append("bounded review_round >= 2 requires a 40-character base_head_sha")
            if not DIFF_SHA_RE.fullmatch(str(artifact.get("diff_sha256", ""))):
                errors.append("bounded review_round >= 2 requires a 64-character diff_sha256")

    prior = artifact.get("prior_findings")
    normalized_prior: list[dict[str, Any]] = []
    if not isinstance(prior, list):
        errors.append("prior_findings must be a list")
    else:
        for index, finding in enumerate(prior):
            validator = _validate_bounded_prior_finding if bounded else _validate_prior_finding
            normalized = validator(finding, index, errors)
            if normalized is not None:
                normalized_prior.append(normalized)
        key_fields = ("finding_id", "source_artifact_id") if bounded else ("id", "source_head_sha")
        prior_keys = [
            (item.get(key_fields[0]), item.get(key_fields[1]))
            for item in normalized_prior
            if item.get(key_fields[0]) and item.get(key_fields[1])
        ]
        if len(prior_keys) != len(set(prior_keys)):
            errors.append("prior_findings id/source_head_sha pairs must be unique")

    if not isinstance(artifact.get("comments"), list):
        errors.append("comments must be a list")

    if status != "completed":
        blockers.append(f"review status is not completed: {status}")
    if verdict not in MERGE_READY_VERDICTS:
        blockers.append(f"review verdict is not merge-ready: {verdict}")
    if artifact.get("gate_status") == "unavailable":
        blockers.append(
            "gate_status unavailable cannot satisfy merge-ready review evidence"
        )
    if verdict == "clean" and normalized_findings:
        blockers.append("clean verdict requires zero findings")
    for finding in normalized_findings:
        if finding.get("severity") in {"critical", "important"} or finding.get("actionable") is True:
            blockers.append(f"blocking current-head finding: {finding.get('id', '<missing>')}")
    for finding in normalized_prior:
        if finding.get("status") == "unresolved":
            blockers.append(
                f"unresolved prior finding: {finding.get('finding_id', finding.get('id', '<missing>'))}"
            )

    return {
        "valid": not errors,
        "errors": errors,
        "blocking_reasons": blockers,
        "artifact": artifact,
    }


def load_review_manifest(
    repo: Path,
    manifest_path: str,
    *,
    expected_pr: int,
    expected_head_sha: str,
    current_binding: dict[str, Any] | None = None,
    enforcement_sensitive: bool = False,
) -> dict[str, Any]:
    """Load every manifest artifact through repository-safe paths."""

    resolved_repo = resolve_path(repo, label="repository")
    path, manifest = _load_manifest_json(resolved_repo, manifest_path, "review manifest")
    _, review_schema = _load_manifest_json(
        resolved_repo,
        "schemas/review_result.schema.json",
        "review result schema",
    )
    errors: list[str] = []
    version = manifest.get("version")
    if version not in {1, 2}:
        errors.append("review manifest version must be 1 or 2")
    if manifest.get("pr") != expected_pr:
        errors.append(f"review manifest pr must match PR {expected_pr}")
    if manifest.get("head_sha") != expected_head_sha:
        errors.append("review manifest head_sha must match the current PR head")
    if not isinstance(manifest.get("human_final_review_required"), bool):
        errors.append("review manifest human_final_review_required must be a boolean")
    lanes = manifest.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        errors.append("review manifest lanes must be a non-empty list")
        lanes = []

    artifacts: list[dict[str, Any]] = []
    original_bindings: dict[str, dict[str, Any]] = {}
    artifact_paths_seen: set[str] = set()
    lane_ids: set[str] = set()
    lane_roster: list[dict[str, Any]] = []
    for lane_index, lane in enumerate(lanes):
        label = f"review manifest lanes[{lane_index}]"
        if not isinstance(lane, dict):
            errors.append(f"{label} must be an object")
            continue
        lane_id = lane.get("lane_id")
        producer = lane.get("producer_identity")
        if not _nonempty(lane_id):
            errors.append(f"{label}.lane_id must be a non-empty string")
            continue
        if lane_id in lane_ids:
            errors.append(f"duplicate manifest lane_id: {lane_id}")
        lane_ids.add(str(lane_id))
        if not _nonempty(producer):
            errors.append(f"{label}.producer_identity must be a non-empty string")
            continue
        raw_paths = lane.get("artifact_paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            errors.append(f"{label}.artifact_paths must be a non-empty list")
            continue
        roster_entry = {
            "lane_id": str(lane_id),
            "producer_identity": str(producer),
        }
        if _nonempty(lane.get("successor_of")):
            roster_entry["successor_of"] = str(lane["successor_of"])
        lane_roster.append(roster_entry)
        for artifact_index, raw_artifact_path in enumerate(raw_paths):
            if not _nonempty(raw_artifact_path):
                errors.append(f"{label}.artifact_paths[{artifact_index}] must be non-empty")
                continue
            normalized_path = str(raw_artifact_path).strip()
            if normalized_path in artifact_paths_seen:
                errors.append(f"duplicate review artifact path: {normalized_path}")
                continue
            artifact_paths_seen.add(normalized_path)
            try:
                _, artifact = _load_manifest_json(
                    resolved_repo,
                    normalized_path,
                    f"review artifact {normalized_path}",
                )
            except ReviewSemanticError as exc:
                errors.append(str(exc))
                continue
            try:
                validate_instance(
                    review_schema,
                    artifact,
                    f"review artifact {normalized_path}",
                )
            except SpecRailError as exc:
                errors.append(str(exc))
            original_binding = None
            try:
                original_binding = load_review_content_binding(resolved_repo, artifact)
            except EvidenceError as exc:
                errors.append(f"{normalized_path}: {exc}")
            if original_binding is not None and _nonempty(artifact.get("artifact_id")):
                original_bindings[str(artifact["artifact_id"])] = original_binding
            result = validate_review_artifact(
                artifact,
                expected_pr=expected_pr,
                expected_lane=str(lane_id),
                expected_producer=str(producer),
                current_binding=None,
                original_binding=original_binding,
                enforcement_sensitive=False,
            )
            errors.extend(f"{normalized_path}: {item}" for item in result["errors"])
            artifact_copy = dict(artifact)
            artifact_copy["artifact_path"] = normalized_path
            artifacts.append(artifact_copy)

    artifact_ids = [item.get("artifact_id") for item in artifacts if _nonempty(item.get("artifact_id"))]
    if len(artifact_ids) != len(set(artifact_ids)):
        errors.append("review artifact IDs must be unique across the manifest")

    per_lane_head: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for artifact in artifacts:
        if artifact.get("status") in TERMINAL_STATUSES:
            key = (artifact.get("reviewer_lane"), artifact.get("head_sha"))
            per_lane_head.setdefault(key, []).append(artifact)
    for (lane_id, head_sha), candidates in per_lane_head.items():
        if len(candidates) > 1:
            errors.append(
                f"duplicate terminal artifacts for lane {lane_id} at head {head_sha}"
            )

    new_fields = {"round_policy_version", "diff_sha256", "round_cap_escalation"}
    round_audit = None
    if version == 1:
        if sum(item.get("content_binding_version") != 1 for item in artifacts) > 1 or any(new_fields & set(item) for item in artifacts):
            errors.append("review manifest v1 supports one legacy artifact only; migrate bounded rounds to v2")
        eligible_artifacts = artifacts
    else:
        round_audit = validate_bounded_rounds(manifest, artifacts, errors)
        latest_artifact_id = (
            round_audit["rounds"][-1]["artifact_id"]
            if round_audit and round_audit["rounds"]
            else None
        )
        eligible_artifacts = [
            item for item in artifacts
            if item.get("artifact_id") == latest_artifact_id
        ]

    current_head = [
        item for item in eligible_artifacts
        if item.get("head_sha") == expected_head_sha
    ]
    exact_terminal = [
        item for item in current_head if item.get("status") in TERMINAL_STATUSES
    ]
    reusable = [
        item
        for item in eligible_artifacts
        if item.get("head_sha") != expected_head_sha
        and item.get("status") in TERMINAL_STATUSES
        and not artifact_binding_errors(
            item,
            expected_head_sha=expected_head_sha,
            current_binding=current_binding,
            original_binding=original_bindings.get(str(item.get("artifact_id"))),
            enforcement_sensitive=enforcement_sensitive,
        )
    ]
    current = exact_terminal or reusable
    if not current:
        errors.append("review manifest has no terminal artifact for the current head or bindings")
    elif len(current) > 1:
        if len([item for item in current if item.get("head_sha") == expected_head_sha]) > 1:
            errors.append("review manifest has multiple terminal artifacts for the current head")
        else:
            errors.append("review manifest has multiple current or reusable terminal artifacts")

    stale_findings: dict[tuple[str, str], dict[str, Any]] = {}
    required_carry: set[tuple[str, str]] = set()
    selected_objects = {id(item) for item in current}
    for artifact in artifacts if version == 1 else []:
        source_head = artifact.get("head_sha")
        if source_head == expected_head_sha or id(artifact) in selected_objects:
            continue
        for finding in artifact.get("findings", []):
            if isinstance(finding, dict) and _nonempty(finding.get("id")) and _nonempty(source_head):
                key = (str(finding["id"]), str(source_head))
                if key in stale_findings and stale_findings[key] != finding:
                    errors.append(f"conflicting stale finding definition: {key[0]} at {key[1]}")
                stale_findings[key] = finding
                required_carry.add(key)
        for finding in artifact.get("prior_findings", []):
            if (
                isinstance(finding, dict)
                and finding.get("status") == "unresolved"
                and _nonempty(finding.get("id"))
                and _nonempty(finding.get("source_head_sha"))
            ):
                required_carry.add(
                    (str(finding["id"]), str(finding["source_head_sha"]))
                )

    carried: dict[tuple[str, str], dict[str, Any]] = {}
    for artifact in current if version == 1 else []:
        for finding in artifact.get("prior_findings", []):
            if isinstance(finding, dict) and _nonempty(finding.get("id")) and _nonempty(finding.get("source_head_sha")):
                key = (str(finding["id"]), str(finding["source_head_sha"]))
                if key in carried and carried[key] != finding:
                    errors.append(f"conflicting prior finding carry-forward: {key[0]} at {key[1]}")
                carried[key] = finding
    missing_carry = sorted(required_carry - set(carried))
    for finding_id, source_head in missing_carry:
        errors.append(f"missing prior finding carry-forward: {finding_id} from {source_head}")
    extra_carry = sorted(set(carried) - required_carry)
    for finding_id, source_head in extra_carry:
        errors.append(f"prior finding has no manifest source artifact: {finding_id} from {source_head}")
    blockers: list[str] = []
    review_sources: set[str] = set()
    review_executions: set[str] = set()
    completed_times: list[str] = []
    blocker_artifacts = [
        *current_head,
        *(item for item in current if item.get("head_sha") != expected_head_sha),
    ]
    for artifact in blocker_artifacts:
        result = validate_review_artifact(
            artifact,
            expected_pr=expected_pr,
            expected_head_sha=expected_head_sha,
            current_binding=current_binding,
            original_binding=original_bindings.get(str(artifact.get("artifact_id"))),
            enforcement_sensitive=enforcement_sensitive,
        )
        blockers.extend(result["blocking_reasons"])
    for artifact in current:
        if artifact.get("human_final_review_required") != manifest.get(
            "human_final_review_required"
        ):
            errors.append(
                f"current artifact {artifact.get('artifact_id')} conflicts with manifest human_final_review_required"
            )
        if _nonempty(artifact.get("review_source")):
            review_sources.add(str(artifact["review_source"]))
        if _nonempty(artifact.get("review_execution")):
            review_executions.add(str(artifact["review_execution"]))
        if _nonempty(artifact.get("review_completed_at")):
            completed_times.append(str(artifact["review_completed_at"]))
    if len(review_sources) > 1:
        blockers.append("current-head artifacts have conflicting review_source values")
    if len(review_executions) > 1:
        blockers.append("current-head artifacts have conflicting review_execution values")

    latest_completed_at = None
    latest_completed_time = None
    for value in completed_times:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest_completed_time is None or parsed > latest_completed_time:
            latest_completed_time = parsed
            latest_completed_at = value

    raw = path.read_bytes()
    return {
        "manifest_path": path.relative_to(resolved_repo).as_posix(),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "pr": expected_pr,
        "head_sha": expected_head_sha,
        "review_source": next(iter(review_sources), None),
        "review_execution": (
            next(iter(review_executions)) if len(review_executions) == 1 else None
        ),
        "review_completed_at": latest_completed_at,
        "human_final_review_required": manifest.get("human_final_review_required"),
        "lane_roster": lane_roster,
        "artifacts": artifacts,
        "current_artifact_ids": [item.get("artifact_id") for item in current],
        "round_audit": round_audit,
        "errors": errors,
        "blocking_reasons": sorted(set(blockers)),
    }
