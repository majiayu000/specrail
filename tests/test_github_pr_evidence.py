from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from github_evidence_common import EvidenceError
from github_pr_evidence import build_evidence, collect_evidence
from specrail_lib import PackConfig


def pr_payload(head: str = "a" * 40) -> dict[str, object]:
    return {
        "number": 42,
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": head,
        "baseRefOid": "b" * 40,
        "mergeStateStatus": "CLEAN",
        "body": "Fixes #208",
        "closingIssuesReferences": [{"number": 208}],
        "statusCheckRollup": [
            {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}
        ],
        "files": [{"path": "src/z.py"}, {"path": "src/a.py"}],
    }


def review(head: str = "a" * 40, profile: str = "standard") -> dict[str, object]:
    return {
        "artifact_id": "review-42",
        "contract_version": 3,
        "repository": "acme/widgets",
        "pr": 42,
        "profile": profile,
        "head_sha": head,
        "review_source": "independent_lane",
        "round": 1,
        "mode": "full",
        "verdict": "clean",
        "body": "## Summary\nComplete review.\n\n## Verdict\nClean.",
        "findings": [],
    }


def config(repo: Path, patterns: list[str] | None = None) -> PackConfig:
    return PackConfig(
        repo=repo,
        workflow={
            "enforcement": {
                "sensitive_registry": {"paths": patterns or [], "specs": []}
            }
        },
        states={},
        labels={},
    )


def test_build_evidence_is_compact_and_deterministic(tmp_path: Path) -> None:
    result = build_evidence(
        pr_payload(),
        repository="acme/widgets",
        profile="standard",
        gate_invocation_id="gate-1",
        review=review(),
        expected_issue=208,
        repo=tmp_path,
        config=config(tmp_path),
    )

    assert result["contract_version"] == 3
    assert result["linked_issue"] == 208
    assert result["changed_files"] == ["src/a.py", "src/z.py"]
    assert result["changed_files_count"] == 2
    assert result["checks"][0]["head_sha"] == "a" * 40
    assert result["profile"] == "standard"
    assert not {
        "review_threads",
        "pr_tier",
        "content_binding_version",
        "runtime_checkpoint",
    } & set(result)


def test_sensitive_paths_automatically_select_heavy(tmp_path: Path) -> None:
    result = build_evidence(
        pr_payload(),
        repository="acme/widgets",
        profile="fastlane",
        gate_invocation_id="gate-1",
        review=review(profile="heavy"),
        expected_issue=208,
        repo=tmp_path,
        config=config(tmp_path, ["src/**"]),
    )

    assert result["profile"] == "heavy"
    assert result["enforcement_sensitive"] is True
    assert result["sensitive_classification"]["matched_paths"] == [
        "src/a.py",
        "src/z.py",
    ]


def test_build_evidence_rejects_incomplete_file_snapshot(tmp_path: Path) -> None:
    payload = pr_payload()
    payload["files"] = [{"name": "src/a.py"}]

    with pytest.raises(EvidenceError, match="must contain a path"):
        build_evidence(
            payload,
            repository="acme/widgets",
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
            repo=tmp_path,
            config=config(tmp_path),
        )


def test_collect_evidence_rejects_head_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots = [pr_payload("a" * 40), pr_payload("c" * 40)]
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshots.pop(0),
    )

    with pytest.raises(EvidenceError, match="PR head changed"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
        )


def test_collect_evidence_rejects_file_set_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = pr_payload()
    second = pr_payload()
    second["files"] = [{"path": "src/new.py"}]
    snapshots = [first, second]
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshots.pop(0),
    )

    with pytest.raises(EvidenceError, match="PR file set changed"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
        )
