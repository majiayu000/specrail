from __future__ import annotations

import json
import subprocess
import sys

import pytest

from runtime_ledger_test_support import (  # noqa: E402
    ROOT,
    _schema_spec_status_enums,
    clean_checkpoint,
)
from runtime_ledger_gate import (  # noqa: E402
    CHECKPOINT_STATUSES,
    FULL_QUEUE_NON_DRAINED_STATES,
    FULL_QUEUE_TERMINAL_REMAINDER_STATES,
    MERGE_READY_STATES,
    evaluate_checkpoint,
)
from specrail_lib import (  # noqa: E402
    RUNTIME_ONLY_STATE,
    RUNTIME_STATE_MAPPING,
    SPEC_STATUSES,
    load_yaml_file,
)


def test_spec_status_schema_matches_shared_constant() -> None:
    for enum in _schema_spec_status_enums():
        assert {item for item in enum if item is not None} == set(SPEC_STATUSES)


def test_runtime_state_mapping_covers_gate_state_sets() -> None:
    gate_states = (
        set(CHECKPOINT_STATUSES)
        | set(FULL_QUEUE_NON_DRAINED_STATES)
        | set(FULL_QUEUE_TERMINAL_REMAINDER_STATES)
        | set(MERGE_READY_STATES)
    )
    assert set(RUNTIME_STATE_MAPPING) == gate_states

    states = load_yaml_file(ROOT / "states.yaml")["states"]
    assert isinstance(states, dict)
    workflow_states = set(states)
    for runtime_state, targets in RUNTIME_STATE_MAPPING.items():
        if targets == RUNTIME_ONLY_STATE:
            continue
        assert isinstance(targets, tuple), f"{runtime_state} must map to a tuple"
        assert targets, f"{runtime_state} mapping must not be empty"
        assert set(targets) <= workflow_states


