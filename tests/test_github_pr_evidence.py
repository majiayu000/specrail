from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from github_evidence_common import EvidenceError, _hosted_thread_finding
from github_pr_evidence import (
    build_evidence,
    collect_evidence,
    collect_head_push_boundary,
    collect_hosted_snapshot_template,
    collect_hosted_findings,
    collect_pr_view,
    collect_snapshot,
    combine_review_findings,
)
from pr_gate import evaluate_pr_gate
from review_json_gate import evaluate_review_gate
from rejection_items import (
    canonical_hosted_snapshot_sha256,
    canonical_review_sha256,
)
from specrail_lib import PackConfig


def pr_payload(head: str = "a" * 40) -> dict[str, object]:
    return {
        "number": 42,
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": head,
        "headRefName": "feature",
        "headRepository": {
            "name": "widgets",
            "nameWithOwner": "acme/widgets",
        },
        "headRepositoryOwner": {"login": "acme"},
        "baseRefName": "main",
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


def review_attestation(
    head: str = "a" * 40,
    invocation_id: str = "gate-1",
    review_payload: dict[str, object] | None = None,
    hosted_findings: list[dict[str, object]] | None = None,
    prior_review_boundary: str | None = None,
) -> dict[str, str]:
    current = review() if review_payload is None else review_payload
    result = {
        "artifact_id": str(current["artifact_id"]),
        "lane_id": "review-lane-1",
        "reviewer_actor": "reviewer-agent-1",
        "review_sha256": canonical_review_sha256(current),
        "head_sha": head,
        "invocation_id": invocation_id,
        "hosted_snapshot_sha256": canonical_hosted_snapshot_sha256(
            head,
            invocation_id,
            hosted_findings or [],
            prior_review_boundary,
        ),
    }
    prior = current.get("prior_review")
    if current.get("round") == 2 and isinstance(prior, dict):
        result["prior_artifact_id"] = str(prior["artifact_id"])
        result["prior_head_sha"] = str(prior["head_sha"])
    return result


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
        review_attestation=review_attestation(),
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
    assert result["review_attestation"]["artifact_id"] == "review-42"
    assert "review_attestation" not in result["review"]
    assert not {
        "review_threads",
        "pr_tier",
        "content_binding_version",
        "runtime_checkpoint",
    } & set(result)


def test_independent_review_attestation_must_use_separate_host_input(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceError, match="review_attestation"):
        build_evidence(
            pr_payload(),
            repository="acme/widgets",
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
            expected_issue=208,
            repo=tmp_path,
            config=config(tmp_path),
        )
    embedded = review()
    embedded["review_attestation"] = review_attestation()
    with pytest.raises(EvidenceError, match="injected separately"):
        build_evidence(
            pr_payload(),
            repository="acme/widgets",
            profile="standard",
            gate_invocation_id="gate-1",
            review=embedded,
            review_attestation=review_attestation(),
            expected_issue=208,
            repo=tmp_path,
            config=config(tmp_path),
        )
    embedded_prior = review()
    embedded_prior["prior_review"] = {
        **review(head="b" * 40),
        "review_attestation": review_attestation(head="b" * 40),
    }
    with pytest.raises(EvidenceError, match="injected separately"):
        build_evidence(
            pr_payload(),
            repository="acme/widgets",
            profile="standard",
            gate_invocation_id="gate-1",
            review=embedded_prior,
            review_attestation=review_attestation(),
            expected_issue=208,
            repo=tmp_path,
            config=config(tmp_path),
        )


def test_review_attestation_is_bound_to_current_head_and_invocation(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceError, match="invocation_id"):
        build_evidence(
            pr_payload(),
            repository="acme/widgets",
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
            review_attestation=review_attestation(invocation_id="old-gate"),
            expected_issue=208,
            repo=tmp_path,
            config=config(tmp_path),
        )

    missing_snapshot = review_attestation()
    missing_snapshot.pop("hosted_snapshot_sha256")
    with pytest.raises(EvidenceError, match="hosted_snapshot_sha256"):
        build_evidence(
            pr_payload(),
            repository="acme/widgets",
            profile="standard",
            gate_invocation_id="gate-1",
            review=review(),
            review_attestation=missing_snapshot,
            expected_issue=208,
            repo=tmp_path,
            config=config(tmp_path),
        )


def test_build_evidence_preserves_trusted_checks_unavailable_declaration(
    tmp_path: Path,
) -> None:
    payload = pr_payload()
    payload["baseRefName"] = "feature-base"
    payload["statusCheckRollup"] = []
    declaration = {
        "reason": "hosted_ci_not_triggered_for_base",
        "base_ref": "feature-base",
        "default_base_ref": "main",
        "workflow_trigger_evidence": "pull_request branches only contains main",
        "local_verification": ["python3 -m pytest -q"],
        "verified": True,
    }

    result = build_evidence(
        payload,
        repository="acme/widgets",
        profile="standard",
        gate_invocation_id="gate-1",
        review=review(),
        review_attestation=review_attestation(),
        checks_unavailable=declaration,
        expected_issue=208,
        repo=tmp_path,
        config=config(tmp_path),
    )

    assert result["checks"] == []
    assert result["base_ref"] == "feature-base"
    assert result["default_base_ref"] == "main"
    assert result["checks_unavailable"] == declaration


def test_sensitive_paths_automatically_select_heavy(tmp_path: Path) -> None:
    result = build_evidence(
        pr_payload(),
        repository="acme/widgets",
        profile="fastlane",
        gate_invocation_id="gate-1",
        review=review(profile="heavy"),
        review_attestation=review_attestation(
            review_payload=review(profile="heavy")
        ),
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
            review_attestation=review_attestation(),
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
            return {"changedFiles": 101, "headRefOid": "a" * 40}
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
    assert len(calls) == 4


@pytest.mark.parametrize(
    "final_identity",
    [
        {"changedFiles": 1, "headRefOid": "b" * 40},
        {"changedFiles": 2, "headRefOid": "a" * 40},
    ],
)
def test_collect_pr_view_rejects_identity_drift_during_pagination(
    monkeypatch: pytest.MonkeyPatch,
    final_identity: dict[str, object],
) -> None:
    responses: list[object] = [
        {"changedFiles": 1, "headRefOid": "a" * 40},
        [{"filename": "src/same.py"}],
        final_identity,
    ]
    monkeypatch.setattr(
        "github_pr_evidence.run_gh_json",
        lambda _args: responses.pop(0),
    )

    with pytest.raises(EvidenceError, match="PR snapshot changed"):
        collect_pr_view("acme/widgets", 42)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("isDraft", True),
        ("state", "CLOSED"),
        ("mergeStateStatus", "BLOCKED"),
        ("statusCheckRollup", [{"conclusion": "FAILURE"}]),
        ("closingIssuesReferences", [{"number": 99}]),
    ],
)
def test_collect_pr_view_rejects_same_head_mutable_pr_drift(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    initial = {
        "changedFiles": 1,
        "headRefOid": "a" * 40,
        "isDraft": False,
        "state": "OPEN",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "closingIssuesReferences": [{"number": 42}],
    }
    final = {**initial, field: value}
    responses: list[object] = [
        initial,
        [{"filename": "src/same.py"}],
        final,
    ]
    monkeypatch.setattr(
        "github_pr_evidence.run_gh_json",
        lambda _args: responses.pop(0),
    )

    with pytest.raises(EvidenceError, match="PR snapshot changed"):
        collect_pr_view("acme/widgets", 42)


def test_collect_pr_view_rejects_incomplete_rest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[object] = [
        {"changedFiles": 101, "headRefOid": "a" * 40},
        [{"filename": "src/only.py"}],
    ]
    monkeypatch.setattr(
        "github_pr_evidence.run_gh_json",
        lambda _args: responses.pop(0),
    )

    with pytest.raises(EvidenceError, match="collected 1 of 101"):
        collect_pr_view("acme/widgets", 42)


def test_collect_head_push_boundary_uses_exact_server_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "github_pr_evidence.run_gh_json",
        lambda _args: [
            {
                "activity_type": "push",
                "ref": "refs/heads/feature",
                "after": "a" * 40,
                "timestamp": "2026-07-28T09:30:00Z",
            },
            {
                "activity_type": "push",
                "ref": "refs/heads/other",
                "after": "a" * 40,
                "timestamp": "2026-07-28T09:20:00Z",
            },
        ],
    )

    assert (
        collect_head_push_boundary("acme/widgets", "feature", "a" * 40)
        == "2026-07-28T09:30:00Z"
    )


