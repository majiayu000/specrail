from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import github_pr_evidence as github_pr_evidence_module

from github_pr_evidence_test_support import (
    ROOT,
    pr_payload,
    reviewer_resolver_roles,
    threads_payload,
)
from github_pr_evidence import (  # noqa: E402
    EvidenceError,
    collect_evidence,
    collect_issue_view,
)
from pr_gate import evaluate_pr_gate  # noqa: E402


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
    resolver_map = tmp_path / "resolver-map.json"
    resolver_map.write_text(
        json.dumps({"reviewer": reviewer_resolver_roles()["reviewer"]}),
        encoding="utf-8",
    )

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
            "--review-manifest",
            "examples/fixtures/review-manifest-pr10.json",
            "--resolver-role-map",
            str(resolver_map),
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
    assert "round_audit" not in evidence["review_evidence"]
    assert evaluate_pr_gate(evidence)["decision"] == "allowed"


def test_cli_collects_verified_partial_issue_with_fake_gh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_payload()
    payload["number"] = 801
    payload["body"] = "- Closes #806\n- Refs #671"
    payload["closingIssuesReferences"] = [{"number": 806}]
    issue_payload = {
        "number": 671,
        "state": "OPEN",
        "url": "https://github.com/majiayu000/remem/issues/671",
    }
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import os",
                "import sys",
                f"pr_payload = {json.dumps(payload)!r}",
                f"threads_payload = {json.dumps(threads_payload())!r}",
                f"issue_payload = {json.dumps(issue_payload)!r}",
                "args = sys.argv[1:]",
                "if args[:2] == ['pr', 'view']:",
                "    print(pr_payload)",
                "elif args[:2] == ['api', 'graphql']:",
                "    print(threads_payload)",
                "elif args[:2] == ['issue', 'view']:",
                "    if os.environ.get('FAKE_ISSUE_FAIL') == '1':",
                "        print('issue unavailable', file=sys.stderr)",
                "        raise SystemExit(1)",
                "    print(issue_payload)",
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
            "majiayu000/remem",
            "--pr",
            "801",
            "--issue",
            "671",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["linked_issue"] == 671
    assert evidence["issue_reference"]["kind"] == "partial"
    assert evidence["issue_reference"]["closing_issue_numbers"] == [806]

    failure_env = os.environ.copy()
    failure_env["FAKE_ISSUE_FAIL"] = "1"
    failed = subprocess.run(
        result.args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=failure_env,
    )
    assert failed.returncode == 1
    assert "gh command failed" in failed.stderr


def test_cli_wires_external_round_cap_authorization_and_maintainer_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authorization = tmp_path / "round-cap.json"
    authorization.write_text(
        json.dumps(
            {
                "authorization_id": "RCA-10-4",
                "pr": 10,
                "prior_head_sha": "a" * 40,
                "target_head_sha": "b" * 40,
                "review_round": 4,
                "decision": "continue_once",
                "actor": "maintainer",
                "source": "maintainer decision in issue #10",
                "authorized_at": "2026-07-23T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    role_map = tmp_path / "maintainer-roles.json"
    role_map.write_text(
        json.dumps(
            {
                "maintainer_roles": {
                    "maintainer": {
                        "role": "maintainer",
                        "authorized_human_maintainer": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_collect(*args: object) -> dict[str, object]:
        return {"round_cap_authorizations": args[-1]}

    monkeypatch.setattr(github_pr_evidence_module, "collect_evidence", fake_collect)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "github_pr_evidence.py",
            "--github-repo",
            "majiayu000/specrail",
            "--pr",
            "10",
            "--round-cap-authorization",
            str(authorization),
            "--maintainer-role-map",
            str(role_map),
            "--json",
        ],
    )

    assert github_pr_evidence_module.main() == 0
    evidence = json.loads(capsys.readouterr().out)
    assert evidence["round_cap_authorizations"] == [
        {
            **json.loads(authorization.read_text(encoding="utf-8")),
            "authorized_human_maintainer": True,
        }
    ]


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


def test_collect_issue_view_uses_same_repository_and_expected_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run_gh_json(args: list[str]) -> dict[str, object]:
        captured.extend(args)
        return {"number": 671, "state": "OPEN", "url": "https://example/671"}

    monkeypatch.setattr("github_pr_evidence.run_gh_json", fake_run_gh_json)

    assert collect_issue_view("majiayu000/remem", 671)["number"] == 671
    assert captured == [
        "issue",
        "view",
        "671",
        "--repo",
        "majiayu000/remem",
        "--json",
        "number,state,url",
    ]


def test_collect_evidence_queries_partial_issue_inside_pr_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_payload()
    payload["body"] = "Closes #806\nRefs #671"
    payload["closingIssuesReferences"] = [{"number": 806}]
    calls: list[str] = []

    def fake_collect_pr_view(_repo: str, _pr: int) -> dict[str, object]:
        calls.append("pr")
        return payload

    def fake_collect_threads(_owner: str, _name: str, _pr: int) -> dict[str, object]:
        calls.append("threads")
        return threads_payload()

    def fake_collect_issue(_repo: str, _issue: int) -> dict[str, object]:
        calls.append("issue")
        return {"number": 671, "state": "OPEN", "url": "https://example/671"}

    monkeypatch.setattr("github_pr_evidence.collect_pr_view", fake_collect_pr_view)
    monkeypatch.setattr("github_pr_evidence.collect_review_threads", fake_collect_threads)
    monkeypatch.setattr("github_pr_evidence.collect_issue_view", fake_collect_issue)

    evidence = collect_evidence(
        "majiayu000/remem",
        801,
        None,
        expected_issue=671,
    )

    assert calls == ["pr", "threads", "issue", "pr", "issue"]
    assert evidence["linked_issue"] == 671
    assert evidence["issue_reference"]["closing_issue_numbers"] == [806]


def test_collect_evidence_rejects_expected_issue_without_refs_directive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_payload()
    payload["closingIssuesReferences"] = [{"number": 806}]
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view", lambda _repo, _pr: payload
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_review_threads",
        lambda _owner, _name, _pr: threads_payload(),
    )

    with pytest.raises(EvidenceError, match="standalone Refs #671"):
        collect_evidence("majiayu000/remem", 801, None, expected_issue=671)


@pytest.mark.parametrize("changed_field", ["body", "closingIssuesReferences"])
def test_collect_evidence_rejects_relation_change_during_gate_query(
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
) -> None:
    first = pr_payload()
    second = dict(first)
    if changed_field == "body":
        second[changed_field] = "Refs #10"
    else:
        second[changed_field] = [{"number": 10}]
    calls = {"pr_view": 0}

    def fake_collect_pr_view(_repo: str, _pr: int) -> dict[str, object]:
        calls["pr_view"] += 1
        return first if calls["pr_view"] == 1 else second

    monkeypatch.setattr("github_pr_evidence.collect_pr_view", fake_collect_pr_view)
    monkeypatch.setattr(
        "github_pr_evidence.collect_review_threads",
        lambda _owner, _name, _pr: threads_payload(),
    )

    with pytest.raises(EvidenceError, match="relation changed"):
        collect_evidence("majiayu000/specrail", 10, None)
