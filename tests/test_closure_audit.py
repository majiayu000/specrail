from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from closure_audit import audit_closure  # noqa: E402


HEAD = "a" * 40


def clean_evidence() -> dict[str, object]:
    return {
        "repository": "Example/SpecRail",
        "pr": 115,
        "final_head_sha": HEAD,
        "gate": {
            "decision": "allowed",
            "head_sha": HEAD,
            "gate_query_head_sha": HEAD,
            "gate_query_completed_at": "2026-07-16T14:36:07Z",
        },
        "merge": {
            "merge_head_sha": HEAD,
            "merged_head_sha": HEAD,
            "remote_confirmed": True,
            "merge_dispatched_at": "2026-07-16T14:37:00Z",
            "merged_at": "2026-07-16T14:38:00Z",
        },
    }


def test_clean_closure_is_advisory_and_clear() -> None:
    result = audit_closure(clean_evidence(), checked_at="2026-07-16T14:39:00Z")

    assert result["status"] == "clear"
    assert result["warnings"] == []
    assert result["repository"] == "example/specrail"
    assert result["advisory_only"] is True
    assert result["github_writes_performed"] is False
    assert result["required_follow_up"] is None


def test_suspicious_chain_warns_without_blocking_or_follow_up() -> None:
    evidence = clean_evidence()
    evidence["gate"]["decision"] = "blocked"
    evidence["merge"]["merge_head_sha"] = "b" * 40
    evidence["merge"]["merge_dispatched_at"] = "2026-07-16T14:35:00Z"

    result = audit_closure(evidence)

    assert result["status"] == "warning"
    codes = {item["code"] for item in result["warnings"]}
    assert {
        "closure_gate_not_allowed",
        "closure_head_mismatch",
        "closure_dispatch_not_after_gate",
    } <= codes
    assert result["required_follow_up"] is None


def test_missing_chain_is_warning_not_gate() -> None:
    result = audit_closure(
        {
            "repository": "example/specrail",
            "pr": 115,
            "final_head_sha": HEAD,
        }
    )

    assert result["status"] == "warning"
    assert {item["code"] for item in result["warnings"]} >= {
        "closure_missing_gate_evidence",
        "closure_missing_merge_evidence",
    }
    assert "decision" not in result


def test_unconfirmed_remote_merge_warns() -> None:
    evidence = clean_evidence()
    evidence["merge"]["remote_confirmed"] = False
    evidence["merge"].pop("merged_head_sha")

    result = audit_closure(evidence)

    assert result["status"] == "warning"
    assert {item["code"] for item in result["warnings"]} >= {
        "closure_remote_not_confirmed",
        "closure_head_mismatch",
    }


@pytest.mark.parametrize(
    "repository",
    ["bad", "owner/", "/repo", "../repo", "owner/..", "owner/repo/extra"],
)
def test_invalid_repository_never_clears(repository: str) -> None:
    evidence = clean_evidence()
    evidence["repository"] = repository

    result = audit_closure(evidence)

    assert result["status"] == "warning"
    assert result["repository"] is None
    assert "invalid_repository" in {
        warning["code"] for warning in result["warnings"]
    }


def test_cli_returns_zero_for_warning_and_performs_no_write(tmp_path: Path) -> None:
    evidence_path = tmp_path / "closure.json"
    evidence_path.write_text(json.dumps({"repository": "bad"}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "checks/closure_audit.py",
            "--repo",
            str(tmp_path),
            "--evidence",
            str(evidence_path),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "warning"
    assert payload["advisory_only"] is True
    assert payload["github_writes_performed"] is False