def test_collect_head_push_boundary_fails_closed_without_exact_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("github_pr_evidence.run_gh_json", lambda _args: [])

    with pytest.raises(EvidenceError, match="exactly one trusted"):
        collect_head_push_boundary("acme/widgets", "feature", "a" * 40)


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
                                    "path": "src/current.py",
                                    "subjectType": "LINE",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "body": "[P1] Current defect",
                                                "createdAt": "2026-07-28T10:00:00Z",
                                                "lastEditedAt": None,
                                                "path": "src/current.py",
                                                "originalLine": 12,
                                                "originalCommit": {"oid": "a" * 40},
                                                "pullRequestReview": {
                                                    "id": "PRR_current",
                                                    "submittedAt": "2026-07-28T10:01:00Z",
                                                    "commit": {"oid": "a" * 40},
                                                },
                                            }
                                        ]
                                    },
                                },
                                {
                                    "id": "thread-old",
                                    "path": "src/old.py",
                                    "subjectType": "LINE",
                                    "isResolved": False,
                                    "isOutdated": True,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "body": "P1 old defect",
                                                "createdAt": "2026-07-28T09:00:00Z",
                                                "lastEditedAt": None,
                                                "path": "src/old.py",
                                                "originalLine": 7,
                                                "originalCommit": {"oid": "b" * 40},
                                                "pullRequestReview": {
                                                    "id": "PRR_old",
                                                    "submittedAt": "2026-07-28T09:01:00Z",
                                                    "commit": {"oid": "b" * 40},
                                                },
                                            }
                                        ]
                                    },
                                },
                                {
                                    "id": "thread-file",
                                    "path": "docs/config.md",
                                    "subjectType": "FILE",
                                    "isResolved": True,
                                    "isOutdated": True,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "body": "[P2] File-level defect",
                                                "createdAt": "2026-07-28T08:00:00Z",
                                                "lastEditedAt": None,
                                                "path": "docs/config.md",
                                                "line": None,
                                                "originalLine": None,
                                                "originalCommit": {"oid": "b" * 40},
                                                "pullRequestReview": {
                                                    "id": "PRR_file",
                                                    "submittedAt": "2026-07-28T08:01:00Z",
                                                    "commit": {"oid": "b" * 40},
                                                },
                                            }
                                        ]
                                    },
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
        "hosted:thread-file",
        "hosted:thread-old",
    ]
    assert combined["verdict"] == "blocking"
    assert combined["findings"][0]["status"] == "unresolved"
    assert combined["findings"][0]["outdated"] is False
    assert findings[0]["_original_head_sha"] == "a" * 40
    assert "_original_head_sha" not in combined["findings"][0]
    assert findings[0]["path"] == "src/current.py"
    assert findings[0]["line"] == 12
    assert findings[1]["fix_paths"] == ["docs/config.md"]
    assert "path" not in findings[1]
    assert "line" not in findings[1]
    assert findings[2]["outdated"] is True


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
    prior["artifact_id"] = "review-pr42-round1"
    prior["base_head_sha"] = "c" * 40
    prior["diff_sha256"] = "d" * 64
    prior["verdict"] = "blocking"
    prior["findings"] = [
        {
            "id": "hosted:thread-1",
            "severity": "P3",
            "status": "resolved",
            "summary": "Caller-controlled summary.",
            "origin": "hosted",
            "outdated": False,
            "fix_paths": ["src/unrelated.py"],
            "path": "src/unrelated.py",
            "line": 999,
            "subject_type": "FILE",
            "introduced_by_diff": True,
        },
        {
            "id": "hosted:thread-2",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Caller-controlled summary.",
            "origin": "hosted",
            "outdated": False,
            "fix_paths": ["src/unrelated.py"],
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
                },
                {
                    "id": "hosted:thread-2",
                    "severity": "P1",
                    "status": "resolved",
                    "summary": "Second hosted blocker.",
                    "origin": "hosted",
                    "outdated": False,
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
            "_subject_type": "LINE",
            "_original_head_sha": "b" * 40,
            "_created_at": "2026-07-28T09:01:01Z",
            "_last_edited_at": "2026-07-28T09:10:00Z",
            "_review_id": "PRR_prior",
            "_review_submitted_at": "2026-07-28T09:01:00Z",
            "_review_head_sha": "b" * 40,
            "path": "src/app.py",
            "fix_paths": ["src/app.py"],
            "line": 11,
        },
        {
            "id": "hosted:thread-2",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Second hosted blocker.",
            "origin": "hosted",
            "outdated": True,
            "_subject_type": "LINE",
            "_original_head_sha": "b" * 40,
            "_created_at": "2026-07-28T09:02:01Z",
            "_last_edited_at": None,
            "_review_id": "PRR_second",
            "_review_submitted_at": "2026-07-28T09:02:00Z",
            "_review_head_sha": "b" * 40,
            "path": "src/second.py",
            "fix_paths": ["src/second.py"],
            "line": 21,
        }
    ]

    combined = combine_review_findings(
        current,
        hosted,
        prior_review_boundary="2026-07-28T09:30:00Z",
    )

    assert [finding["id"] for finding in combined["findings"]] == [
        "hosted:thread-1",
        "hosted:thread-2",
    ]
    assert combined["findings"][0]["status"] == "resolved"
    assert combined["findings"][0]["outdated"] is True
    prior_findings = combined["prior_review"]["findings"]
    assert [finding["origin"] for finding in prior_findings] == [
        "hosted",
        "hosted",
    ]
    assert [finding["fix_paths"] for finding in prior_findings] == [
        ["src/app.py"],
        ["src/second.py"],
    ]
    assert [finding["summary"] for finding in prior_findings] == [
        "Round-one blocker.",
        "Second hosted blocker.",
    ]
    assert [finding["severity"] for finding in prior_findings] == ["P1", "P1"]
    assert [finding["line"] for finding in prior_findings] == [11, 21]
    assert all("introduced_by_diff" not in finding for finding in prior_findings)
    assert all("subject_type" not in finding for finding in prior_findings)
    assert all(finding["status"] == "unresolved" for finding in prior_findings)
    assert all(finding["outdated"] is False for finding in prior_findings)
    assert combined["verdict"] == "clean"
    attestation = review_attestation(review_payload=combined)
    gate = evaluate_review_gate(
        combined,
        "",
        verify_diff=False,
        gate_invocation_id="gate-1",
        attestation=attestation,
    )
    assert gate["decision"] == "allowed", gate["reasons"]
    unrelated_diff = (
        "diff --git a/src/unrelated.py b/src/unrelated.py\n"
        "--- a/src/unrelated.py\n"
        "+++ b/src/unrelated.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    forged_scope_gate = evaluate_review_gate(
        combined,
        unrelated_diff,
        verify_diff=False,
        gate_invocation_id="gate-1",
        attestation=attestation,
    )
    assert forged_scope_gate["decision"] == "blocked"
    assert any(
        "outside prior blocker fix scope" in reason
        for reason in forged_scope_gate["reasons"]
    )

    created_equal_hosted = [dict(finding) for finding in hosted]
    created_equal_hosted[0]["_last_edited_at"] = None
    equal_boundary = combine_review_findings(
        current,
        created_equal_hosted,
        prior_review_boundary="2026-07-28T09:01:01Z",
    )
    assert equal_boundary["prior_review"]["findings"][0] == {
        "id": "hosted:thread-1"
    }
    submitted_equal_hosted = [dict(finding) for finding in hosted]
    submitted_equal_hosted[0]["_created_at"] = "2026-07-28T09:00:59Z"
    submitted_equal_hosted[0]["_last_edited_at"] = None
    submitted_equal_boundary = combine_review_findings(
        current,
        submitted_equal_hosted,
        prior_review_boundary="2026-07-28T09:01:00Z",
    )
    assert submitted_equal_boundary["prior_review"]["findings"][0] == {
        "id": "hosted:thread-1"
    }

    for edited_at in ("2026-07-28T09:30:00Z", "2026-07-28T09:31:00Z"):
        edited_hosted = [dict(finding) for finding in hosted]
        edited_hosted[0]["_last_edited_at"] = edited_at
        edited_boundary = combine_review_findings(
            current,
            edited_hosted,
            prior_review_boundary="2026-07-28T09:30:00Z",
        )
        assert edited_boundary["prior_review"]["findings"][0] == {
            "id": "hosted:thread-1"
        }

