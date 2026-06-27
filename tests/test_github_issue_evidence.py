from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from github_issue_evidence import (  # noqa: E402
    EvidenceError,
    build_issue_evidence,
    parse_github_repo,
    parse_issue_number,
)


def issue_payload(
    labels: list[object] | None = None,
    body: str | None = "",
    number: int = 16,
    state: str = "OPEN",
) -> dict[str, object]:
    return {
        "number": number,
        "title": "Implement GitHub issue evidence adapter",
        "state": state,
        "labels": labels if labels is not None else [{"name": "ready_to_spec"}],
        "url": f"https://github.com/majiayu000/specrail/issues/{number}",
        "body": body,
    }


def test_parse_github_repo_and_issue_number_require_valid_input() -> None:
    assert parse_github_repo("majiayu000/specrail") == ("majiayu000", "specrail")
    assert parse_issue_number("16") == 16

    with pytest.raises(EvidenceError):
        parse_github_repo("majiayu000/specrail/extra")

    with pytest.raises(EvidenceError):
        parse_github_repo("../specrail")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_issue_number("0")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_issue_number("not-a-number")


def test_build_evidence_matches_route_gate_contract_from_label() -> None:
    evidence = build_issue_evidence(
        issue_payload(labels=[{"name": "area_runtime"}, {"name": "ready_to_spec"}])
    )

    assert evidence == {
        "issue": 16,
        "github_state": "OPEN",
        "state": "ready_to_spec",
        "labels": ["area_runtime", "ready_to_spec"],
        "url": "https://github.com/majiayu000/specrail/issues/16",
        "title": "Implement GitHub issue evidence adapter",
        "artifacts": {
            "product_spec": "specs/GH16/product.md",
            "tech_spec": "specs/GH16/tech.md",
            "task_plan": "specs/GH16/tasks.md",
        },
    }


def test_build_evidence_uses_body_state_hint_without_readiness_label() -> None:
    evidence = build_issue_evidence(
        issue_payload(
            labels=[{"name": "area_runtime"}],
            body="## routing\n- state: `ready_to_implement`\n",
        )
    )

    assert evidence["state"] == "ready_to_implement"
    assert evidence["labels"] == ["area_runtime"]


def test_terminal_label_takes_precedence_over_readiness_label() -> None:
    evidence = build_issue_evidence(
        issue_payload(labels=[{"name": "ready_to_spec"}, {"name": "security_private"}])
    )

    assert evidence["state"] == "security_private"


def test_terminal_states_are_valid_issue_evidence_schema_values() -> None:
    for label in ["security_private", "duplicate", "abandoned", "reserved_internal"]:
        evidence = build_issue_evidence(issue_payload(labels=[{"name": label}]))
        assert evidence["state"] == label


def test_closed_issue_state_is_preserved_for_route_gate() -> None:
    evidence = build_issue_evidence(issue_payload(state="CLOSED"))

    assert evidence["github_state"] == "CLOSED"


def test_conflicting_readiness_labels_are_rejected() -> None:
    with pytest.raises(EvidenceError):
        build_issue_evidence(
            issue_payload(labels=[{"name": "ready_to_spec"}, {"name": "ready_to_implement"}])
        )


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
                f"payload = {json.dumps(issue_payload(labels=[{'name': 'area_runtime'}], body='state: ready_to_spec'))!r}",
                "args = sys.argv[1:]",
                "expected = [",
                "    'issue', 'view', '16',",
                "    '--repo', 'majiayu000/specrail',",
                "    '--json', 'number,title,state,labels,url,body',",
                "]",
                "if args == expected:",
                "    print(payload)",
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
            "checks/github_issue_evidence.py",
            "--github-repo",
            "majiayu000/specrail",
            "--issue",
            "16",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["issue"] == 16
    assert evidence["github_state"] == "OPEN"
    assert evidence["state"] == "ready_to_spec"
    assert evidence["labels"] == ["area_runtime"]
    assert evidence["artifacts"]["product_spec"] == "specs/GH16/product.md"


def test_route_gate_consumes_issue_fixture() -> None:
    fixture = ROOT / "examples/fixtures/issue-ready-to-spec.json"
    result = subprocess.run(
        [
            sys.executable,
            "checks/route_gate.py",
            "--repo",
            ".",
            "--route",
            "write_spec",
            "--issue",
            "16",
            "--evidence",
            str(fixture),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert payload["current_state"] == "ready_to_spec"
    assert "linked_issue: GH-16" in payload["satisfied"]


def test_route_gate_blocks_closed_issue_evidence(tmp_path: Path) -> None:
    evidence = build_issue_evidence(issue_payload(state="CLOSED"))
    evidence_path = tmp_path / "closed-issue.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "checks/route_gate.py",
            "--repo",
            ".",
            "--route",
            "write_spec",
            "--issue",
            "16",
            "--evidence",
            str(evidence_path),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "blocked"
    assert "GitHub issue state must be OPEN; got CLOSED" in payload["reasons"]
