"""Canonical content bindings shared by SpecRail evidence consumers."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from github_evidence_common import (
    CONTENT_CATEGORIES,
    EvidenceError,
    trusted_ci_coverage,
)
from schema_validation import load_json_schema, validate_instance
from specrail_lib import PackConfig, SpecRailError, resolve_repo_path, spec_packet_root


CONTENT_BINDING_VERSION = 1
CONTENT_BINDING_EVIDENCE_VERSION = 1
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OID_PATTERN = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    return value.strip()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or HASH_PATTERN.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be a lowercase SHA-256 digest")
    return value


def normalize_repo_path(value: Any) -> str:
    path = _nonempty_string(value, "spec file path")
    if "\\" in path or "\0" in path or path.startswith("/"):
        raise EvidenceError("spec file path must be a normalized repo-relative path")
    parsed = PurePosixPath(path)
    if path != parsed.as_posix() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise EvidenceError("spec file path must be a normalized repo-relative path")
    return path


def hash_code_inputs(base_tree_oid: str, normalized_code_patch: bytes) -> str:
    oid = _nonempty_string(base_tree_oid, "base_tree_oid")
    if OID_PATTERN.fullmatch(oid) is None:
        raise EvidenceError("base_tree_oid must be a 40- or 64-character hex object ID")
    if not isinstance(normalized_code_patch, bytes):
        raise EvidenceError("normalized_code_patch must be bytes")
    return _sha256(oid.lower().encode("ascii") + b"\0" + normalized_code_patch)


def hash_spec_files(
    files: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> str:
    entries = files.items() if isinstance(files, Mapping) else files
    normalized: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for raw_path, content in entries:
        path = normalize_repo_path(raw_path)
        if path in seen:
            raise EvidenceError(f"duplicate spec file path: {path}")
        if not isinstance(content, bytes):
            raise EvidenceError(f"spec file content for {path} must be bytes")
        seen.add(path)
        normalized.append((path, content))
    encoded = bytearray()
    for path, content in sorted(normalized):
        encoded.extend(path.encode("utf-8"))
        encoded.extend(b"\0")
        encoded.extend(str(len(content)).encode("ascii"))
        encoded.extend(b"\0")
        encoded.extend(content)
    return _sha256(bytes(encoded))


def hash_pr_metadata(metadata: Mapping[str, Any]) -> str:
    if not isinstance(metadata, Mapping):
        raise EvidenceError("pr_metadata must be an object")
    if any(not isinstance(key, str) for key in metadata):
        raise EvidenceError("pr_metadata keys must be strings")
    try:
        encoded = json.dumps(
            dict(metadata),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceError("pr_metadata must be canonical JSON data") from exc
    return _sha256(encoded)


def build_content_binding(
    head_sha: str,
    base_tree_oid: str,
    normalized_code_patch: bytes,
    spec_files: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
    pr_metadata: Mapping[str, Any],
    collector: str = "github_pr_evidence",
) -> dict[str, Any]:
    head = _nonempty_string(head_sha, "head_sha")
    if OID_PATTERN.fullmatch(head) is None:
        raise EvidenceError("head_sha must be a 40- or 64-character hex object ID")
    base = _nonempty_string(base_tree_oid, "base_tree_oid").lower()
    if OID_PATTERN.fullmatch(base) is None:
        raise EvidenceError("base_tree_oid must be a 40- or 64-character hex object ID")
    producer = _nonempty_string(collector, "collector")
    return {
        "content_binding_version": CONTENT_BINDING_VERSION,
        "snapshot": {
            "head_sha": head.lower(),
            "base_tree_oid": base,
            "algorithm": "sha256",
            "normalization": "specrail-v1",
            "collector": producer,
        },
        "content_hashes": {
            "code_inputs": hash_code_inputs(base, normalized_code_patch),
            "spec_files": hash_spec_files(spec_files),
            "pr_metadata": hash_pr_metadata(pr_metadata),
        },
    }


def validate_content_binding(value: Any) -> dict[str, Any]:
    payload = _object(value, "content binding")
    if payload.get("content_binding_version") != CONTENT_BINDING_VERSION:
        raise EvidenceError("content_binding_version must equal 1")
    snapshot = _object(payload.get("snapshot"), "snapshot")
    if set(snapshot) != {
        "head_sha", "base_tree_oid", "algorithm", "normalization", "collector"
    }:
        raise EvidenceError("snapshot must contain the closed v1 provenance fields")
    head = _nonempty_string(snapshot.get("head_sha"), "snapshot.head_sha")
    base = _nonempty_string(
        snapshot.get("base_tree_oid"), "snapshot.base_tree_oid"
    )
    if OID_PATTERN.fullmatch(head) is None or OID_PATTERN.fullmatch(base) is None:
        raise EvidenceError("snapshot object IDs must be 40- or 64-character hex")
    if snapshot.get("algorithm") != "sha256":
        raise EvidenceError("snapshot.algorithm must equal sha256")
    if snapshot.get("normalization") != "specrail-v1":
        raise EvidenceError("snapshot.normalization must equal specrail-v1")
    collector = _nonempty_string(snapshot.get("collector"), "snapshot.collector")
    if collector != "github_pr_evidence":
        raise EvidenceError(
            "snapshot.collector must equal the trusted github_pr_evidence collector"
        )
    hashes = validate_content_hashes(payload.get("content_hashes"))
    return {
        "content_binding_version": CONTENT_BINDING_VERSION,
        "snapshot": dict(snapshot),
        "content_hashes": hashes,
    }


def build_content_binding_evidence(
    pr: int, binding: Any, artifact_id: str | None = None,
) -> dict[str, Any]:
    """Build a standalone collector sidecar for a trusted PR snapshot."""

    if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
        raise EvidenceError("content binding evidence pr must be a positive integer")
    normalized = validate_content_binding(binding)
    if normalized["snapshot"]["collector"] != "github_pr_evidence":
        raise EvidenceError("content binding evidence requires github_pr_evidence collector")
    identifier = artifact_id or (
        f"content-binding-pr-{pr}-{normalized['snapshot']['head_sha'][:12]}"
    )
    _nonempty_string(identifier, "content binding evidence artifact_id")
    return {
        "version": CONTENT_BINDING_EVIDENCE_VERSION,
        "artifact_id": identifier,
        "pr": pr,
        **normalized,
    }


def load_content_binding_evidence(
    repo: Path,
    reference: Any,
    *,
    expected_pr: int,
    expected_head_sha: str,
) -> dict[str, Any]:
    """Load and authenticate a schema-backed collector sidecar by path and digest."""

    ref = _object(reference, "content_binding_evidence reference")
    if set(ref) != {"artifact_id", "path", "sha256"}:
        raise EvidenceError(
            "content_binding_evidence reference must contain artifact_id, path, and sha256"
        )
    artifact_id = _nonempty_string(ref.get("artifact_id"), "content binding artifact_id")
    raw_path = _nonempty_string(ref.get("path"), "content binding evidence path")
    expected_digest = _hash(ref.get("sha256"), "content binding evidence sha256")
    try:
        evidence_path = resolve_repo_path(repo, raw_path, label="content binding evidence")
        schema_path = resolve_repo_path(
            repo,
            "schemas/content_binding_evidence.schema.json",
            label="content binding evidence schema",
        )
        raw = evidence_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        schema = load_json_schema(schema_path)
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"cannot read content binding evidence: {exc}") from exc
    except (json.JSONDecodeError, SpecRailError) as exc:
        raise EvidenceError(f"invalid content binding evidence: {exc}") from exc
    if _sha256(raw) != expected_digest:
        raise EvidenceError("content binding evidence sha256 does not match its reference")
    if not isinstance(payload, dict) or not isinstance(schema, dict):
        raise EvidenceError("content binding evidence and schema must be objects")
    try:
        validate_instance(schema, payload, "content binding evidence")
    except SpecRailError as exc:
        raise EvidenceError(f"content binding evidence schema validation failed: {exc}") from exc
    if payload.get("artifact_id") != artifact_id:
        raise EvidenceError("content binding evidence artifact_id does not match its reference")
    if payload.get("pr") != expected_pr:
        raise EvidenceError("content binding evidence pr does not match review artifact pr")
    binding = validate_content_binding(payload)
    if binding["snapshot"]["collector"] != "github_pr_evidence":
        raise EvidenceError("content binding evidence must use github_pr_evidence collector")
    if binding["snapshot"]["head_sha"].lower() != expected_head_sha.lower():
        raise EvidenceError("content binding evidence head does not match review artifact head")
    return binding


def validate_content_hashes(value: Any) -> dict[str, str]:
    hashes = _object(value, "content_hashes")
    if set(hashes) != set(CONTENT_CATEGORIES):
        raise EvidenceError("content_hashes keys must equal the v1 category set")
    return {category: _hash(hashes[category], f"content_hashes.{category}")
            for category in CONTENT_CATEGORIES}


def build_component_binding(
    covered_categories: Iterable[str], current_content_hashes: Any
) -> dict[str, Any]:
    covered = list(covered_categories)
    hashes = validate_content_hashes(current_content_hashes)
    component = {
        "content_binding_version": CONTENT_BINDING_VERSION,
        "covered_categories": covered,
        "content_bindings": {
            category: hashes[category]
            for category in covered
            if category in hashes
        },
    }
    validate_component_binding(component)
    return component


def validate_component_binding(
    component: Any,
) -> tuple[tuple[str, ...], dict[str, str]]:
    payload = _object(component, "component binding")
    if payload.get("content_binding_version") != CONTENT_BINDING_VERSION:
        raise EvidenceError("component content_binding_version must equal 1")
    covered = payload.get("covered_categories")
    if not isinstance(covered, list) or not covered:
        raise EvidenceError("covered_categories must be a non-empty list")
    if any(not isinstance(category, str) for category in covered):
        raise EvidenceError("covered_categories entries must be strings")
    if len(set(covered)) != len(covered):
        raise EvidenceError("covered_categories must not contain duplicates")
    if any(category not in CONTENT_CATEGORIES for category in covered):
        raise EvidenceError("covered_categories contains an unknown category")
    bindings = _object(payload.get("content_bindings"), "content_bindings")
    if set(bindings) != set(covered):
        raise EvidenceError("content_bindings keys must equal covered_categories")
    return tuple(covered), {
        category: _hash(bindings[category], f"content_bindings.{category}")
        for category in covered
    }


def content_bindings_match(component: Any, current_content_hashes: Any) -> bool:
    covered, original = validate_component_binding(component)
    current = validate_content_hashes(current_content_hashes)
    return all(original[category] == current[category] for category in covered)


def build_reuse_audit(
    component: Any, current_binding: Any, reason: str,
) -> dict[str, Any]:
    payload = _object(component, "reused component")
    artifact_id = _nonempty_string(payload.get("artifact_id"), "artifact_id")
    original_head = _nonempty_string(
        payload.get("head_sha"), "original component head_sha"
    )
    covered, original = validate_component_binding(payload)
    current = validate_content_binding(current_binding)
    if original_head == current["snapshot"]["head_sha"]:
        raise EvidenceError("reuse audit requires a previous-head component")
    if not content_bindings_match(payload, current["content_hashes"]):
        raise EvidenceError(
            f"reused component {artifact_id} does not match current content bindings"
        )
    return {
        "artifact_id": artifact_id,
        "original_head_sha": original_head,
        "covered_categories": list(covered),
        "original_content_bindings": original,
        "current_content_bindings": {
            category: current["content_hashes"][category] for category in covered
        },
        "collector_provenance": current["snapshot"],
        "reason": _nonempty_string(reason, "reuse reason"),
    }


def _git_bytes(repo: Path, args: list[str], label: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, check=False, capture_output=True,
        )
    except FileNotFoundError as exc:
        raise EvidenceError("git executable was not found in PATH") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise EvidenceError(f"unable to collect {label}: {detail or 'git failed'}")
    return completed.stdout


def git_oid(repo: Path, revision: str, label: str) -> str:
    raw = _git_bytes(repo, ["rev-parse", "--verify", revision], label)
    try:
        return raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{label} returned a non-ASCII object ID") from exc


def checkout_is_exact_head(repo: Path, head_sha: str) -> bool:
    return git_oid(repo, "HEAD", "checkout head") == head_sha


def _collect_spec_files(
    repo: Path, head_sha: str, config: PackConfig,
) -> dict[str, bytes]:
    configured_root = spec_packet_root(config)
    tree_root = configured_root.as_posix()
    raw_paths = _git_bytes(
        repo, ["ls-tree", "-r", "-z", "--name-only", head_sha, "--", tree_root],
        "spec file list",
    )
    files: dict[str, bytes] = {}
    for raw_path in raw_paths.split(b"\0"):
        if not raw_path:
            continue
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceError("spec file path must be valid UTF-8") from exc
        candidate = PurePosixPath(path)
        try:
            relative = candidate.relative_to(configured_root)
        except ValueError:
            continue
        if len(relative.parts) >= 2 and re.fullmatch(r"GH[1-9][0-9]*", relative.parts[0]):
            files[path] = _git_bytes(
                repo, ["show", f"{head_sha}:{path}"], f"spec file {path}",
            )
    return files


def collect_content_binding(
    repo: Path,
    pr_payload: dict[str, Any],
    pr_snapshot: dict[str, Any],
    issue_reference: dict[str, Any] | None,
    config: PackConfig,
) -> dict[str, Any]:
    head_sha = _nonempty_string(pr_payload.get("headRefOid"), "headRefOid")
    if not checkout_is_exact_head(repo, head_sha):
        raise EvidenceError("content binding requires an exact-head repository checkout")
    base_sha = _nonempty_string(pr_snapshot.get("base_sha"), "base_sha")
    base_tree_oid = git_oid(repo, f"{base_sha}^{{tree}}", "base tree")
    code_patch = _git_bytes(
        repo,
        [
            "diff", "--binary", "--full-index", "--no-color", "--no-ext-diff",
            "--no-textconv", "--no-renames", base_sha, head_sha, "--", ".",
            f":(exclude){spec_packet_root(config).as_posix().rstrip('/')}/GH*/**",
        ],
        "normalized code patch",
    )
    base_ref = _nonempty_string(pr_payload.get("baseRefName"), "baseRefName")
    if base_ref != pr_snapshot.get("base_ref"):
        raise EvidenceError("PR view and file snapshot base ref disagree")
    body = pr_payload.get("body")
    if not isinstance(body, str):
        raise EvidenceError("body must be a string for content binding")
    metadata = {
        "title": _nonempty_string(pr_payload.get("title"), "title"),
        "body": body,
        "base_ref": base_ref,
        "head_ref": _nonempty_string(pr_payload.get("headRefName"), "headRefName"),
        "issue_relation": issue_reference,
    }
    return build_content_binding(
        head_sha,
        base_tree_oid,
        code_patch,
        _collect_spec_files(repo, head_sha, config),
        metadata,
    )


def load_versioned_pr_evidence(repo: Path, raw_path: str) -> dict[str, Any]:
    """Load a schema-backed prior collector wrapper from inside the repository."""

    evidence_path = resolve_repo_path(repo, raw_path, label="reused PR evidence")
    schema_path = resolve_repo_path(
        repo, "schemas/pr_review_gate.schema.json", label="PR evidence schema"
    )
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        schema = load_json_schema(schema_path)
    except OSError as exc:
        raise EvidenceError(f"cannot read reused PR evidence: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"reused PR evidence is invalid JSON: {exc.msg}") from exc
    except SpecRailError as exc:
        raise EvidenceError(f"reused PR evidence schema is invalid: {exc}") from exc
    if not isinstance(evidence, dict) or not isinstance(schema, dict):
        raise EvidenceError("reused PR evidence and schema must be objects")
    try:
        validate_instance(schema, evidence, "reused PR evidence")
    except SpecRailError as exc:
        raise EvidenceError(f"reused PR evidence schema validation failed: {exc}") from exc
    binding = validate_content_binding(evidence)
    if evidence.get("head_sha") != binding["snapshot"]["head_sha"]:
        raise EvidenceError(
            "reused PR evidence head_sha must match its content binding snapshot"
        )
    return evidence


def merge_reusable_ci_checks(
    current_checks: list[dict[str, Any]],
    prior_evidence: dict[str, Any] | None,
    current_binding: dict[str, Any] | None,
    config: PackConfig | None,
) -> list[dict[str, Any]]:
    if prior_evidence is None:
        return current_checks
    if current_binding is None:
        raise EvidenceError("reusing CI evidence requires v1 content binding")
    prior_binding = validate_content_binding(prior_evidence)
    current = validate_content_binding(current_binding)
    if (
        prior_binding["snapshot"]["head_sha"]
        == current["snapshot"]["head_sha"]
    ):
        raise EvidenceError(
            "reused PR evidence snapshot must come from a previous head"
        )
    prior_checks = prior_evidence.get("checks")
    if not isinstance(prior_checks, list):
        raise EvidenceError("reused PR evidence checks must be a list")
    merged = list(current_checks)
    indexes = {
        item.get("name"): index for index, item in enumerate(merged)
        if isinstance(item.get("name"), str)
    }
    for component in prior_checks:
        if not isinstance(component, dict):
            raise EvidenceError("reused PR evidence check must be an object")
        name = component.get("name")
        coverage = trusted_ci_coverage(config, name) if isinstance(name, str) else None
        if coverage is None:
            continue
        current_index = indexes.get(name)
        if current_index is not None:
            live = merged[current_index]
            if live.get("status") == "COMPLETED":
                continue
        covered, _ = validate_component_binding(component)
        if covered != coverage:
            raise EvidenceError(f"reused CI check {name} has untrusted coverage")
        if component.get("head_sha") != prior_binding["snapshot"]["head_sha"]:
            raise EvidenceError(f"reused CI check {name} head does not match its snapshot")
        if not content_bindings_match(component, prior_binding["content_hashes"]):
            raise EvidenceError(f"reused CI check {name} bindings do not match prior snapshot")
        if not content_bindings_match(component, current["content_hashes"]):
            raise EvidenceError(f"reused CI check {name} bindings do not match current snapshot")
        if current_index is None:
            indexes[name] = len(merged)
            merged.append(dict(component))
        else:
            merged[current_index] = dict(component)
    return merged


def collect_reuse_audits(
    checks: list[dict[str, Any]],
    review_evidence: dict[str, Any] | None,
    current_binding: dict[str, Any],
    current_head_sha: str,
) -> list[dict[str, Any]]:
    components = list(checks)
    if review_evidence is not None:
        current_ids = review_evidence.get("current_artifact_ids")
        artifacts = review_evidence.get("artifacts")
        if isinstance(current_ids, list) and isinstance(artifacts, list):
            components.extend(
                item for item in artifacts
                if isinstance(item, dict) and item.get("artifact_id") in current_ids
            )
    return [
        build_reuse_audit(
            component,
            current_binding,
            "covered content categories match the current trusted snapshot",
        )
        for component in components
        if component.get("head_sha") != current_head_sha
        and "content_binding_version" in component
    ]