def test_round_two_cannot_backfill_late_old_head_review_from_forged_prior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = review(head="b" * 40)
    prior["artifact_id"] = "PRR_late"
    prior.update(
        {
            "base_head_sha": "c" * 40,
            "diff_sha256": "d" * 64,
            "verdict": "blocking",
            "findings": [
                {
                    "id": "hosted:thread-late",
                    "severity": "P1",
                    "status": "unresolved",
                    "summary": "[P1] Late old-head blocker.",
                    "origin": "hosted",
                    "outdated": False,
                    "fix_paths": ["src/app.py"],
                }
            ],
        }
    )
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
                    "id": "hosted:thread-late",
                    "severity": "P1",
                    "status": "resolved",
                    "summary": "[P1] Late old-head blocker.",
                    "origin": "hosted",
                    "outdated": False,
                    "introduced_by_diff": False,
                }
            ],
        }
    )
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
                                    "id": "thread-late",
                                    "path": "src/app.py",
                                    "subjectType": "LINE",
                                    "isResolved": True,
                                    "isOutdated": True,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "body": "[P1] Late old-head blocker.",
                                                "createdAt": "2026-07-28T10:00:00Z",
                                                "lastEditedAt": None,
                                                "path": "src/app.py",
                                                "originalLine": 10,
                                                "originalCommit": {"oid": "b" * 40},
                                                "pullRequestReview": {
                                                    "id": "PRR_late",
                                                    "submittedAt": "2026-07-28T10:01:00Z",
                                                    "commit": {"oid": "b" * 40},
                                                },
                                            }
                                        ]
                                    },
                                }
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

    hosted = collect_hosted_findings("acme/widgets", 42, "a" * 40)
    assert hosted[0]["_original_head_sha"] == "b" * 40
    combined = combine_review_findings(
        current,
        hosted,
        prior_review_boundary="2026-07-28T09:30:00Z",
    )
    gate = evaluate_review_gate(combined, "", verify_diff=False)

    assert gate["decision"] == "blocked"
    assert combined["prior_review"]["findings"] == [
        {"id": "hosted:thread-late"}
    ]
    assert any(reason.startswith("prior_review:") for reason in gate["reasons"])


