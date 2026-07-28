from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

import github_pr_evidence
from github_evidence_common import EvidenceError
from github_pr_evidence import parse_github_repo, parse_issue_number, parse_pr_number


@pytest.mark.parametrize("value", ["owner/repo", "a-b/c_d", "x.y/z"])
def test_parse_github_repo_accepts_explicit_owner_repo(value: str) -> None:
    assert "/".join(parse_github_repo(value)) == value


@pytest.mark.parametrize("value", ["repo", "../repo", "owner/", "/repo", "a/b/c"])
def test_parse_github_repo_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(EvidenceError):
        parse_github_repo(value)


def test_number_parsers_require_positive_values() -> None:
    assert parse_pr_number("4") == 4
    assert parse_issue_number("7") == 7
    with pytest.raises(Exception):
        parse_pr_number("0")
    with pytest.raises(Exception):
        parse_issue_number("-1")


def test_run_gh_json_uses_argument_array_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        return subprocess.CompletedProcess(command, 1, "", "denied")

    monkeypatch.setattr(github_pr_evidence.subprocess, "run", fake_run)

    with pytest.raises(EvidenceError, match="denied"):
        github_pr_evidence.run_gh_json(["pr", "view", "4"])
    assert observed == ["gh", "pr", "view", "4"]


def test_main_prints_compact_collector_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    review_path = tmp_path / "review.json"
    review_path.write_text("{}", encoding="utf-8")
    authorization_path = tmp_path / "authorization.json"
    authorization = {
        "actor": "maintainer",
        "authorized_at": "2026-07-28T12:00:00Z",
        "head_sha": "a" * 40,
        "invocation_id": "gate-1",
    }
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    attestation_path = tmp_path / "review-attestation.json"
    attestation = {
        "lane_id": "review-lane-1",
        "reviewer_actor": "reviewer-agent-1",
        "head_sha": "a" * 40,
        "invocation_id": "gate-1",
    }
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    unavailable_path = tmp_path / "checks-unavailable.json"
    unavailable = {
        "reason": "hosted_ci_not_triggered_for_base",
        "base_ref": "feature-base",
        "default_base_ref": "main",
        "workflow_trigger_evidence": "pull_request branches excludes feature-base",
        "local_verification": ["python3 -m pytest -q"],
        "verified": True,
    }
    unavailable_path.write_text(json.dumps(unavailable), encoding="utf-8")
    expected = {"contract_version": 3, "pr": 4}
    observed: dict[str, object] = {}
    monkeypatch.setattr(github_pr_evidence, "load_pack", lambda _repo: object())
    monkeypatch.setattr(
        github_pr_evidence,
        "collect_evidence",
        lambda *_args, **kwargs: observed.update(kwargs) or expected,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "github_pr_evidence.py",
            "--github-repo",
            "acme/widgets",
            "--repo",
            str(tmp_path),
            "--pr",
            "4",
            "--gate-invocation-id",
            "gate-1",
            "--review",
            str(review_path),
            "--authorization",
            str(authorization_path),
            "--review-attestation",
            str(attestation_path),
            "--checks-unavailable",
            str(unavailable_path),
            "--json",
        ],
    )

    assert github_pr_evidence.main() == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert observed["authorization"] == authorization
    assert observed["review_attestation"] == attestation
    assert observed["checks_unavailable"] == unavailable
    assert observed["gate_invocation_id"] == "gate-1"
