from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_route_gate(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = subprocess.run(
        [
            sys.executable,
            "checks/route_gate.py",
            "--repo",
            ".",
            *args,
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return result, payload


def write_duplicate_evidence(
    tmp_path: Path,
    *,
    issue: int = 999,
    open_prs: list[dict[str, object]] | None = None,
    remote_branches: list[str] | None = None,
) -> Path:
    path = tmp_path / "duplicate-evidence.json"
    path.write_text(
        json.dumps(
            {
                "issue": issue,
                "collected_at": "2026-07-04T00:00:00Z",
                "open_prs": [] if open_prs is None else open_prs,
                "remote_branches": [] if remote_branches is None else remote_branches,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_route_gate_requires_trusted_state_for_readiness_gated_routes(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "github_state": "OPEN",
                "state": "ready_to_spec",
                "state_source": "body_hint",
                "state_trusted": False,
            }
        ),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert payload["decision"] == "needs_human"
    assert "trusted_state" in payload["missing"]
    assert any("untrusted body_hint" in reason for reason in payload["reasons"])


def test_route_gate_required_mode_fails_untrusted_readiness_state(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "github_state": "OPEN",
                "state": "ready_to_spec",
                "state_source": "body_hint",
                "state_trusted": False,
            }
        ),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--evidence",
        str(evidence_path),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "needs_human"


def test_route_gate_allows_trusted_readiness_label_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "github_state": "OPEN",
                "state": "ready_to_spec",
                "state_source": "label",
                "state_trusted": True,
            }
        ),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"


def test_route_gate_dry_run_warns_for_missing_artifacts_but_required_blocks(
    tmp_path: Path,
) -> None:
    duplicate_evidence = write_duplicate_evidence(tmp_path)
    dry_run, dry_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "dry_run",
    )
    required, required_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "required",
    )

    assert dry_run.returncode == 0
    assert dry_payload["decision"] == "warn"
    assert any("product_spec" in item for item in dry_payload["missing"])

    assert required.returncode == 1
    assert required_payload["decision"] == "blocked"
    assert any("tech_spec" in item for item in required_payload["missing"])


def test_route_gate_implement_requires_duplicate_evidence() -> None:
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "55",
        "--state",
        "ready_to_implement",
    )

    assert result.returncode == 0
    assert payload["decision"] == "needs_human"
    assert "duplicate_work:duplicate_evidence" in payload["missing"]


def test_route_gate_blocks_duplicate_open_pr(tmp_path: Path) -> None:
    duplicate_evidence = write_duplicate_evidence(
        tmp_path,
        issue=55,
        open_prs=[
            {
                "number": 123,
                "head_ref": "codex/gh55-existing",
                "references_issue": True,
            }
        ],
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "55",
        "--state",
        "ready_to_implement",
        "--duplicate-evidence",
        str(duplicate_evidence),
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("#123" in reason for reason in payload["reasons"])


def test_route_gate_duplicate_branch_needs_human(tmp_path: Path) -> None:
    duplicate_evidence = write_duplicate_evidence(
        tmp_path,
        issue=55,
        remote_branches=["codex/gh55-existing"],
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "55",
        "--state",
        "ready_to_implement",
        "--duplicate-evidence",
        str(duplicate_evidence),
    )

    assert result.returncode == 0
    assert payload["decision"] == "needs_human"
    assert "duplicate_work:branch_ownership_decision" in payload["missing"]


def test_route_gate_blocks_unknown_current_state() -> None:
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_merge",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert payload["reasons"] == ["unknown current state: ready_to_merge"]
