"""Mechanical spec-revision routing and exact-head approval validation."""

from __future__ import annotations

import fnmatch
import hashlib
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sensitive_enforcement import normalize_changed_paths, sensitive_registry
from specrail_lib import PackConfig, SpecRailError, spec_packet_artifact_paths


COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SPEC_APPROVAL_FIELDS = {
    "lifecycle_state",
    "state_source",
    "state_trusted",
    "maintainer_actor",
    "approved_at",
    "approval_source",
    "approval_url",
    "commit_oid",
    "artifact_paths",
    "spec_artifacts_sha256",
}


@dataclass(frozen=True)
class RouteEligibility:
    """A deterministic route decision derived only from trusted classification."""

    eligible: bool
    artifact_paths: tuple[str, ...] = ()
    reason: str | None = None


def _ineligible(reason: str) -> RouteEligibility:
    return RouteEligibility(False, reason=reason)


def spec_revision_route_eligible(
    config: PackConfig,
    issue: int,
    classification: Any,
) -> RouteEligibility:
    """Return whether a trusted PR snapshot is only this issue's spec packet."""

    if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
        return _ineligible("linked issue must be a positive integer")
    if not isinstance(classification, dict):
        return _ineligible("trusted sensitive classification must be an object")
    if classification.get("source") != "github_changed_files":
        return _ineligible("spec revision requires a GitHub changed-file snapshot")

    try:
        changed_paths = normalize_changed_paths(
            config.repo,
            classification.get("changed_paths"),
            label="sensitive_classification.changed_paths",
        )
        matched_paths = normalize_changed_paths(
            config.repo,
            classification.get("matched_paths"),
            label="sensitive_classification.matched_paths",
        )
        matched_specs = normalize_changed_paths(
            config.repo,
            classification.get("matched_specs"),
            label="sensitive_classification.matched_specs",
        )
        registry = sensitive_registry(config)
        configured = spec_packet_artifact_paths(config, issue, repo=config.repo)
    except SpecRailError as exc:
        return _ineligible(str(exc))

    if not changed_paths:
        return _ineligible("spec revision changed-file snapshot must be non-empty")
    allowed = {
        configured["product_spec"],
        configured["tech_spec"],
        configured["task_plan"],
    }
    if not set(changed_paths).issubset(allowed):
        return _ineligible("changed files are not limited to the linked issue spec packet")
    if matched_paths:
        return _ineligible("spec revision must not match enforcement code paths")
    if not registry["specs"] or any(
        not any(fnmatch.fnmatchcase(path, pattern) for pattern in registry["specs"])
        for path in changed_paths
    ):
        return _ineligible("every changed spec must match the trusted spec registry")
    if not set(changed_paths).issubset(matched_specs):
        return _ineligible("matched specs do not cover the changed spec paths")
    if classification.get("enforcement_sensitive") is not True:
        return _ineligible("trusted classification must be enforcement-sensitive")
    return RouteEligibility(True, tuple(changed_paths))


def _git_show(repo: Path, head_sha: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{head_sha}:{path}"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SpecRailError(
            f"spec revision artifact is unavailable at gated head: {path}: "
            f"{detail or 'git command failed'}"
        )
    return completed.stdout


def spec_artifacts_sha256(
    repo: Path,
    head_sha: str,
    artifact_paths: Any,
) -> str:
    """Hash sorted ``path + NUL + sha256(content-at-head)`` records."""

    if not isinstance(head_sha, str) or not COMMIT_RE.fullmatch(head_sha):
        raise SpecRailError("gated head SHA must be a full commit SHA")
    paths = normalize_changed_paths(
        repo, artifact_paths, label="spec_approval.artifact_paths"
    )
    if not paths:
        raise SpecRailError("spec_approval.artifact_paths must be non-empty")
    content_hashes = {
        path: hashlib.sha256(_git_show(repo, head_sha, path)).hexdigest()
        for path in paths
    }
    return spec_artifacts_sha256_from_hashes(content_hashes)


