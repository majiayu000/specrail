from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from github_pr_evidence import (  # noqa: E402
    EvidenceError,
    REVIEW_THREADS_QUERY,
    build_evidence,
    build_human_authorization,
    collect_evidence,
    parse_github_repo,
)
from pr_gate import evaluate_pr_gate  # noqa: E402


def pr_payload() -> dict[str, object]:
    return {
        "number": 10,
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
        "mergeStateStatus": "CLEAN",
        "closingIssuesReferences": [{"number": 9}],
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "workflow-check",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://github.com/example/specrail/actions/runs/1",
            },
            {
                "__typename": "StatusContext",
                "context": "lint",
                "state": "SUCCESS",
                "targetUrl": "https://ci.example.invalid/lint",
            },
        ],
        "reviews": [
            {"author": {"login": "reviewer"}, "state": "CHANGES_REQUESTED"},
            {"author": {"login": "reviewer"}, "state": "APPROVED"},
            {"author": {"login": "bot"}, "state": "COMMENTED"},
        ],
    }


def threads_payload() -> dict[str, object]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "PRRT_kwDOExample",
                                "isResolved": True,
                                "isOutdated": False,
                                "resolvedBy": {"login": "reviewer"},
                                "resolverRole": "reviewer_lane",
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/example/specrail/pull/10#discussion_r1",
                                            "author": {"login": "reviewer"},
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                }
            }
        }
    }


def test_parse_github_repo_requires_owner_repo() -> None:
    assert parse_github_repo("majiayu000/specrail") == ("majiayu000", "specrail")

    with pytest.raises(EvidenceError):
        parse_github_repo("majiayu000/specrail/extra")

    with pytest.raises(EvidenceError):
        parse_github_repo("../specrail")


def test_review_threads_query_requests_resolver_identity() -> None:
    assert "resolvedBy" in REVIEW_THREADS_QUERY
    assert "login" in REVIEW_THREADS_QUERY


def test_build_evidence_matches_pr_gate_contract() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        {
            "actor": "user",
            "source": "chat",
            "summary": "merge approved",
        },
        review_source="independent_lane",
    )

    assert evidence["pr"] == 10
    assert evidence["review_source"] == "independent_lane"
    assert evidence["lane_failures"] == []
    assert evidence["gate_query_head_sha"] == "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"
    assert evidence["gate_query_completed_at"].endswith("Z")
    assert evidence["linked_issue"] == 9
    assert evidence["checks"] == [
        {
            "name": "workflow-check",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "url": "https://github.com/example/specrail/actions/runs/1",
        },
        {
            "name": "lint",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "url": "https://ci.example.invalid/lint",
        },
    ]
    assert evidence["reviews"] == [
        {"author": "reviewer", "state": "APPROVED"},
        {"author": "bot", "state": "COMMENTED"},
    ]
    assert evidence["review_threads"] == [
        {
            "id": "PRRT_kwDOExample",
            "url": "https://github.com/example/specrail/pull/10#discussion_r1",
            "is_resolved": True,
            "is_outdated": False,
            "resolved_by": "reviewer",
            "resolver_role": "reviewer_lane",
        }
    ]
    assert evaluate_pr_gate(evidence)["decision"] == "allowed"


def test_build_evidence_maps_resolver_role_from_lane_roster() -> None:
    payload = threads_payload()
    thread = payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]  # type: ignore[index]
    assert isinstance(thread, dict)
    thread.pop("resolverRole")

    evidence = build_evidence(
        pr_payload(),
        payload,
        {
            "actor": "user",
            "source": "chat",
        },
        review_source="independent_lane",
        resolver_roles={"reviewer": "reviewer_lane"},
    )

    assert evidence["review_threads"][0]["resolver_role"] == "reviewer_lane"
    assert evaluate_pr_gate(evidence)["decision"] == "allowed"


def test_build_evidence_without_authorization_needs_human() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        review_source="independent_lane",
    )

    assert "human_authorization" not in evidence
    result = evaluate_pr_gate(evidence)
    assert result["decision"] == "needs_human"
    assert "human_authorization" in result["missing"]


def test_build_evidence_can_record_merge_dispatch_ordering() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        {
            "actor": "user",
            "source": "chat",
        },
        "2026-07-04T00:00:10Z",
        "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
        review_source="independent_lane",
    )

    assert evidence["merge_dispatched_at"] == "2026-07-04T00:00:10Z"
    assert evidence["merge_head_sha"] == "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"


def test_authorization_flags_must_include_actor_and_source() -> None:
    assert build_human_authorization(None, None, None) is None
    assert build_human_authorization("user", "chat", "approved") == {
        "actor": "user",
        "source": "chat",
        "summary": "approved",
    }

    with pytest.raises(EvidenceError):
        build_human_authorization("user", None, None)

    with pytest.raises(EvidenceError):
        build_human_authorization(None, None, "approved")


def test_cli_uses_fake_gh_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import sys",
                f"pr_payload = {json.dumps(pr_payload())!r}",
                f"threads_payload = {json.dumps(threads_payload())!r}",
                "args = sys.argv[1:]",
                "if args[:2] == ['pr', 'view']:",
                "    print(pr_payload)",
                "elif args[:2] == ['api', 'graphql']:",
                "    print(threads_payload)",
                "else:",
                "    print('unexpected args: ' + ' '.join(args), file=sys.stderr)",
                "    raise SystemExit(2)",
            ]
        ),
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    result = subprocess.run(
        [
            sys.executable,
            "checks/github_pr_evidence.py",
            "--github-repo",
            "majiayu000/specrail",
            "--pr",
            "10",
            "--authorization-actor",
            "user",
            "--authorization-source",
            "chat",
            "--authorization-summary",
            "merge approved",
            "--review-source",
            "independent_lane",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["pr"] == 10
    assert evidence["linked_issue"] == 9
    assert evidence["human_authorization"] == {
        "actor": "user",
        "source": "chat",
        "summary": "merge approved",
    }
    assert evidence["gate_query_head_sha"] == evidence["head_sha"]
    assert evaluate_pr_gate(evidence)["decision"] == "allowed"


def test_collect_evidence_rejects_head_change_during_gate_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = pr_payload()
    second = dict(first)
    second["headRefOid"] = "ffffffffffffffffffffffffffffffffffffffff"
    calls = {"pr_view": 0}

    def fake_collect_pr_view(_repo: str, _pr: int) -> dict[str, object]:
        calls["pr_view"] += 1
        return first if calls["pr_view"] == 1 else second

    monkeypatch.setattr("github_pr_evidence.collect_pr_view", fake_collect_pr_view)
    monkeypatch.setattr("github_pr_evidence.collect_review_threads", lambda _owner, _name, _pr: threads_payload())

    with pytest.raises(EvidenceError, match="PR head changed"):
        collect_evidence("majiayu000/specrail", 10, None)
