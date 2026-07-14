"""Trusted path-derived enforcement classification and approved-spec checks."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from specrail_lib import (
    PackConfig,
    SpecRailError,
    resolve_path,
    resolve_repo_path,
    spec_packet_artifact_paths,
    validated_repo_relative_path,
)


CLASSIFICATION_SOURCES = {"github_changed_files", "task_plan"}
APPROVED_SPEC_FIELDS = {
    "repository",
    "issue",
    "spec_paths",
    "content_hashes",
    "approved_base_sha",
    "approved_at",
    "maintainer_actor",
    "state_source",
    "state_trusted",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
TASK_PLAN_MANIFEST_RE = re.compile(
    rb"<!--\s*specrail-planned-changes\s*\n(.*?)\n\s*-->", re.DOTALL
)


def sensitive_registry(config: PackConfig) -> dict[str, list[str]]:
    enforcement = config.workflow.get("enforcement", {})
    if enforcement is None:
        enforcement = {}
    if not isinstance(enforcement, dict):
        raise SpecRailError("workflow.yaml: enforcement must be a mapping")
    registry = enforcement.get("sensitive_registry", {})
    if registry is None:
        registry = {}
    if not isinstance(registry, dict):
        raise SpecRailError(
            "workflow.yaml: enforcement.sensitive_registry must be a mapping"
        )
    unknown = sorted(set(registry) - {"paths", "specs"})
    if unknown:
        raise SpecRailError(
            "workflow.yaml: enforcement.sensitive_registry contains unsupported "
            f"fields: {', '.join(unknown)}"
        )

    normalized: dict[str, list[str]] = {"paths": [], "specs": []}
    for key in normalized:
        values = registry.get(key, [])
        if not isinstance(values, list):
            raise SpecRailError(
                f"workflow.yaml: enforcement.sensitive_registry.{key} must be a list"
            )
        for index, raw in enumerate(values, start=1):
            if not isinstance(raw, str) or not raw.strip():
                raise SpecRailError(
                    "workflow.yaml: enforcement.sensitive_registry."
                    f"{key}[{index}] must be a non-empty string"
                )
            pattern = validated_repo_relative_path(
                raw.strip(),
                label=f"workflow.yaml: enforcement.sensitive_registry.{key}[{index}]",
            ).as_posix()
            if pattern in {"", "."}:
                raise SpecRailError(
                    f"workflow.yaml: enforcement.sensitive_registry.{key}[{index}] "
                    "must identify a repository path"
                )
            normalized[key].append(pattern)
    return normalized


def validate_sensitive_registry(config: PackConfig) -> list[str]:
    try:
        sensitive_registry(config)
    except SpecRailError as exc:
        return [str(exc)]
    return []


def _trusted_path(repo: Path, raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise SpecRailError(f"{label} must be a non-empty string")
    relative = validated_repo_relative_path(raw.strip(), label=label)
    resolved_repo = resolve_path(repo, label="repository")
    resolved = resolve_repo_path(repo, relative, label=label)
    expected = resolved_repo.joinpath(*relative.parts)
    if resolved != expected:
        raise SpecRailError(f"{label} must preserve its repository path identity")
    return relative.as_posix()


def normalize_changed_paths(repo: Path, values: Any, *, label: str) -> list[str]:
    if not isinstance(values, list):
        raise SpecRailError(f"{label} must be a list")
    normalized = [
        _trusted_path(repo, raw, f"{label}[{index}]")
        for index, raw in enumerate(values, start=1)
    ]
    if len(set(normalized)) != len(normalized):
        raise SpecRailError(f"{label} must not contain duplicate normalized paths")
    return sorted(normalized)


def classify_sensitive_changes(
    config: PackConfig,
    repo: Path,
    changed_paths: Any,
    spec_refs: Any,
    *,
    source: str,
) -> dict[str, Any]:
    if source not in CLASSIFICATION_SOURCES:
        raise SpecRailError(
            "sensitive_classification.source must be one of: "
            + ", ".join(sorted(CLASSIFICATION_SOURCES))
        )
    registry = sensitive_registry(config)
    paths = normalize_changed_paths(
        repo, changed_paths, label="sensitive_classification.changed_paths"
    )
    specs = normalize_changed_paths(
        repo, spec_refs, label="sensitive_classification.spec_refs"
    )
    matched_paths = sorted(
        path
        for path in paths
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in registry["paths"])
    )
    matched_specs = sorted(
        path
        for path in specs
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in registry["specs"])
    )
    return {
        "source": source,
        "changed_paths": paths,
        "spec_refs": specs,
        "matched_paths": matched_paths,
        "matched_specs": matched_specs,
        "registry_configured": bool(registry["paths"] or registry["specs"]),
        "enforcement_sensitive": bool(matched_paths or matched_specs),
    }


def _git(repo: Path, args: list[str], label: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SpecRailError(f"{label}: {detail or 'git command failed'}")
    return completed.stdout


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def trusted_default_base(repo: Path) -> tuple[str, str]:
    """Resolve the local, fetch-backed origin default branch and commit."""

    symbolic_ref = _git(
        repo,
        ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        "trusted default branch",
    ).decode("utf-8", errors="strict").strip()
    prefix = "refs/remotes/origin/"
    if not symbolic_ref.startswith(prefix):
        raise SpecRailError(
            "trusted default branch origin/HEAD must target refs/remotes/origin/<branch>"
        )
    branch = symbolic_ref.removeprefix(prefix)
    if not branch or branch == "HEAD":
        raise SpecRailError("trusted default branch origin/HEAD target is ambiguous")
    sha = _git(
        repo,
        ["rev-parse", "--verify", f"{symbolic_ref}^{{commit}}"],
        "trusted default branch commit",
    ).decode("utf-8", errors="strict").strip()
    if not COMMIT_RE.fullmatch(sha):
        raise SpecRailError("trusted default branch did not resolve to a full commit SHA")
    return branch, sha.lower()


def build_approved_spec_evidence(
    config: PackConfig,
    repo: Path,
    *,
    repository: str,
    issue: int,
    approved_base_sha: str,
    approved_at: str,
    maintainer_actor: str,
) -> dict[str, Any]:
    if not isinstance(approved_base_sha, str) or not COMMIT_RE.fullmatch(
        approved_base_sha
    ):
        raise SpecRailError("approved_base_sha must be a full commit SHA")
    paths = spec_packet_artifact_paths(config, issue, repo=repo)
    spec_paths = [paths["product_spec"], paths["tech_spec"]]
    hashes = {
        path: _hash_bytes(
            _git(
                repo,
                ["show", f"{approved_base_sha}:{path}"],
                f"approved spec at approval base {path}",
            )
        )
        for path in spec_paths
    }
    evidence = {
        "repository": repository,
        "issue": issue,
        "spec_paths": spec_paths,
        "content_hashes": hashes,
        "approved_base_sha": approved_base_sha,
        "approved_at": approved_at,
        "maintainer_actor": maintainer_actor,
        "state_source": "label",
        "state_trusted": True,
    }
    validate_approved_spec_evidence(
        config,
        repo,
        evidence,
        repository=repository,
        issue=issue,
    )
    return evidence


def _aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SpecRailError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpecRailError(
            f"{label} must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise SpecRailError(f"{label} must be a timezone-aware ISO-8601 timestamp")
    return parsed


def validate_approved_spec_evidence(
    config: PackConfig,
    repo: Path,
    evidence: Any,
    *,
    repository: str,
    issue: int,
) -> None:
    if not isinstance(evidence, dict):
        raise SpecRailError("approved_spec must be an object")
    unknown = sorted(set(evidence) - APPROVED_SPEC_FIELDS)
    if unknown:
        raise SpecRailError(
            "approved_spec contains unsupported fields: " + ", ".join(unknown)
        )
    if evidence.get("repository") != repository:
        raise SpecRailError("approved_spec.repository must match repository")
    if evidence.get("issue") != issue:
        raise SpecRailError("approved_spec.issue must match linked issue")
    if evidence.get("state_source") != "label" or evidence.get("state_trusted") is not True:
        raise SpecRailError(
            "approved_spec requires state_source=label and state_trusted=true"
        )
    if not isinstance(evidence.get("maintainer_actor"), str) or not evidence["maintainer_actor"].strip():
        raise SpecRailError("approved_spec.maintainer_actor must be a non-empty string")
    if not _aware_timestamp(evidence.get("approved_at")):
        raise SpecRailError(
            "approved_spec.approved_at must be a timezone-aware ISO-8601 timestamp"
        )

    _timestamp(evidence.get("approved_at"), "approved_spec.approved_at")
    approved_base_sha = evidence.get("approved_base_sha")
    if not isinstance(approved_base_sha, str) or not COMMIT_RE.fullmatch(
        approved_base_sha
    ):
        raise SpecRailError("approved_spec.approved_base_sha must be a full commit SHA")
    _git(
        repo,
        ["cat-file", "-e", f"{approved_base_sha}^{{commit}}"],
        "approved spec approval base",
    )
    _trusted_base_ref, trusted_base_sha = trusted_default_base(repo)
    _git(
        repo,
        ["merge-base", "--is-ancestor", approved_base_sha, trusted_base_sha],
        "approved spec approval base must be an ancestor of the trusted default base",
    )

    configured = spec_packet_artifact_paths(config, issue, repo=repo)
    expected_paths = [configured["product_spec"], configured["tech_spec"]]
    paths = normalize_changed_paths(
        repo, evidence.get("spec_paths"), label="approved_spec.spec_paths"
    )
    if paths != sorted(expected_paths):
        raise SpecRailError("approved_spec.spec_paths must match configured product and tech specs")
    hashes = evidence.get("content_hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(expected_paths):
        raise SpecRailError("approved_spec.content_hashes must cover every approved spec path")
    for path in expected_paths:
        digest = hashes.get(path)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise SpecRailError(f"approved_spec.content_hashes[{path}] must be a sha256 hex digest")
        approved_digest = _hash_bytes(
            _git(
                repo,
                ["show", f"{approved_base_sha}:{path}"],
                f"approved spec at approval base {path}",
            )
        )
        current_base_digest = _hash_bytes(
            _git(
                repo,
                ["show", f"{trusted_base_sha}:{path}"],
                f"approved spec at current trusted base {path}",
            )
        )
        if digest != approved_digest or digest != current_base_digest:
            raise SpecRailError(
                f"approved spec content changed since approval or hash mismatched: {path}"
            )


def classification_from_task_plan(
    config: PackConfig,
    repo: Path,
    *,
    issue: int,
    base_sha: str,
) -> dict[str, Any]:
    if not COMMIT_RE.fullmatch(base_sha):
        raise SpecRailError("task plan base_sha must be a full commit SHA")
    task_path = spec_packet_artifact_paths(config, issue, repo=repo)["task_plan"]
    base_content = _git(
        repo, ["show", f"{base_sha}:{task_path}"], "trusted task plan"
    )
    current_path = resolve_repo_path(repo, task_path, label="trusted task plan")
    try:
        current_content = current_path.read_bytes()
    except OSError as exc:
        raise SpecRailError(f"cannot read trusted task plan: {exc}") from exc
    if current_content != base_content:
        raise SpecRailError("trusted task plan changed after the base snapshot")
    matches = TASK_PLAN_MANIFEST_RE.findall(base_content)
    if len(matches) != 1:
        raise SpecRailError(
            "configured tasks.md must contain exactly one specrail-planned-changes manifest"
        )
    try:
        manifest = json.loads(matches[0])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecRailError("task plan manifest must be valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "version", "issue", "complete", "paths", "spec_refs"
    }:
        raise SpecRailError("task plan manifest has unsupported or missing fields")
    if manifest.get("version") != 1 or manifest.get("issue") != issue:
        raise SpecRailError("task plan manifest version/issue binding is invalid")
    if manifest.get("complete") is not True:
        raise SpecRailError("task plan manifest must declare complete=true")
    classification = classify_sensitive_changes(
        config,
        repo,
        manifest.get("paths"),
        manifest.get("spec_refs"),
        source="task_plan",
    )
    classification.update(
        {
            "source_path": task_path,
            "source_content_hash": _hash_bytes(base_content),
            "source_base_sha": base_sha,
            "planned_paths_complete": True,
        }
    )
    return classification


def evaluate_sensitive_evidence(
    config: PackConfig,
    repo: Path,
    evidence: dict[str, Any],
    *,
    expected_source: str,
    issue: int | None,
    expected_base_ref: str | None = None,
    expected_base_head: str | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Return computed classification, satisfied facts, and blocking reasons."""

    reasons: list[str] = []
    satisfied: list[str] = []
    declaration = evidence.get("enforcement_sensitive")
    if declaration is not None and not isinstance(declaration, bool):
        reasons.append("enforcement_sensitive declaration must be a boolean")
    registry = sensitive_registry(config)
    classification_input = evidence.get("sensitive_classification")
    needs_classification = bool(registry["paths"] or registry["specs"])
    classification: dict[str, Any] | None = None
    if classification_input is None:
        if needs_classification:
            reasons.append("configured sensitive registry requires trusted path evidence")
    elif not isinstance(classification_input, dict):
        reasons.append("sensitive_classification must be an object")
    else:
        unknown = sorted(
            set(classification_input)
            - {
                "source", "changed_paths", "spec_refs", "matched_paths",
                "matched_specs", "registry_configured", "enforcement_sensitive",
            }
        )
        if unknown:
            reasons.append(
                "sensitive_classification contains unsupported fields: "
                + ", ".join(unknown)
            )
        try:
            if classification_input.get("source") != expected_source:
                raise SpecRailError(
                    f"sensitive_classification.source must be {expected_source}"
                )
            classification = classify_sensitive_changes(
                config,
                repo,
                classification_input.get("changed_paths"),
                classification_input.get("spec_refs", []),
                source=expected_source,
            )
            if expected_source == "github_changed_files":
                expected_digest = hashlib.sha256(
                    json.dumps(
                        classification["changed_paths"], separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest()
                if evidence.get("changed_files_count") != len(
                    classification["changed_paths"]
                ):
                    reasons.append(
                        "changed_files_count conflicts with complete path snapshot"
                    )
                if evidence.get("changed_files_sha256") != expected_digest:
                    reasons.append(
                        "changed_files_sha256 conflicts with complete path snapshot"
                    )
            for field in ["matched_paths", "matched_specs", "registry_configured", "enforcement_sensitive"]:
                if field in classification_input and classification_input[field] != classification[field]:
                    reasons.append(
                        f"sensitive_classification.{field} conflicts with trusted registry calculation"
                    )
        except SpecRailError as exc:
            reasons.append(str(exc))

    computed_sensitive = bool(
        classification and classification["enforcement_sensitive"]
    )
    if computed_sensitive and declaration is not True:
        reasons.append(
            "sensitive registry matched but enforcement_sensitive declaration is not true"
        )
    requires_approval = computed_sensitive or declaration is True
    if requires_approval:
        repository = evidence.get("repository")
        trusted_base_ref: str | None = None
        trusted_base_sha: str | None = None
        try:
            trusted_base_ref, trusted_base_sha = trusted_default_base(repo)
        except SpecRailError as exc:
            reasons.append(str(exc))
        if trusted_base_ref is not None and expected_base_ref != trusted_base_ref:
            reasons.append(
                "reported base_ref does not match the trusted origin default branch"
            )
        if trusted_base_sha is not None and expected_base_head != trusted_base_sha:
            reasons.append(
                "reported base_sha does not match the trusted origin default branch"
            )
        if expected_source == "github_changed_files":
            try:
                checkout_head = _git(
                    repo,
                    ["rev-parse", "--verify", "HEAD^{commit}"],
                    "sensitive PR gate checkout head",
                ).decode("utf-8", errors="strict").strip()
            except SpecRailError as exc:
                reasons.append(str(exc))
            else:
                evidence_head = evidence.get("head_sha")
                query_head = evidence.get("gate_query_head_sha")
                if (
                    not isinstance(evidence_head, str)
                    or not COMMIT_RE.fullmatch(evidence_head)
                    or query_head != evidence_head
                    or checkout_head != evidence_head
                ):
                    reasons.append(
                        "sensitive PR gate requires local checkout HEAD, head_sha, "
                        "and gate_query_head_sha to match"
                    )
        if not isinstance(repository, str) or not repository.strip():
            reasons.append("repository is required for enforcement-sensitive evidence")
        elif issue is None:
            reasons.append("linked issue is required for enforcement-sensitive evidence")
        else:
            try:
                validate_approved_spec_evidence(
                    config,
                    repo,
                    evidence.get("approved_spec"),
                    repository=repository.strip(),
                    issue=issue,
                )
                satisfied.append("approved spec evidence revalidated")
            except SpecRailError as exc:
                reasons.append(str(exc))
    elif evidence.get("approved_spec") is not None:
        reasons.append("approved_spec was provided without enforcement_sensitive=true")

    if classification:
        satisfied.append(
            "sensitive registry classification: "
            + ("matched" if computed_sensitive else "not matched")
        )
    return classification, satisfied, reasons
