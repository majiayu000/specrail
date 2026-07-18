from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from route_gate_test_support import (
    ROOT,
    run_route_gate,
    sensitive_route_evidence,
    write_duplicate_evidence,
    write_sensitive_pack,
)


def test_route_gate_revalidates_sensitive_registry_and_approved_spec(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    duplicate_evidence = write_duplicate_evidence(tmp_path)

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(duplicate_evidence),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"
    assert payload["sensitive_classification"]["matched_paths"] == [
        "checks/route_gate.py"
    ]


def test_route_gate_blocks_complete_manifest_with_empty_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo, planned_paths=[])
    evidence = sensitive_route_evidence(repo, head)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("manifest paths must be non-empty" in item for item in payload["reasons"])


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("base_ref", "forged", "reported base_ref"),
        ("base_sha", "f" * 40, "reported base_sha"),
    ],
)
def test_route_gate_blocks_forged_caller_base_identity(
    tmp_path: Path,
    field: str,
    value: str,
    reason: str,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    evidence[field] = value
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any(reason in item for item in payload["reasons"])


def test_route_gate_blocks_missing_origin_head_even_with_adapter_default(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--delete", "refs/remotes/origin/HEAD"],
        check=True,
    )
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("origin/HEAD is missing" in item for item in payload["reasons"])


def test_route_gate_blocks_non_origin_default_symbolic_ref(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    subprocess.run(
        [
            "git", "-C", str(repo), "symbolic-ref",
            "refs/remotes/origin/HEAD", "refs/remotes/upstream/main",
        ],
        check=True,
    )
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any("trusted default branch" in item for item in payload["reasons"])


@pytest.mark.parametrize(
    ("field", "value"),
    [("default_base_ref", "forged"), ("default_base_sha", "f" * 40)],
)
def test_route_gate_blocks_forged_adapter_default_identity(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    evidence[field] = value
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any("default base" in item for item in payload["reasons"])


def test_route_gate_blocks_spec_source_that_predates_incorporation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    pre_spec = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD^"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    path = "specs/GH999/product.md"
    evidence["approved_spec"]["spec_revisions"][path]["source_commit_sha"] = pre_spec
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any("approved spec source" in item for item in payload["reasons"])


def test_route_gate_blocks_approved_spec_changed_on_current_default_base(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    (repo / "specs" / "GH999" / "product.md").write_text(
        "GitHub issue: `#999`\nchanged after approval\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid", "commit", "-qm", "spec drift",
        ],
        check=True,
    )
    current_base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", current_base],
        check=True,
    )
    evidence["base_sha"] = current_base
    evidence["default_base_sha"] = current_base
    evidence["approved_spec"]["default_base_sha"] = current_base
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any("changed since approval" in item for item in payload["reasons"])


@pytest.mark.parametrize("forgery", ["body_hint", "changed_hash", "false"])
def test_route_gate_blocks_forged_or_conflicting_sensitive_evidence(
    tmp_path: Path,
    forgery: str,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    if forgery == "body_hint":
        evidence["approved_spec"]["state_source"] = "body_hint"
        evidence["approved_spec"]["state_trusted"] = False
    elif forgery == "changed_hash":
        path = "specs/GH999/product.md"
        evidence["approved_spec"]["content_hashes"][path] = "0" * 64
    else:
        evidence["enforcement_sensitive"] = False
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert "sensitive_enforcement" in payload["missing"]
    assert "missing_evidence_field:sensitive_enforcement" in {
        item["item_id"] for item in payload["rejection_items"]
    }


@pytest.mark.parametrize("caller_paths", [[], ["README.md"]])
def test_route_gate_ignores_caller_planned_paths(
    tmp_path: Path,
    caller_paths: list[str],
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    evidence["sensitive_classification"]["changed_paths"] = caller_paths
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 0
    assert payload["sensitive_classification"]["changed_paths"] == [
        "checks/route_gate.py"
    ]
    assert payload["sensitive_classification"]["planned_paths_complete"] is True
    assert payload["sensitive_classification"]["source_path"] == (
        "specs/GH999/tech.md"
    )
    assert len(payload["sensitive_classification"]["source_content_hash"]) == 64


def test_route_gate_blocks_complete_manifest_with_no_planned_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo, planned_paths=[])
    evidence = sensitive_route_evidence(repo, head)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("at least one planned path" in reason for reason in payload["reasons"])


def test_route_gate_allows_preimplement_without_tasks_md(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo)
    evidence = sensitive_route_evidence(repo, head)
    assert not (repo / "specs" / "GH999" / "tasks.md").exists()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"


@pytest.mark.parametrize("manifest_count", [0, 2])
def test_route_gate_blocks_missing_or_duplicate_tech_manifest(
    tmp_path: Path, manifest_count: int
) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo, manifest_count=manifest_count)
    evidence = sensitive_route_evidence(repo, head)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any("exactly one" in reason for reason in payload["reasons"])


def test_route_gate_blocks_unfilled_tech_template_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo, render_manifest=False)
    evidence = sensitive_route_evidence(repo, head)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert any("version/issue binding" in reason for reason in payload["reasons"])


def test_route_gate_blocks_traversal_in_trusted_tech_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = write_sensitive_pack(repo, ["../escape"])
    evidence = sensitive_route_evidence(repo, head)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route", "implement", "--issue", "999", "--evidence",
        str(evidence_path), "--duplicate-evidence", str(write_duplicate_evidence(tmp_path)),
        "--mode", "required", repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("stay within" in reason for reason in payload["reasons"])