def test_hosted_thread_fails_closed_on_malformed_edit_or_line() -> None:
    thread = {
        "id": "thread-invalid",
        "path": "src/app.py",
        "subjectType": "LINE",
        "isResolved": False,
        "isOutdated": False,
        "comments": {
            "nodes": [
                {
                    "body": "[P1] Invalid evidence.",
                    "createdAt": "2026-07-28T09:00:00Z",
                    "lastEditedAt": "malformed",
                    "path": "src/app.py",
                    "originalLine": 10,
                }
            ]
        },
    }
    with pytest.raises(EvidenceError, match="lastEditedAt"):
        _hosted_thread_finding(thread)

    thread["comments"]["nodes"][0]["lastEditedAt"] = None
    thread["comments"]["nodes"][0]["originalLine"] = 0
    with pytest.raises(EvidenceError, match="positive line"):
        _hosted_thread_finding(thread)


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
        review_attestation=review_attestation(
            review_payload=review(profile="heavy")
        ),
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
    hosted_finding = {
        "id": "hosted:security",
        "severity": "P2",
        "status": "unresolved",
        "summary": "Sensitive follow-up.",
        "fix_paths": ["src/app.py"],
        "origin": "hosted",
        "outdated": False,
    }
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )

    def hosted(_repo: str, _pr: int, _head: str) -> list[dict[str, object]]:
        hosted_calls.append(_head)
        return [dict(hosted_finding)]

    monkeypatch.setattr("github_pr_evidence.collect_hosted_findings", hosted)
    current_review = review(profile="heavy")

    result = collect_evidence(
        "acme/widgets",
        42,
        profile="fastlane",
        gate_invocation_id="gate-1",
        review=current_review,
        review_attestation=review_attestation(
            review_payload=current_review,
            hosted_findings=[hosted_finding],
        ),
        repo=tmp_path,
        config=config(tmp_path, ["src/**"]),
    )

    assert result["profile"] == "heavy"
    assert hosted_calls == ["a" * 40, "a" * 40]
    assert result["review"] == current_review
    assert result["hosted_findings"] == [hosted_finding]


