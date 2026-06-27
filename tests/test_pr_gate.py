from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from pr_gate import evaluate_pr_gate  # noqa: E402


def clean_evidence() -> dict[str, object]:
    return fixture("pr-clean-authorized.json")


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_pr_gate_allows_clean_authorized_merge() -> None:
    result = evaluate_pr_gate(clean_evidence())

    assert result["decision"] == "allowed"
    assert result["missing"] == []
    assert result["reasons"] == []


def test_pr_gate_needs_human_without_authorization() -> None:
    evidence = fixture("pr-missing-human-auth.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "needs_human"
    assert "human_authorization" in result["missing"]
    assert result["blocked_actions"] == ["merge"]


def test_pr_gate_blocks_pending_ci() -> None:
    evidence = fixture("pr-pending-ci.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("workflow-check is not completed" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unresolved_thread() -> None:
    evidence = fixture("pr-unresolved-thread.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("unresolved review threads" in reason for reason in result["reasons"])


def test_pr_gate_cli_json_contract(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(clean_evidence()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "checks/pr_gate.py",
            "--repo",
            ".",
            "--evidence",
            str(evidence_path),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert {
        "decision",
        "pr",
        "linked_issue",
        "head_sha",
        "reasons",
        "satisfied",
        "missing",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)
