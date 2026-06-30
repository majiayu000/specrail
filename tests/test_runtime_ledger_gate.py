from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402


def clean_checkpoint() -> dict[str, object]:
    return {
        "checkpoint_version": 1,
        "tranche_id": "2026-06-30-example-t01",
        "repo": "example/repo",
        "scope": "close one issue only",
        "status": "handoff",
        "context_budget": {
            "window_tokens": 258400,
            "soft_stop_ratio": 0.5,
            "hard_stop_ratio": 0.65,
            "critical_stop_ratio": 0.75,
        },
        "output_firewall": {
            "raw_log_policy": "file_only",
            "max_parent_stdout_lines": 150,
            "max_subagent_final_lines": 150,
            "artifact_root": "artifacts/logs/t01",
        },
        "goal_candidate": {
            "objective": "Finish this bounded tranche only",
            "done_when": [
                "runtime checkpoint updated",
                "remote truth refreshed",
            ],
            "constraints": [
                "do not read raw Codex session logs",
            ],
            "blocked_stop_condition": "record blocker and next_action",
        },
        "items": [
            {
                "issue": 751,
                "pr": 752,
                "state": "merge_ready",
                "branch": "fix/issue-751",
                "worktree": "/tmp/example",
                "head_sha": "1234567890abcdef",
                "truth_level": "A",
                "ci": {
                    "status": "green",
                    "evidence": "artifacts/logs/t01/ci-summary.md",
                },
                "local_verification": [
                    {
                        "command": "cargo check --all-features --locked",
                        "status": "passed",
                        "evidence": "artifacts/logs/t01/cargo-check.log",
                    }
                ],
                "review": {
                    "reviewer_lane": "reviewer-1",
                    "status": "passed",
                    "blocking_findings": [],
                },
                "review_threads": {
                    "status": "clean",
                    "unresolved_count": 0,
                    "evidence": "artifacts/reviews/t01/review-threads.json",
                    "checked_at": "2026-06-30T12:00:00Z",
                },
                "pr_gate": {
                    "status": "passed",
                    "head_sha": "1234567890abcdef",
                    "evidence": "artifacts/reviews/t01/pr-gate.json",
                    "checked_at": "2026-06-30T12:01:00Z",
                },
                "blocker": None,
                "next_action": "merge after final remote refresh",
                "merge_state": "clean",
                "merge_authorization": {
                    "actor": "maintainer",
                    "source": "chat",
                    "summary": "you can merge",
                },
            }
        ],
        "resume_prompt": "Read this checkpoint and refresh remote truth.",
    }


def test_runtime_ledger_gate_allows_complete_merge_ready_checkpoint() -> None:
    result = evaluate_checkpoint(clean_checkpoint())

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_runtime_ledger_gate_blocks_merge_ready_without_authorization() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item.pop("merge_authorization")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("merge_authorization" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_missing_window_tokens() -> None:
    checkpoint = clean_checkpoint()
    context_budget = checkpoint["context_budget"]
    assert isinstance(context_budget, dict)
    context_budget.pop("window_tokens")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("context_budget.window_tokens" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_bounded_stdout_policy() -> None:
    checkpoint = clean_checkpoint()
    output_firewall = checkpoint["output_firewall"]
    assert isinstance(output_firewall, dict)
    output_firewall["raw_log_policy"] = "bounded_stdout"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("raw_log_policy" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_invalid_goal_candidate() -> None:
    checkpoint = clean_checkpoint()
    checkpoint["goal_candidate"] = {
        "objective": "Finish tranche",
        "done_when": [],
        "blocked_stop_condition": "stop",
    }

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("goal_candidate.done_when" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_missing_review_threads_evidence() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item.pop("review_threads")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("review_threads" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_stale_pr_gate_head_sha() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["head_sha"] = "stale"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("pr_gate head_sha" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_pending_test_marked_complete() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["state"] = "complete"
    item["local_verification"] = [
        {
            "command": "cargo test --all-features --locked",
            "status": "running",
            "evidence": "artifacts/logs/t01/cargo-test.log",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("pending verification" in error for error in result["errors"])


def test_runtime_ledger_gate_cli_json_contract(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(json.dumps(clean_checkpoint()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "checks/runtime_ledger_gate.py",
            "--checkpoint",
            str(checkpoint_path),
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
    assert {
        "decision",
        "errors",
        "warnings",
        "satisfied",
    } <= set(payload)
