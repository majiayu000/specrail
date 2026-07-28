"""Repository-owned sensitive path classification."""

from __future__ import annotations

import fnmatch
import json
import re
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


CLASSIFICATION_SOURCES = {"github_changed_files", "tech_spec"}
PLANNED_CHANGES_MANIFEST_RE = re.compile(
    rb"<!--\s*specrail-planned-changes\s*\n(.*?)\n\s*-->",
    re.DOTALL,
)


def sensitive_registry(config: PackConfig) -> dict[str, list[str]]:
    enforcement = config.workflow.get("enforcement", {})
    if not isinstance(enforcement, dict):
        raise SpecRailError("workflow.yaml: enforcement must be a mapping")
    unknown_enforcement = sorted(set(enforcement) - {"sensitive_registry"})
    if unknown_enforcement:
        raise SpecRailError(
            "workflow.yaml: enforcement contains unsupported fields: "
            + ", ".join(unknown_enforcement)
        )
    registry = enforcement.get("sensitive_registry", {})
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
                label=(
                    "workflow.yaml: enforcement.sensitive_registry."
                    f"{key}[{index}]"
                ),
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
        repo,
        changed_paths,
        label="sensitive_classification.changed_paths",
    )
    specs = normalize_changed_paths(
        repo,
        spec_refs,
        label="sensitive_classification.spec_refs",
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


def parse_planned_changes_manifest(
    content: bytes,
    *,
    label: str = "tech spec",
) -> dict[str, Any]:
    matches = PLANNED_CHANGES_MANIFEST_RE.findall(content)
    if len(matches) != 1:
        raise SpecRailError(
            f"{label} must contain exactly one specrail-planned-changes manifest"
        )
    try:
        manifest = json.loads(matches[0])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecRailError(f"{label} manifest must be valid UTF-8 JSON") from exc
    required = {"version", "issue", "complete", "paths", "spec_refs"}
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise SpecRailError(f"{label} manifest has unsupported or missing fields")
    if (
        not isinstance(manifest.get("version"), int)
        or isinstance(manifest.get("version"), bool)
        or not isinstance(manifest.get("issue"), int)
        or isinstance(manifest.get("issue"), bool)
        or manifest["issue"] < 0
        or not isinstance(manifest.get("complete"), bool)
        or not isinstance(manifest.get("paths"), list)
        or not isinstance(manifest.get("spec_refs"), list)
    ):
        raise SpecRailError(f"{label} manifest field types are invalid")
    return manifest


def classification_from_tech_spec(
    config: PackConfig,
    repo: Path,
    *,
    issue: int,
) -> dict[str, Any]:
    """Classify the current durable tech spec without approval ledgers."""

    tech_path = spec_packet_artifact_paths(config, issue, repo=repo)["tech_spec"]
    try:
        content = resolve_repo_path(
            repo,
            tech_path,
            label="configured tech spec",
        ).read_bytes()
    except OSError as exc:
        raise SpecRailError(f"cannot read configured tech spec {tech_path}: {exc}") from exc
    manifest = parse_planned_changes_manifest(content, label="configured tech.md")
    if manifest.get("version") != 1 or manifest.get("issue") != issue:
        raise SpecRailError("tech spec manifest version/issue binding is invalid")
    if manifest.get("complete") is not True:
        raise SpecRailError("tech spec manifest must declare complete=true")
    if not manifest.get("paths"):
        raise SpecRailError(
            "tech spec manifest paths must be non-empty; "
            "complete=true requires at least one planned path"
        )
    classification = classify_sensitive_changes(
        config,
        repo,
        manifest["paths"],
        manifest["spec_refs"],
        source="tech_spec",
    )
    classification.update(
        {
            "source_path": tech_path,
            "planned_paths_complete": True,
        }
    )
    return classification
