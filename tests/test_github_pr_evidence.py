from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from github_evidence_common import EvidenceError
from github_pr_evidence import (
    build_evidence,
    collect_evidence,
    collect_hosted_findings,
    collect_pr_view,
    combine_review_findings,
)
from review_json_gate import evaluate_review_gate
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
            "artifacts": {
                "spec_packet": "specs/GH{issue_number}/",
                "product_spec": "specs/GH{issue_number}/product.md",
                "tech_spec": "specs/GH{issue_number}/tech.md",
                "task_plan": "specs/GH{issue_number}/tasks.md",
            },
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


def test_collect_pr_view_uses_complete_rest_file_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> object:
        calls.append(args)
        if args[:2] == ["pr", "view"]:
            return {"changedFiles": 101}
        page = int(
            next(value for value in args if value.startswith("page=")).split("=", 1)[1]
        )
        start = 0 if page == 1 else 100
        count = 100 if page == 1 else 1
        return [
            {"filename": f"src/file-{index:03d}.py"}
            for index in range(start, start + count)
        ]

    monkeypatch.setattr("github_pr_evidence.run_gh_json", fake_run)

    payload = collect_pr_view("acme/widgets", 42)

    assert len(payload["files"]) == 101
    assert payload["files"][-1]["path"] == "src/file-100.py"
    assert len(calls) == 3


def test_collect_pr_view_rejects_incomplete_rest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[object] = [
        {"changedFiles": 101},
        [{"filename": "src/only.py"}],
    ]
    monkeypatch.setattr(
        "github_pr_evidence.run_gh_json",
        lambda _args: responses.pop(0),
    )

    with pytest.raises(EvidenceError, match="collected 1 of 101"):
        collect_pr_view("acme/widgets", 42)


def test_hosted_findings_preserve_resolution_and_outdated_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "github_pr_evidence.run_gh_json",
        lambda _args: {
            "data": {
                "repository": {
                    "pullRequest": {
                        "headRefOid": "a" * 40,
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "thread-current",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {"nodes": [{"body": "[P1] Current defect"}]},
                                },
                                {
                                    "id": "thread-old",
                                    "isResolved": False,
                                    "isOutdated": True,
                                    "comments": {"nodes": [{"body": "P1 old defect"}]},
                                },
                            ],
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                        },
                    }
                }
            }
        },
    )

    findings = collect_hosted_findings("acme/widgets", 42, "a" * 40)
    combined = combine_review_findings(review(), findings)

    assert [finding["id"] for finding in findings] == [
        "hosted:thread-current",
        "hosted:thread-old",
    ]
    assert combined["verdict"] == "blocking"
    assert findings[1]["outdated"] is True


def test_local_review_cannot_self_report_hosted_or_outdated_provenance() -> None:
    local = review()
    local["findings"] = [
        {
            "id": "forged-hosted",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Must remain a current local blocker.",
            "origin": "hosted",
            "outdated": True,
        }
    ]

    combined = combine_review_findings(local, [])

    assert combined["findings"] == [
        {
            "id": "forged-hosted",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Must remain a current local blocker.",
        }
    ]
    assert combined["verdict"] == "blocking"


def test_round_two_reconciles_carried_hosted_finding_by_thread_id() -> None:
    prior = review(head="b" * 40)
    prior["base_head_sha"] = "c" * 40
    prior["diff_sha256"] = "d" * 64
    prior["verdict"] = "blocking"
    prior["findings"] = [
        {
            "id": "hosted:thread-1",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Round-one blocker.",
            "origin": "hosted",
            "outdated": False,
            "fix_paths": ["src/app.py"],
        }
    ]
    current = review()
    current.update(
        {
            "base_head_sha": "b" * 40,
            "diff_sha256": "e" * 64,
            "round": 2,
            "mode": "diff_only",
            "prior_review": prior,
            "findings": [
                {
                    "id": "hosted:thread-1",
                    "severity": "P1",
                    "status": "unresolved",
                    "summary": "Carried blocker.",
                    "origin": "hosted",
                    "outdated": False,
                    "introduced_by_diff": False,
                }
            ],
        }
    )
    hosted = [
        {
            "id": "hosted:thread-1",
            "severity": "P1",
            "status": "resolved",
            "summary": "Round-one blocker.",
            "origin": "hosted",
            "outdated": True,
        }
    ]

    combined = combine_review_findings(current, hosted)

    assert [finding["id"] for finding in combined["findings"]] == [
        "hosted:thread-1"
    ]
    assert combined["findings"][0]["status"] == "resolved"
    assert combined["findings"][0]["outdated"] is True
    prior_finding = combined["prior_review"]["findings"][0]
    assert prior_finding["origin"] == "hosted"
    assert prior_finding["outdated"] is False
    assert prior_finding["status"] == "unresolved"
    assert combined["verdict"] == "clean"
    gate = evaluate_review_gate(combined, "", verify_diff=False)
    assert gate["decision"] == "allowed", gate["reasons"]


def test_spec_registry_uses_linked_issue_artifact_references(tmp_path: Path) -> None:
    pack = config(tmp_path)
    pack.workflow["enforcement"]["sensitive_registry"]["specs"] = [
        "specs/GH208/**"
    ]

    result = build_evidence(
        pr_payload(),
        repository="acme/widgets",
        profile="standard",
        gate_invocation_id="gate-1",
        review=review(profile="heavy"),
        expected_issue=208,
        repo=tmp_path,
        config=pack,
    )

    assert result["profile"] == "heavy"
    assert result["sensitive_classification"]["matched_specs"] == [
        "specs/GH208/product.md",
        "specs/GH208/tasks.md",
        "specs/GH208/tech.md",
    ]


def test_sensitive_fastlane_collection_includes_hosted_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = pr_payload()
    hosted_calls: list[str] = []
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )

    def hosted(_repo: str, _pr: int, _head: str) -> list[dict[str, object]]:
        hosted_calls.append(_head)
        return [
            {
                "id": "hosted:security",
                "severity": "P2",
                "status": "unresolved",
                "summary": "Sensitive follow-up.",
                "origin": "hosted",
                "outdated": False,
            }
        ]

    monkeypatch.setattr("github_pr_evidence.collect_hosted_findings", hosted)

    result = collect_evidence(
        "acme/widgets",
        42,
        profile="fastlane",
        gate_invocation_id="gate-1",
        review=review(profile="heavy"),
        repo=tmp_path,
        config=config(tmp_path, ["src/**"]),
    )

    assert result["profile"] == "heavy"
    assert hosted_calls == ["a" * 40, "a" * 40]
    assert result["review"]["verdict"] == "non_blocking"


def test_noncanonical_fastlane_independent_review_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = pr_payload()
    hosted_calls: list[str] = []
    pack = config(tmp_path)
    pack.workflow["verification_profiles"] = {
        "default": "fastlane",
        "profiles": {
            "fastlane": {
                "requires_independent_review": True,
                "max_review_rounds": 1,
                "merge_authorization": "invocation",
            }
        },
    }
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda _repo, _pr, head: hosted_calls.append(head) or [],
    )

    with pytest.raises(EvidenceError, match="canonical safety policy"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="fastlane",
            gate_invocation_id="gate-1",
            review=review(profile="fastlane"),
            repo=tmp_path,
            config=pack,
        )
    assert hosted_calls == []


def test_collect_evidence_rejects_head_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots = [pr_payload("a" * 40), pr_payload("c" * 40)]
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshots.pop(0),
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda *_args: [],
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
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda *_args: [],
    )

    with pytest.raises(EvidenceError, match="PR file set changed"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
        )
