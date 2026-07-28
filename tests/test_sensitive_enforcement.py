from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from sensitive_enforcement import (  # noqa: E402
    classification_from_tech_spec,
    classify_sensitive_changes,
    parse_planned_changes_manifest,
    sensitive_registry,
)
from specrail_lib import PackConfig, SpecRailError  # noqa: E402


def config(repo: Path) -> PackConfig:
    return PackConfig(
        repo=repo,
        workflow={
            "enforcement": {
                "sensitive_registry": {
                    "paths": ["auth/**", "checks/**"],
                    "specs": ["specs/security/**"],
                }
            }
        },
        states={},
        labels={},
    )


def test_sensitive_registry_rejects_unknown_fields(tmp_path: Path) -> None:
    pack = config(tmp_path)
    pack.workflow["enforcement"]["sensitive_registry"]["alias"] = []

    with pytest.raises(SpecRailError, match="unsupported fields"):
        sensitive_registry(pack)


def test_classification_is_path_derived_and_sorted(tmp_path: Path) -> None:
    result = classify_sensitive_changes(
        config(tmp_path),
        tmp_path,
        ["docs/readme.md", "auth/session.py"],
        ["specs/security/oauth.md"],
        source="github_changed_files",
    )

    assert result["enforcement_sensitive"] is True
    assert result["matched_paths"] == ["auth/session.py"]
    assert result["matched_specs"] == ["specs/security/oauth.md"]


def test_classification_rejects_traversal_and_duplicates(tmp_path: Path) -> None:
    with pytest.raises(SpecRailError):
        classify_sensitive_changes(
            config(tmp_path),
            tmp_path,
            ["../secret"],
            [],
            source="github_changed_files",
        )
    with pytest.raises(SpecRailError, match="duplicate"):
        classify_sensitive_changes(
            config(tmp_path),
            tmp_path,
            ["auth/a.py", "auth/a.py"],
            [],
            source="github_changed_files",
        )


def manifest(issue: int = 8, complete: bool = True) -> bytes:
    value = {
        "version": 1,
        "issue": issue,
        "complete": complete,
        "paths": ["checks/route_gate.py"],
        "spec_refs": [],
    }
    return (
        "<!-- specrail-planned-changes\n"
        + json.dumps(value, separators=(",", ":"))
        + "\n-->"
    ).encode()


def test_manifest_requires_exactly_one_closed_contract() -> None:
    assert parse_planned_changes_manifest(manifest())["issue"] == 8
    with pytest.raises(SpecRailError, match="exactly one"):
        parse_planned_changes_manifest(b"")
    with pytest.raises(SpecRailError, match="unsupported or missing"):
        parse_planned_changes_manifest(
            manifest().replace(b'"spec_refs":[]', b'"spec_refs":[],"extra":true')
        )


def test_classification_from_current_tech_spec(tmp_path: Path) -> None:
    packet = tmp_path / "specs" / "GH8"
    packet.mkdir(parents=True)
    (packet / "tech.md").write_bytes(manifest())
    pack = config(tmp_path)
    pack.workflow["artifacts"] = {
        "spec_packet": "specs/GH{issue_number}",
        "product_spec": "specs/GH{issue_number}/product.md",
        "tech_spec": "specs/GH{issue_number}/tech.md",
        "task_plan": "specs/GH{issue_number}/tasks.md",
    }

    result = classification_from_tech_spec(pack, tmp_path, issue=8)

    assert result["enforcement_sensitive"] is True
    assert result["source_path"] == "specs/GH8/tech.md"
