from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402
from schema_validation import load_json_schema  # noqa: E402
from specrail_lib import SpecRailError, validate_instance  # noqa: E402


def checkpoint(name: str = "runtime-running.json") -> dict[str, object]:
    return json.loads((ROOT / "examples" / "fixtures" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "name",
    ["runtime-running.json", "runtime-handoff.json", "runtime-complete.json"],
)
def test_milestone_checkpoint_fixtures_are_allowed(name: str) -> None:
    payload = checkpoint(name)
    validate_instance(
        load_json_schema(ROOT / "schemas" / "runtime_checkpoint.schema.json"),
        payload,
    )

    assert evaluate_checkpoint(payload) == {
        "decision": "allowed",
        "errors": [],
        "warnings": [],
    }


def test_checkpoint_rejects_duplicate_work_across_lists() -> None:
    payload = checkpoint()
    payload["blocked"] = [
        {"kind": "pr", "number": 11, "reason": "waiting for a maintainer"}
    ]

    result = evaluate_checkpoint(payload)

    assert result["decision"] == "blocked"
    assert "appears in both pending and blocked" in result["errors"][0]


def test_complete_checkpoint_rejects_remaining_work() -> None:
    payload = checkpoint("runtime-complete.json")
    payload["pending"] = [
        {"kind": "issue", "number": 20, "next_action": "write the implementation"}
    ]

    result = evaluate_checkpoint(payload)

    assert result["decision"] == "blocked"
    assert "cannot contain pending or blocked work" in result["errors"][0]


@pytest.mark.parametrize(
    ("status", "milestone_state"),
    [("running", "complete"), ("handoff", "active"), ("blocked", "active")],
)
def test_checkpoint_status_matches_milestone_state(
    status: str, milestone_state: str
) -> None:
    payload = checkpoint("runtime-handoff.json")
    payload["status"] = status
    payload["milestone"]["state"] = milestone_state

    result = evaluate_checkpoint(payload)

    assert result["decision"] == "blocked"
    assert any("milestone" in error for error in result["errors"])


def test_checkpoint_schema_rejects_copied_github_state() -> None:
    payload = checkpoint()
    payload["head_sha"] = "a" * 40

    result = evaluate_checkpoint(payload)

    assert result["decision"] == "blocked"
    assert "head_sha" in result["errors"][0]
    assert "additional property" in result["errors"][0]


def test_checkpoint_schema_requires_resume_cursor() -> None:
    payload = checkpoint()
    del payload["resume"]

    result = evaluate_checkpoint(payload)

    assert result["decision"] == "blocked"
    assert "resume" in result["errors"][0]


def test_checkpoint_validation_does_not_mutate_payload() -> None:
    payload = checkpoint()
    before = deepcopy(payload)

    evaluate_checkpoint(payload)

    assert payload == before


def test_runtime_ledger_gate_cli_json_contract(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(checkpoint()), encoding="utf-8")

    process = subprocess.run(
        [
            sys.executable,
            "checks/runtime_ledger_gate.py",
            "--checkpoint",
            str(path),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0
    assert json.loads(process.stdout)["decision"] == "allowed"


def test_schema_rejects_unknown_checkpoint_version() -> None:
    payload = checkpoint()
    payload["checkpoint_version"] = 2
    schema = load_json_schema(ROOT / "schemas" / "runtime_checkpoint.schema.json")

    with pytest.raises(SpecRailError, match="checkpoint_version"):
        validate_instance(schema, payload)
