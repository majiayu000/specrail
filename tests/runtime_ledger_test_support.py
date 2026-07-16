from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))


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
        "thread_dispatch_gate": {
            "explicit_thread_request": "yes",
            "native_subagents": "available",
            "spawn_requirement": "required",
            "fallback_mode": "none",
            "planned_native_threads": [
                {
                    "id": "merge-reviewer-1",
                    "role": "merge_reviewer",
                    "target": "PR #718",
                    "write_scope": "read_only",
                    "spawn_status": "spawned",
                    "no_spawn_reason": None,
                }
            ],
            "native_thread_evidence": {
                "spawned_agents": [
                    {
                        "lane_id": "merge-reviewer-1",
                        "spawn_tool": "multi_agent_v1.spawn_agent",
                        "agent_id_or_thread_id": "agent-reviewer-1",
                        "wait_evidence": "wait_agent completed",
                        "close_evidence": "close_agent completed",
                        "result_collected": "yes",
                    }
                ],
                "fallback_reason": None,
            },
            "no_spawn_reason": None,
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
                "issue": 716,
                "pr": 718,
                "state": "merge_ready",
                "branch": "fix/issue-751",
                "worktree": "/tmp/example",
                "head_sha": "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
                "truth_level": "A",
                "review_source": "independent_lane",
                "lane_failures": [],
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
                    "reviewer_lane": "merge-reviewer-1",
                    "native_thread_id": "agent-reviewer-1",
                    "status": "passed",
                    "review_source": "independent_lane",
                    "evidence": "artifacts/reviews/t01/merge-reviewer-1.json",
                    "manifest": "artifacts/reviews/t01/manifest.json",
                    "artifact_id": "pr718-head1-reviewer1",
                    "head_sha": "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
                    "review_completed_at": "2026-06-30T12:00:00Z",
                    "terminal_status": "completed",
                    "verdict": "clean",
                    "human_final_review_required": False,
                    "findings": [],
                    "prior_findings": [],
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
                    "head_sha": "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
                    "evidence": str(
                        ROOT / "examples" / "fixtures" / "pr-clean-authorized.json"
                    ),
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
    item["spec_status_reason"] = "specs/GH716 has product, tech, and tasks"
    checkpoint["scope"] = "drain all actionable issues and PRs"
    checkpoint["overall_objective"] = "drain_all_actionable_issues_and_prs"
    checkpoint["queue_mode"] = "full_queue_drain"
    checkpoint["spec_coverage"] = {
        "checked_at": "2026-07-01T00:00:00Z",
        "complete": [716],
        "needs_tasks": [],
        "needs_spec": [],
        "umbrella_covered": [],
        "exception_allowed": [],
    }
    checkpoint["remaining_queue"] = []
    return checkpoint


def _schema_spec_status_enums() -> list[list[object]]:
    schema_path = ROOT / "schemas" / "runtime_checkpoint.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    enums: list[list[object]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("properties") and "spec_status" in value["properties"]:
                spec_status = value["properties"]["spec_status"]
                assert isinstance(spec_status, dict), "spec_status schema must be an object"
                enum = spec_status.get("enum")
                assert isinstance(enum, list), "spec_status schema must define enum"
                enums.append(enum)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    assert enums, "runtime checkpoint schema must define spec_status enum"
    return enums


def _fixture_checkpoint(name: str) -> dict[str, object]:
    path = ROOT / "examples" / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))