def test_collector_rejects_attestation_for_a_different_hosted_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = pr_payload()
    hosted_finding = {
        "id": "hosted:changed",
        "severity": "P2",
        "status": "unresolved",
        "summary": "Appeared after attestation.",
        "fix_paths": ["src/app.py"],
        "origin": "hosted",
        "outdated": False,
    }
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda _repo, _pr, _head: [dict(hosted_finding)],
    )
    current_review = review()

    with pytest.raises(EvidenceError, match="canonical hosted snapshot"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="standard",
            gate_invocation_id="gate-1",
            review=current_review,
            review_attestation=review_attestation(
                review_payload=current_review,
            ),
            repo=tmp_path,
            config=config(tmp_path),
        )


def test_hosted_snapshot_template_uses_the_canonical_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hosted = [
        {
            "id": "hosted:P2-template",
            "severity": "P2",
            "status": "unresolved",
            "summary": "Template finding.",
            "fix_paths": ["src/app.py"],
            "origin": "hosted",
            "outdated": False,
        }
    ]
    monkeypatch.setattr(
        "github_pr_evidence.collect_snapshot",
        lambda *_args, **_kwargs: (pr_payload(), None, hosted, None),
    )

    template = collect_hosted_snapshot_template(
        "acme/widgets",
        42,
        profile="standard",
        gate_invocation_id="gate-1",
        review=review(),
    )

    assert template["hosted_snapshot_sha256"] == canonical_hosted_snapshot_sha256(
        "a" * 40,
        "gate-1",
        hosted,
        None,
    )