def test_runtime_ledger_gate_allows_complete_merge_ready_checkpoint() -> None:
    result = evaluate_checkpoint(clean_checkpoint())

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_runtime_ledger_gate_allows_blocked_lane_failure_checkpoint() -> None:
    fixture = ROOT / "examples" / "fixtures" / "runtime-lane-failure-blocked.json"
    checkpoint = json.loads(fixture.read_text(encoding="utf-8"))

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_runtime_ledger_gate_allows_independent_retry_after_lane_failure() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["lane_failures"] = [
        {
            "lane_id": "merge-reviewer-0",
            "failure_kind": "usage_limit",
            "observed_marker": "You've hit your usage limit",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_runtime_ledger_gate_blocks_self_review_merged_without_authorization() -> None:
    fixture = ROOT / "examples" / "fixtures" / "runtime-self-review-merged-unauthorized.json"
    checkpoint = json.loads(fixture.read_text(encoding="utf-8"))

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("self_review_authorization" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_lane_failure_without_downgrade_or_retry() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["state"] = "running"
    item["review_source"] = "self_review"
    item["lane_failures"] = [
        {
            "lane_id": "merge-reviewer-1",
            "failure_kind": "usage_limit",
            "observed_marker": "You've hit your usage limit",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("reviewer lane failure requires" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_merge_ready_without_authorization() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item.pop("merge_authorization")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("merge_authorization" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_merge_ready_without_thread_dispatch_gate() -> None:
    checkpoint = clean_checkpoint()
    checkpoint.pop("thread_dispatch_gate")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("thread_dispatch_gate" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_pr_merge_states_without_pr_identifier() -> None:
    for state in ["merge_ready", "ready_to_merge", "merged"]:
        checkpoint = clean_checkpoint()
        item = checkpoint["items"][0]  # type: ignore[index]
        assert isinstance(item, dict)
        item["state"] = state
        item.pop("pr")

        result = evaluate_checkpoint(checkpoint)

        assert result["decision"] == "blocked"
        assert any("requires pr" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_native_required_without_native_reviewer() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    review = item["review"]
    assert isinstance(review, dict)
    review.pop("native_thread_id")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("native_thread_id" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_blocked_pr_gate_artifact(tmp_path: Path) -> None:
    checkpoint = clean_checkpoint()
    blocked_gate = tmp_path / "pr-gate.json"
    blocked_gate.write_text(
        json.dumps(
            {
                "decision": "blocked",
                "pr": 718,
                "head_sha": "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
                "reasons": ["invalid evidence JSON"],
            }
        ),
        encoding="utf-8",
    )
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = str(blocked_gate)

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("decision must be allowed" in error for error in result["errors"])


@pytest.mark.parametrize(
    "evidence",
    [
        "https://github.com/example/repo/actions/runs/1",
        "http://example.test/pr-gate.json",
        "",
    ],
)
def test_runtime_ledger_gate_blocks_non_local_sensitive_pr_gate_evidence(
    evidence: str,
) -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["enforcement_sensitive"] = True
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = evidence

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("pr_gate evidence" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_string_sensitive_flag_with_remote_evidence() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["enforcement_sensitive"] = "true"
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = "https://github.com/example/repo/actions/runs/1"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "enforcement_sensitive must be a boolean or null" in error
        for error in result["errors"]
    )


@pytest.mark.parametrize("malformed", ["true", 1, 0, 1.5, [], {}])
def test_runtime_ledger_gate_blocks_malformed_sensitive_flag_in_non_merge_state(
    malformed: object,
) -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["state"] = "running"
    item["enforcement_sensitive"] = malformed

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "enforcement_sensitive must be a boolean or null" in error
        for error in result["errors"]
    )


def test_runtime_ledger_gate_blocks_unreadable_sensitive_pr_gate_evidence(
    tmp_path: Path,
) -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["enforcement_sensitive"] = True
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = str(tmp_path / "missing-pr-gate.json")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("evidence file does not exist" in error for error in result["errors"])


def test_runtime_ledger_gate_preserves_remote_evidence_for_non_sensitive_item() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = "https://github.com/example/repo/actions/runs/1"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_runtime_ledger_gate_preserves_remote_evidence_for_explicit_false_flag() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["enforcement_sensitive"] = False
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = "https://github.com/example/repo/actions/runs/1"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_runtime_ledger_gate_preserves_remote_evidence_for_null_flag() -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["enforcement_sensitive"] = None
    pr_gate = item["pr_gate"]
    assert isinstance(pr_gate, dict)
    pr_gate["evidence"] = "https://github.com/example/repo/actions/runs/1"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


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
            "--repo",
            str(ROOT),
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


def test_runtime_ledger_passes_explicit_repo_for_raw_sensitive_pr_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    item["enforcement_sensitive"] = True
    raw_path = tmp_path / "raw-pr.json"
    raw_path.write_text(json.dumps({"pr": 718, "head_sha": item["head_sha"]}), encoding="utf-8")
    item["pr_gate"]["evidence"] = str(raw_path)
    observed: dict[str, object] = {}

    def fake_gate(payload: dict[str, object], *, repo: Path, config: object) -> dict[str, object]:
        observed.update({"payload": payload, "repo": repo, "config": config})
        return {
            "decision": "allowed", "pr": 718, "head_sha": item["head_sha"],
            "enforcement_sensitive": True,
        }

    monkeypatch.setattr("runtime_ledger_gate.evaluate_pr_gate", fake_gate)
    config = object()

    result = evaluate_checkpoint(checkpoint, repo=ROOT, config=config)  # type: ignore[arg-type]

    assert result["decision"] == "allowed"
    assert observed["repo"] == ROOT
    assert observed["config"] is config


def test_runtime_ledger_blocks_raw_sensitive_evidence_without_repo(
    tmp_path: Path,
) -> None:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    item["enforcement_sensitive"] = True
    raw = json.loads(
        (ROOT / "examples" / "fixtures" / "pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    raw["enforcement_sensitive"] = True
    raw_path = tmp_path / "raw-sensitive-pr.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    item["pr_gate"]["evidence"] = str(raw_path)

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("repository checkout is required" in error for error in result["errors"])
