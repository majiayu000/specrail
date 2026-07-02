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


def test_route_gate_dry_run_warns_for_missing_artifacts_but_required_blocks() -> None:
    dry_run, dry_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
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
        "--mode",
        "required",
    )

    assert dry_run.returncode == 0
    assert dry_payload["decision"] == "warn"
    assert any("product_spec" in item for item in dry_payload["missing"])

    assert required.returncode == 1
    assert required_payload["decision"] == "blocked"
    assert any("tech_spec" in item for item in required_payload["missing"])


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