def spec_artifacts_sha256_from_hashes(content_hashes: Any) -> str:
    """Aggregate trusted content digests using the canonical record encoding."""

    if not isinstance(content_hashes, dict) or not content_hashes:
        raise SpecRailError("spec artifact content hashes must be a non-empty object")
    digest = hashlib.sha256()
    for path in sorted(content_hashes):
        if not isinstance(path, str) or not path.strip() or path != path.strip():
            raise SpecRailError("spec artifact content hash path must be normalized")
        content_digest = content_hashes[path]
        if not isinstance(content_digest, str) or not SHA256_RE.fullmatch(content_digest):
            raise SpecRailError(
                f"spec artifact content hash must be sha256 for path: {path}"
            )
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_digest.encode("ascii"))
    return digest.hexdigest()


def _aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _github_review_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.username is None
        and parsed.password is None
        and bool(parsed.path.strip("/"))
    )


def validate_spec_revision_evidence(
    config: PackConfig,
    repo: Path,
    evidence: Any,
    *,
    repository: str,
    issue: int,
    gated_head_sha: str,
    classification: Any,
) -> dict[str, Any]:
    """Validate and return the exact-head maintainer approval audit object."""

    if not isinstance(evidence, dict):
        raise SpecRailError("spec revision evidence must be an object")
    if not isinstance(repository, str) or not repository.strip():
        raise SpecRailError("repository is required for spec revision evidence")
    eligibility = spec_revision_route_eligible(config, issue, classification)
    if not eligibility.eligible:
        raise SpecRailError(
            "spec_revision route is not eligible: "
            + (eligibility.reason or "unknown route failure")
        )
    if evidence.get("sensitive_route") != "spec_revision":
        raise SpecRailError("eligible spec revision requires sensitive_route=spec_revision")
    if evidence.get("approved_spec") is not None:
        raise SpecRailError("spec_revision must not include approved_spec")

    approval = evidence.get("spec_approval")
    if not isinstance(approval, dict):
        raise SpecRailError("spec_approval must be an object")
    unknown = sorted(set(approval) - SPEC_APPROVAL_FIELDS)
    missing = sorted(SPEC_APPROVAL_FIELDS - set(approval))
    if unknown or missing:
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        if unknown:
            details.append("unsupported fields: " + ", ".join(unknown))
        raise SpecRailError("spec_approval is malformed (" + "; ".join(details) + ")")
    if approval.get("lifecycle_state") != "spec_approved":
        raise SpecRailError("spec_approval.lifecycle_state must be spec_approved")
    if approval.get("state_source") != "label" or approval.get("state_trusted") is not True:
        raise SpecRailError("spec_approval requires state_source=label and state_trusted=true")
    actor = approval.get("maintainer_actor")
    if not isinstance(actor, str) or not actor.strip():
        raise SpecRailError("spec_approval.maintainer_actor must be a non-empty string")
    if not _aware_timestamp(approval.get("approved_at")):
        raise SpecRailError(
            "spec_approval.approved_at must be a timezone-aware ISO-8601 timestamp"
        )
    if approval.get("approval_source") != "github_pr_review":
        raise SpecRailError("spec_approval.approval_source must be github_pr_review")
    if not _github_review_url(approval.get("approval_url")):
        raise SpecRailError("spec_approval.approval_url must be an auditable GitHub HTTPS URL")
    commit_oid = approval.get("commit_oid")
    if not isinstance(commit_oid, str) or not COMMIT_RE.fullmatch(commit_oid):
        raise SpecRailError("spec_approval.commit_oid must be a full commit SHA")
    if not isinstance(gated_head_sha, str) or not COMMIT_RE.fullmatch(gated_head_sha):
        raise SpecRailError("gated head SHA must be a full commit SHA")
    if commit_oid.lower() != gated_head_sha.lower():
        raise SpecRailError("spec_approval.commit_oid must match the gated head SHA")
    artifact_paths = normalize_changed_paths(
        repo, approval.get("artifact_paths"), label="spec_approval.artifact_paths"
    )
    if artifact_paths != list(eligibility.artifact_paths):
        raise SpecRailError(
            "spec_approval.artifact_paths must match the eligible changed spec paths"
        )
    reported_digest = approval.get("spec_artifacts_sha256")
    if not isinstance(reported_digest, str) or not SHA256_RE.fullmatch(reported_digest):
        raise SpecRailError("spec_approval.spec_artifacts_sha256 must be a sha256 digest")
    expected_digest = spec_artifacts_sha256(repo, gated_head_sha, artifact_paths)
    if reported_digest != expected_digest:
        raise SpecRailError(
            "spec_approval.spec_artifacts_sha256 does not match gated-head artifacts"
        )
    return dict(approval)
