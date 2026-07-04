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


def test_pr_gate_allows_human_resolved_thread() -> None:
    evidence = clean_evidence()
    thread = evidence["review_threads"][0]
    thread["resolved_by"] = "maintainer"
    thread["resolver_role"] = "human"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed"
    assert any("resolved by human" in item for item in result["satisfied"])


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


def test_pr_gate_blocks_outdated_unresolved_thread() -> None:
    evidence = fixture("pr-outdated-unresolved-thread.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("outdated-unresolved-thread" in reason for reason in result["reasons"])


def test_pr_gate_blocks_implementer_resolved_thread() -> None:
    evidence = fixture("pr-implementer-resolved-thread.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("forbidden implementer" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unknown_resolved_thread() -> None:
    evidence = clean_evidence()
    thread = evidence["review_threads"][0]
    thread["resolved_by"] = "unknown-actor"
    thread["resolver_role"] = "unknown"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("forbidden unknown" in reason for reason in result["reasons"])


def test_pr_gate_blocks_missing_thread_resolver_attribution() -> None:
    evidence = fixture("pr-missing-thread-resolver.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review_threads[1].resolved_by" in result["missing"]
    assert "review_threads[1].resolver_role" in result["missing"]


def test_pr_gate_blocks_missing_gate_query_ordering_fields() -> None:
    evidence = clean_evidence()
    evidence.pop("gate_query_completed_at")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate_query_completed_at" in result["missing"]


def test_pr_gate_blocks_gate_query_after_merge() -> None:
    evidence = fixture("pr-query-after-merge.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate query must complete before merge dispatch" in result["reasons"]


def test_pr_gate_blocks_gate_query_head_mismatch() -> None:
    evidence = fixture("pr-gate-head-mismatch.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate_query_head_sha must match head_sha" in result["reasons"]


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
        "gate_query_completed_at",
        "gate_query_head_sha",
        "reasons",
        "satisfied",
        "missing",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)


def test_pr_gate_blocks_missing_review_source() -> None:
    evidence = clean_evidence()
    del evidence["review_source"]
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review_source" in result["missing"]


def test_pr_gate_blocks_self_review_source() -> None:
    evidence = fixture("pr-self-review-source.json")
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("self_review" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unknown_review_source() -> None:
    evidence = clean_evidence()
    evidence["review_source"] = "coordinator_summary"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("review_source must be one of" in reason for reason in result["reasons"])
