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


def full_queue_checkpoint() -> dict[str, object]:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["spec_status"] = "complete"
    item["spec_status_reason"] = "specs/GH751 has product, tech, and tasks"
    checkpoint["scope"] = "drain all actionable issues and PRs"
    checkpoint["overall_objective"] = "drain_all_actionable_issues_and_prs"
    checkpoint["queue_mode"] = "full_queue_drain"
    checkpoint["spec_coverage"] = {
        "checked_at": "2026-07-01T00:00:00Z",
        "complete": [751],
        "needs_tasks": [],
        "needs_spec": [],
        "umbrella_covered": [],
        "exception_allowed": [],
    }
    checkpoint["remaining_queue"] = []
    return checkpoint


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


def test_runtime_ledger_gate_blocks_invalid_top_level_contract() -> None:
    checkpoint = clean_checkpoint()
    checkpoint["tranche_id"] = ""
    checkpoint["repo"] = ""
    checkpoint["scope"] = ""
    checkpoint["status"] = "not-a-status"
    checkpoint["resume_prompt"] = ""

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("checkpoint.tranche_id" in error for error in result["errors"])
    assert any("checkpoint.repo" in error for error in result["errors"])
    assert any("checkpoint.scope" in error for error in result["errors"])
    assert any("checkpoint.status" in error for error in result["errors"])
    assert any("checkpoint.resume_prompt" in error for error in result["errors"])


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


def test_full_queue_blocks_implementation_without_spec() -> None:
    checkpoint = full_queue_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["issue"] = 88
    item["pr"] = 116
    item["state"] = "running"
    item["spec_status"] = "needs_spec"
    item["spec_status_reason"] = "specs/GH88/product.md is missing"
    checkpoint["spec_coverage"] = {
        "checked_at": "2026-07-01T00:00:00Z",
        "complete": [],
        "needs_tasks": [],
        "needs_spec": [88],
        "umbrella_covered": [],
        "exception_allowed": [],
    }
    checkpoint["remaining_queue"] = [
        {
            "issue": 88,
            "state": "needs_spec",
            "spec_status": "needs_spec",
            "next_action": "write specs/GH88/product.md and tech.md",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("must route to spec or task planning" in error for error in result["errors"])


def test_full_queue_allows_umbrella_spec_coverage() -> None:
    checkpoint = full_queue_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["issue"] = 119
    item["pr"] = 125
    item["spec_status"] = "umbrella_covered"
    item["spec_status_reason"] = "specs/GH118 explicitly covers #119"
    checkpoint["spec_coverage"] = {
        "checked_at": "2026-07-01T00:00:00Z",
        "complete": [118],
        "needs_tasks": [],
        "needs_spec": [],
        "umbrella_covered": [119],
        "exception_allowed": [],
    }

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_full_queue_blocks_complete_when_pr_is_still_waiting_ci() -> None:
    checkpoint = full_queue_checkpoint()
    checkpoint["status"] = "complete"
    checkpoint["remaining_queue"] = [
        {
            "issue": 116,
            "pr": 116,
            "state": "waiting_ci",
            "spec_status": "complete",
            "next_action": "refresh CI and PR gate for current head",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("waiting_ci" in error for error in result["errors"])


def test_full_queue_blocks_complete_with_remaining_needs_spec() -> None:
    checkpoint = full_queue_checkpoint()
    checkpoint["status"] = "complete"
    checkpoint["spec_coverage"] = {
        "checked_at": "2026-07-01T00:00:00Z",
        "complete": [],
        "needs_tasks": [],
        "needs_spec": [88],
        "umbrella_covered": [],
        "exception_allowed": [],
    }
    checkpoint["remaining_queue"] = [
        {
            "issue": 88,
            "state": "needs_spec",
            "spec_status": "needs_spec",
            "next_action": "write specs/GH88/product.md and tech.md",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("needs_spec" in error for error in result["errors"])


def test_full_queue_handoff_needs_spec_fixture_is_allowed() -> None:
    fixture = ROOT / "examples" / "fixtures" / "runtime-full-queue-handoff-needs-spec.json"
    checkpoint = json.loads(fixture.read_text(encoding="utf-8"))

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_full_queue_false_complete_needs_spec_fixture_is_blocked() -> None:
    fixture = ROOT / "examples" / "fixtures" / "runtime-full-queue-false-complete-needs-spec.json"
    checkpoint = json.loads(fixture.read_text(encoding="utf-8"))

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("needs_spec" in error for error in result["errors"])