def test_round_two_local_finding_collects_and_passes_pr_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    def commit(contents: str, message: str) -> str:
        source = repo / "src" / "app.py"
        source.parent.mkdir(exist_ok=True)
        source.write_text(contents, encoding="utf-8")
        subprocess.run(["git", "add", "src/app.py"], cwd=repo, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=SpecRail Test",
                "-c",
                "user.email=specrail@example.invalid",
                "commit",
                "-qm",
                message,
            ],
            cwd=repo,
            check=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    base_head = commit("value = 'safe'\n", "base")
    prior_head = commit("value = 'broken'\n", "introduce defect")
    current_head = commit("value = 'fixed'\n", "fix defect")

    def diff_bytes(start: str, end: str, *, merge_base: bool) -> bytes:
        separator = "..." if merge_base else ".."
        return subprocess.run(
            [
                "git",
                "diff",
                "--no-ext-diff",
                "--binary",
                f"{start}{separator}{end}",
                "--",
            ],
            cwd=repo,
            check=True,
            capture_output=True,
        ).stdout

    prior = review(head=prior_head)
    prior.update(
        {
            "artifact_id": "review-42-round1",
            "base_head_sha": base_head,
            "diff_sha256": hashlib.sha256(
                diff_bytes(base_head, prior_head, merge_base=True)
            ).hexdigest(),
            "verdict": "blocking",
            "findings": [
                {
                    "id": "local:P1-value",
                    "severity": "P1",
                    "status": "unresolved",
                    "summary": "The value is unsafe.",
                    "fix_paths": ["src/app.py"],
                    "origin": "local",
                }
            ],
        }
    )
    current = review(head=current_head)
    current.update(
        {
            "artifact_id": "review-42-round2",
            "base_head_sha": prior_head,
            "diff_sha256": hashlib.sha256(
                diff_bytes(prior_head, current_head, merge_base=False)
            ).hexdigest(),
            "round": 2,
            "mode": "diff_only",
            "prior_review": prior,
            "findings": [
                {
                    "id": "local:P1-value",
                    "severity": "P1",
                    "status": "resolved",
                    "summary": "The value is unsafe.",
                    "fix_paths": ["src/app.py"],
                    "origin": "local",
                    "introduced_by_diff": False,
                }
            ],
        }
    )
    snapshot = pr_payload(head=current_head)
    snapshot["baseRefOid"] = base_head
    snapshot["files"] = [{"path": "src/app.py"}]
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_head_push_boundary",
        lambda _repo, _ref, _head: "2026-07-29T00:00:00Z",
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda _repo, _pr, _head: [],
    )

    collected = collect_evidence(
        "acme/widgets",
        42,
        profile="standard",
        gate_invocation_id="gate-1",
        review=current,
        review_attestation=review_attestation(
            head=current_head,
            review_payload=current,
            prior_review_boundary="2026-07-29T00:00:00Z",
        ),
        repo=repo,
        config=config(repo),
    )
    result = evaluate_pr_gate(collected, repo, config(repo))

    assert collected["review"] == current
    assert collected["review"]["prior_review"]["findings"] == prior["findings"]
    assert collected["hosted_findings"] == []
    assert result["decision"] == "allowed", result["reasons"]


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
            review_attestation=review_attestation(),
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
            review_attestation=review_attestation(),
        )


