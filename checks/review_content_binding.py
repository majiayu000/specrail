"""Trusted sidecar validation for reusable terminal review artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evidence_content_binding import (
    load_content_binding_evidence,
    validate_component_binding,
    validate_content_binding,
)
from github_evidence_common import EvidenceError
from specrail_lib import SpecRailError, resolve_repo_path


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_versioned_review(artifact: dict[str, Any]) -> bool:
    return any(
        key in artifact
        for key in [
            "content_binding_version",
            "covered_categories",
            "content_bindings",
            "content_binding_evidence",
        ]
    )


def load_review_content_binding(
    repo: Path, artifact: dict[str, Any],
) -> dict[str, Any] | None:
    if not is_versioned_review(artifact):
        return None
    pr = artifact.get("pr")
    head = artifact.get("head_sha")
    if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
        raise EvidenceError("review artifact pr must identify its content binding evidence")
    if not isinstance(head, str) or not head:
        raise EvidenceError("review artifact head_sha must identify its content binding evidence")
    return load_content_binding_evidence(
        repo,
        artifact.get("content_binding_evidence"),
        expected_pr=pr,
        expected_head_sha=head,
    )


def artifact_binding_errors(
    artifact: dict[str, Any],
    *,
    expected_head_sha: str | None,
    current_binding: dict[str, Any] | None,
    original_binding: dict[str, Any] | None,
    enforcement_sensitive: bool,
) -> list[str]:
    """Validate legacy exact-head or sidecar-authenticated v1 review evidence."""

    if not is_versioned_review(artifact):
        if expected_head_sha is not None and artifact.get("head_sha") != expected_head_sha:
            return ["legacy review artifact head_sha must match the expected final head"]
        return []
    errors: list[str] = []
    try:
        covered, component_hashes = validate_component_binding(artifact)
    except EvidenceError as exc:
        return [f"review content binding is invalid: {exc}"]
    if original_binding is None:
        return ["v1 review artifact requires trusted collector binding evidence sidecar"]
    try:
        original = validate_content_binding(original_binding)
    except EvidenceError as exc:
        return [f"review collector binding evidence is invalid: {exc}"]
    original_hashes = original["content_hashes"]
    mismatched = [key for key in covered if component_hashes[key] != original_hashes[key]]
    if mismatched:
        errors.append(
            "review artifact content bindings must match its collector sidecar: "
            + ", ".join(mismatched)
        )
    if current_binding is None:
        if expected_head_sha is None and not enforcement_sensitive:
            return errors
        return [*errors, "v1 review artifact requires the current content binding"]
    try:
        current = validate_content_binding(current_binding)
    except EvidenceError as exc:
        return [*errors, f"review content binding is invalid: {exc}"]
    if expected_head_sha is not None and current["snapshot"]["head_sha"] != expected_head_sha:
        errors.append("current content binding snapshot.head_sha must match the expected final head")
    if any(original_hashes[key] != current["content_hashes"][key] for key in covered):
        errors.append("review artifact covered content bindings do not match the current snapshot")
    if enforcement_sensitive:
        missing = sorted({"code_inputs", "spec_files"} - set(covered))
        if missing:
            errors.append(
                "enforcement-sensitive review must cover actual code_inputs and spec_files"
            )
        if artifact.get("review_source") != "independent_lane":
            errors.append("enforcement-sensitive review must remain an independent terminal review")
    return errors


def load_review_json(
    repo: Path, raw_path: str, label: str,
) -> tuple[Path, dict[str, Any]]:
    """Load a repository-contained review JSON object."""

    from review_result_semantics import ReviewSemanticError

    try:
        path = resolve_repo_path(repo, raw_path, label=label)
    except SpecRailError as exc:
        raise ReviewSemanticError(
            f"{label} must use repo-relative POSIX paths within the repository: {exc}"
        ) from exc
    if not path.is_file():
        raise ReviewSemanticError(f"{label} is missing: {raw_path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReviewSemanticError(f"cannot read {label} {raw_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReviewSemanticError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ReviewSemanticError(f"{label} must contain a JSON object")
    return path, data


def evaluate_review_evidence(
    evidence: Any,
    *,
    expected_pr: int | None,
    expected_head_sha: str | None,
    current_binding: dict[str, Any] | None = None,
    repo: Path | None = None,
    enforcement_sensitive: bool = False,
) -> dict[str, list[str]]:
    """Revalidate embedded current or reusable manifest evidence."""

    from review_result_semantics import (
        REVIEW_EXECUTIONS,
        TERMINAL_STATUSES,
        validate_review_artifact,
    )

    errors: list[str] = []
    blockers: list[str] = []
    satisfied: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "errors": ["review_evidence must be an object"],
            "blocking_reasons": [],
            "satisfied": [],
        }
    if evidence.get("pr") != expected_pr:
        errors.append("review_evidence.pr must match pr")
    if evidence.get("head_sha") != expected_head_sha:
        errors.append("review_evidence.head_sha must match head_sha")
    execution = evidence.get("review_execution")
    if execution not in REVIEW_EXECUTIONS:
        errors.append(
            "review_evidence.review_execution must be one of: "
            + ", ".join(sorted(REVIEW_EXECUTIONS))
        )
    elif execution != "local":
        errors.append(
            "hosted review evidence is supplemental only; primary review must be local"
        )
    embedded_errors = evidence.get("errors")
    if not isinstance(embedded_errors, list):
        errors.append("review_evidence.errors must be a list")
    else:
        errors.extend(str(item) for item in embedded_errors if _nonempty(item))
    embedded_blockers = evidence.get("blocking_reasons")
    if not isinstance(embedded_blockers, list):
        errors.append("review_evidence.blocking_reasons must be a list")
    else:
        blockers.extend(str(item) for item in embedded_blockers if _nonempty(item))
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("review_evidence.artifacts must be a non-empty list")
    else:
        current = 0
        current_executions: set[str] = set()
        raw_current_ids = evidence.get("current_artifact_ids")
        valid_ids = (
            isinstance(raw_current_ids, list)
            and all(_nonempty(item) for item in raw_current_ids)
            and len(raw_current_ids) == len(set(raw_current_ids))
        )
        current_ids = set(raw_current_ids) if valid_ids else set()
        if not current_ids:
            errors.append(
                "review_evidence.current_artifact_ids must be a non-empty unique string list"
            )
        seen_ids: set[str] = set()
        for index, artifact in enumerate(artifacts):
            original_binding = None
            if isinstance(artifact, dict):
                if repo is None and artifact.get("content_binding_version") == 1:
                    errors.append(
                        f"review_evidence.artifacts[{index}]: "
                        "v1 review artifact requires repository sidecar revalidation"
                    )
                elif repo is not None:
                    try:
                        original_binding = load_review_content_binding(repo, artifact)
                    except EvidenceError as exc:
                        errors.append(f"review_evidence.artifacts[{index}]: {exc}")
            result = validate_review_artifact(
                artifact,
                expected_pr=expected_pr,
                original_binding=original_binding,
            )
            errors.extend(
                f"review_evidence.artifacts[{index}]: {item}"
                for item in result["errors"]
            )
            if not isinstance(artifact, dict):
                continue
            artifact_id = artifact.get("artifact_id")
            if _nonempty(artifact_id):
                seen_ids.add(str(artifact_id))
            if artifact_id in current_ids and artifact.get("status") in TERMINAL_STATUSES:
                binding_reasons = artifact_binding_errors(
                    artifact,
                    expected_head_sha=expected_head_sha,
                    current_binding=current_binding,
                    original_binding=original_binding,
                    enforcement_sensitive=enforcement_sensitive,
                )
                errors.extend(
                    f"review_evidence.artifacts[{index}]: {item}"
                    for item in binding_reasons
                )
                if binding_reasons:
                    continue
                current += 1
                execution_value = artifact.get("review_execution")
                if _nonempty(execution_value):
                    current_executions.add(str(execution_value))
                blockers.extend(result["blocking_reasons"])
        missing_ids = sorted(str(item) for item in current_ids - seen_ids)
        if missing_ids:
            errors.append(
                "review_evidence.current_artifact_ids are missing artifacts: "
                + ", ".join(missing_ids)
            )
        if current == 0:
            errors.append("review_evidence has no current or reusable terminal artifact")
        if len(current_executions) == 1 and execution not in current_executions:
            errors.append(
                "review_evidence.review_execution must be derived from "
                "current or reusable artifacts"
            )
    if not errors:
        satisfied.append("review manifest and artifacts are semantically valid")
    if not blockers:
        satisfied.append("terminal review evidence has no blocking findings")
    return {
        "errors": sorted(set(errors)),
        "blocking_reasons": sorted(set(blockers)),
        "satisfied": satisfied,
    }
