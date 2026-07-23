from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from sensitive_enforcement import (  # noqa: E402
    classify_sensitive_changes,
    evaluate_sensitive_evidence,
)
from spec_revision_evidence import (  # noqa: E402
    spec_artifacts_sha256,
    spec_revision_route_eligible,
    validate_spec_revision_evidence,
)
from specrail_lib import PackConfig, SpecRailError, load_pack  # noqa: E402


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _run(repo, "add", ".")
    _run(
        repo,
        "-c",
        "user.name=SpecRail Test",
        "-c",
        "user.email=specrail@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return _run(repo, "rev-parse", "HEAD")


@pytest.fixture
def spec_revision_case(tmp_path: Path) -> tuple[PackConfig, Path, str, str]:
    repo = tmp_path / "repo"
    packet = repo / "specs" / "GH168"
    packet.mkdir(parents=True)
    for name in ["product.md", "tech.md", "tasks.md"]:
        (packet / name).write_text(f"# initial {name}\n", encoding="utf-8")
    (repo / "checks").mkdir()
    (repo / "checks" / "gate.py").write_text("# gate\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    base = _commit(repo, "base")
    _run(repo, "update-ref", "refs/remotes/origin/main", base)
    _run(
        repo,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        "refs/remotes/origin/main",
    )
    (packet / "product.md").write_text("# revised product\n", encoding="utf-8")
    head = _commit(repo, "revise spec")

    base_config = load_pack(ROOT)
    workflow = deepcopy(base_config.workflow)
    workflow["enforcement"]["sensitive_registry"] = {
        "paths": ["checks/**"],
        "specs": ["specs/GH*/**"],
    }
    return PackConfig(repo, workflow, base_config.states, base_config.labels), repo, base, head


def _classification(
    config: PackConfig,
    repo: Path,
    changed_paths: list[str],
) -> dict[str, object]:
    spec_refs = [
        path for path in changed_paths if path.startswith("specs/")
    ] + ["specs/GH168/tech.md"]
    return classify_sensitive_changes(
        config,
        repo,
        changed_paths,
        sorted(set(spec_refs)),
        source="github_changed_files",
    )


def _approval(
    repo: Path,
    head: str,
    artifact_paths: list[str],
) -> dict[str, object]:
    return {
        "lifecycle_state": "spec_approved",
        "state_source": "label",
        "state_trusted": True,
        "maintainer_actor": "maintainer",
        "approved_at": "2030-07-23T08:00:00+08:00",
        "approval_source": "github_pr_review",
        "approval_url": (
            "https://github.com/majiayu000/specrail/"
            "pull/999#pullrequestreview-1"
        ),
        "commit_oid": head,
        "artifact_paths": artifact_paths,
        "spec_artifacts_sha256": spec_artifacts_sha256(
            repo, head, artifact_paths
        ),
    }


def _evidence(
    repo: Path,
    base: str,
    head: str,
    classification: dict[str, object],
) -> dict[str, object]:
    paths = classification["changed_paths"]
    assert isinstance(paths, list)
    return {
        "repository": "majiayu000/specrail",
        "base_ref": "main",
        "base_sha": base,
        "default_base_ref": "main",
        "default_base_sha": base,
        "head_sha": head,
        "gate_query_head_sha": head,
        "changed_files_count": len(paths),
        "changed_files_sha256": hashlib.sha256(
            json.dumps(paths, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "enforcement_sensitive": True,
        "sensitive_classification": {
            "source": "github_changed_files",
            "changed_paths": paths,
            "spec_refs": classification["spec_refs"],
        },
        "sensitive_route": "spec_revision",
        "spec_approval": _approval(repo, head, paths),
    }


@pytest.mark.parametrize(
    "changed_paths",
    [
        ["specs/GH168/product.md"],
        ["specs/GH168/product.md", "specs/GH168/tech.md", "specs/GH168/tasks.md"],
    ],
)
def test_spec_revision_route_accepts_only_own_packet_subsets(
    spec_revision_case: tuple[PackConfig, Path, str, str],
    changed_paths: list[str],
) -> None:
    config, repo, _base, _head = spec_revision_case
    classification = _classification(config, repo, changed_paths)

    result = spec_revision_route_eligible(config, 168, classification)

    assert result.eligible is True
    assert result.artifact_paths == tuple(sorted(changed_paths))


@pytest.mark.parametrize(
    "changed_paths",
    [
        [],
        ["specs/GH169/product.md"],
        ["specs/GH168/product.md", "README.md"],
        ["specs/GH168/product.md", "checks/gate.py"],
    ],
)
def test_spec_revision_route_rejects_foreign_empty_and_mixed_changes(
    spec_revision_case: tuple[PackConfig, Path, str, str],
    changed_paths: list[str],
) -> None:
    config, repo, _base, _head = spec_revision_case
    classification = _classification(config, repo, changed_paths)

    result = spec_revision_route_eligible(config, 168, classification)

    assert result.eligible is False
    assert result.reason


def test_spec_revision_route_requires_registry_match(
    spec_revision_case: tuple[PackConfig, Path, str, str],
) -> None:
    config, repo, _base, _head = spec_revision_case
    workflow = deepcopy(config.workflow)
    workflow["enforcement"]["sensitive_registry"]["specs"] = ["specs/GH999/**"]
    mismatched = PackConfig(repo, workflow, config.states, config.labels)
    classification = _classification(
        mismatched, repo, ["specs/GH168/product.md"]
    )

    result = spec_revision_route_eligible(mismatched, 168, classification)

    assert result.eligible is False
    assert "registry" in (result.reason or "")


def test_spec_revision_exact_head_evidence_passes(
    spec_revision_case: tuple[PackConfig, Path, str, str],
) -> None:
    config, repo, base, head = spec_revision_case
    classification = _classification(config, repo, ["specs/GH168/product.md"])
    evidence = _evidence(repo, base, head, classification)

    validated = validate_spec_revision_evidence(
        config,
        repo,
        evidence,
        repository="majiayu000/specrail",
        issue=168,
        gated_head_sha=head,
        classification=classification,
    )

    assert validated == evidence["spec_approval"]


@pytest.mark.parametrize(
    ("forgery", "reason"),
    [
        ("review_state", "lifecycle_state"),
        ("old_head", "commit_oid"),
        ("digest", "spec_artifacts_sha256"),
        ("mixed", "must not include approved_spec"),
        ("body_source", "approval_source"),
        ("unknown", "unsupported fields"),
        ("untrusted_state", "state_source=label"),
        ("empty_actor", "maintainer_actor"),
        ("naive_time", "timezone-aware"),
        ("non_github_url", "GitHub HTTPS URL"),
        ("digest_shape", "must be a sha256 digest"),
    ],
)
def test_spec_revision_evidence_fails_closed(
    spec_revision_case: tuple[PackConfig, Path, str, str],
    forgery: str,
    reason: str,
) -> None:
    config, repo, base, head = spec_revision_case
    classification = _classification(config, repo, ["specs/GH168/product.md"])
    evidence = _evidence(repo, base, head, classification)
    approval = evidence["spec_approval"]
    assert isinstance(approval, dict)
    if forgery == "review_state":
        approval["lifecycle_state"] = "spec_review"
    elif forgery == "old_head":
        approval["commit_oid"] = base
    elif forgery == "digest":
        approval["spec_artifacts_sha256"] = "0" * 64
    elif forgery == "mixed":
        evidence["approved_spec"] = {}
    elif forgery == "body_source":
        approval["approval_source"] = "pr_body"
    elif forgery == "unknown":
        approval["agent_claim"] = True
    elif forgery == "untrusted_state":
        approval["state_source"] = "body_hint"
    elif forgery == "empty_actor":
        approval["maintainer_actor"] = ""
    elif forgery == "naive_time":
        approval["approved_at"] = "2030-07-23T08:00:00"
    elif forgery == "non_github_url":
        approval["approval_url"] = "https://example.com/review/1"
    else:
        approval["spec_artifacts_sha256"] = "not-a-digest"

    with pytest.raises(SpecRailError, match=reason):
        validate_spec_revision_evidence(
            config,
            repo,
            evidence,
            repository="majiayu000/specrail",
            issue=168,
            gated_head_sha=head,
            classification=classification,
        )


def test_sensitive_evaluator_routes_eligible_revision(
    spec_revision_case: tuple[PackConfig, Path, str, str],
) -> None:
    config, repo, base, head = spec_revision_case
    classification = _classification(config, repo, ["specs/GH168/product.md"])
    evidence = _evidence(repo, base, head, classification)

    _computed, satisfied, reasons = evaluate_sensitive_evidence(
        config,
        repo,
        evidence,
        expected_source="github_changed_files",
        issue=168,
        expected_base_ref="main",
        expected_base_head=base,
    )

    assert reasons == []
    assert "spec revision approval evidence revalidated" in satisfied


def test_sensitive_evaluator_rejects_self_reported_snapshot_digest(
    spec_revision_case: tuple[PackConfig, Path, str, str],
) -> None:
    config, repo, base, head = spec_revision_case
    classification = _classification(config, repo, ["specs/GH168/product.md"])
    evidence = _evidence(repo, base, head, classification)
    evidence["changed_files_sha256"] = "0" * 64

    _computed, _satisfied, reasons = evaluate_sensitive_evidence(
        config,
        repo,
        evidence,
        expected_source="github_changed_files",
        issue=168,
        expected_base_ref="main",
        expected_base_head=base,
    )

    assert any("changed_files_sha256" in reason for reason in reasons)


def test_non_revision_route_cannot_supply_spec_approval(
    spec_revision_case: tuple[PackConfig, Path, str, str],
) -> None:
    config, repo, base, head = spec_revision_case
    classification = _classification(config, repo, ["checks/gate.py"])
    evidence = _evidence(repo, base, head, classification)

    _computed, _satisfied, reasons = evaluate_sensitive_evidence(
        config,
        repo,
        evidence,
        expected_source="github_changed_files",
        issue=168,
        expected_base_ref="main",
        expected_base_head=base,
    )

    assert any("sensitive_route=approved_spec" in reason for reason in reasons)
    assert any("must not include spec_approval" in reason for reason in reasons)