def test_collect_evidence_rejects_head_push_activity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = [pr_payload(), pr_payload()]
    boundaries = [
        "2026-07-28T09:30:00Z",
        "2026-07-28T09:31:00Z",
    ]
    current_review = review()
    current_review["round"] = 2
    current_review["mode"] = "diff_only"
    current_review["prior_review"] = review(head="b" * 40)
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshots.pop(0),
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_head_push_boundary",
        lambda *_args: boundaries.pop(0),
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda *_args: [],
    )

    with pytest.raises(EvidenceError, match="push activity changed"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="standard",
            gate_invocation_id="gate-1",
            review=current_review,
            review_attestation=review_attestation(),
        )


def test_collect_evidence_uses_fork_head_repository_for_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = pr_payload()
    first["headRepository"] = {
        "name": "widgets-fork",
        "nameWithOwner": "",
    }
    first["headRepositoryOwner"] = {"login": "forker"}
    second = dict(first)
    snapshots = [first, second]
    boundary_repositories: list[str] = []
    current_review = review()
    current_review["round"] = 2
    current_review["mode"] = "diff_only"
    current_review["prior_review"] = review(head="b" * 40)
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshots.pop(0),
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_head_push_boundary",
        lambda repository, *_args: (
            boundary_repositories.append(repository)
            or "2026-07-28T09:30:00Z"
        ),
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_hosted_findings",
        lambda *_args: [],
    )

    collect_evidence(
        "acme/widgets",
        42,
        profile="standard",
        gate_invocation_id="gate-1",
        review=current_review,
        review_attestation=review_attestation(
            review_payload=current_review,
            prior_review_boundary="2026-07-28T09:30:00Z",
        ),
    )

    assert boundary_repositories == ["forker/widgets-fork", "forker/widgets-fork"]


def test_collect_evidence_rejects_missing_head_repository_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = pr_payload()
    snapshot["headRepository"] = {"name": "widgets"}
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )
    current_review = review()
    current_review["prior_review"] = review(head="b" * 40)

    with pytest.raises(EvidenceError, match="headRepository.nameWithOwner is required"):
        collect_evidence(
            "acme/widgets",
            42,
            profile="standard",
            gate_invocation_id="gate-1",
            review=current_review,
            review_attestation=review_attestation(),
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
            review_attestation=review_attestation(),
        )


@pytest.mark.parametrize(
    "final_issue",
    [
        {"number": 208, "state": "CLOSED", "url": "https://example/208"},
        {"number": 208, "state": "OPEN", "url": "https://example/moved"},
        {"number": 209, "state": "OPEN", "url": "https://example/208"},
    ],
)
def test_partial_issue_drift_is_rejected_at_collection_end(
    monkeypatch: pytest.MonkeyPatch,
    final_issue: dict[str, object],
) -> None:
    snapshot = pr_payload()
    snapshot["body"] = "Refs #208"
    snapshot["closingIssuesReferences"] = []
    issue_snapshots = [
        {"number": 208, "state": "OPEN", "url": "https://example/208"},
        final_issue,
    ]
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view",
        lambda _repo, _pr: snapshot,
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_issue_view",
        lambda _repo, _issue: issue_snapshots.pop(0),
    )

    with pytest.raises(EvidenceError, match="partial issue changed"):
        collect_snapshot(
            "acme/widgets",
            42,
            profile="fastlane",
            gate_invocation_id="gate-1",
            review=review(profile="fastlane"),
            expected_issue=208,
        )
