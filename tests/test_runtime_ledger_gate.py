from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from runtime_ledger_test_support import (  # noqa: E402
    ROOT,
    _fixture_checkpoint,
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


# --- GH-137: checkpoint_version 3 trusted runtime budgets ---


def _v3_now(checkpoint: dict[str, object], minutes: int = 5) -> datetime:
    raw = str(checkpoint["tranche_started_at"]).replace("Z", "+00:00")
    return datetime.fromisoformat(raw) + timedelta(minutes=minutes)


def _v3_fixture(name: str) -> tuple[dict[str, object], datetime]:
    checkpoint = _fixture_checkpoint(name)
    return checkpoint, _v3_now(checkpoint)


def test_blocked_when_runtime_observed_exceeds_budget_despite_low_self_report() -> None:
    checkpoint, now = _v3_fixture("runtime-telemetry-mismatch-blocked.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: compaction observed 2 > limit 1" in error
        for error in result["errors"]
    )
    assert any(
        "compaction telemetry mismatch: observed 2 vs self-reported 0" in warning
        for warning in result["warnings"]
    )


def test_compaction_basis_rejected_without_telemetry() -> None:
    checkpoint, now = _v3_fixture(
        "runtime-telemetry-unavailable-compaction-basis.json"
    )

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "telemetry_source unavailable" in error
        and "item_cap or runtime_dims" in error
        for error in result["errors"]
    )
    assert not any(
        "budget exceeded: compaction" in error for error in result["errors"]
    )


def test_goal_active_second_compaction_blocked() -> None:
    checkpoint, now = _v3_fixture("runtime-goal-active-second-compaction.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: compaction observed 2 > limit 1" in error
        for error in result["errors"]
    )


def test_wall_clock_exceeded_blocked() -> None:
    checkpoint, now = _v3_fixture("runtime-wall-clock-exceeded-blocked.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: wall_clock observed 300 > limit 120" in error
        for error in result["errors"]
    )


def test_tool_calls_exceeded_blocked() -> None:
    checkpoint, now = _v3_fixture("runtime-tool-calls-exceeded-blocked.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: tool_calls observed 861 > limit 250" in error
        for error in result["errors"]
    )


def test_review_rounds_exceeded_blocked() -> None:
    checkpoint, now = _v3_fixture("runtime-review-rounds-exceeded-blocked.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: review_rounds observed 3 > limit 2" in error
        for error in result["errors"]
    )


def test_full_test_runs_exceeded_blocked() -> None:
    checkpoint, now = _v3_fixture("runtime-full-test-runs-exceeded-blocked.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: full_test_runs observed 3 > limit 1" in error
        for error in result["errors"]
    )


def test_wall_clock_recomputed_from_tranche_started_at_beats_self_report() -> None:
    checkpoint, _ = _v3_fixture("runtime-new-tranche-reset.json")
    late_now = _v3_now(checkpoint, minutes=300)

    result = evaluate_checkpoint(checkpoint, now=late_now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: wall_clock observed 300 > limit 120" in error
        for error in result["errors"]
    )


@pytest.mark.parametrize("bad_limit", [0, -1, True, 1.5, "250"])
def test_invalid_dimension_limits_fail_validation(bad_limit: object) -> None:
    checkpoint, now = _v3_fixture("runtime-tool-calls-exceeded-blocked.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget["observed_tool_calls"] = 10
    budget["max_tool_calls"] = bad_limit

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget.max_tool_calls must be a positive integer" in error
        for error in result["errors"]
    )


def test_override_is_per_dimension() -> None:
    checkpoint, now = _v3_fixture("runtime-override-per-dimension.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: wall_clock observed 200 > limit 120" in error
        for error in result["errors"]
    )
    assert not any("tool_calls" in error for error in result["errors"])
    assert any(
        "tool_calls budget exceeded under a recorded per-dimension" in entry
        for entry in result["satisfied"]
    )


def test_new_tranche_resets_observed_counters() -> None:
    checkpoint, now = _v3_fixture("runtime-new-tranche-reset.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_v3_drain_checkpoint_requires_budget() -> None:
    checkpoint, now = _v3_fixture("runtime-new-tranche-reset.json")
    checkpoint.pop("budget")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "full_queue_drain checkpoint requires a declared budget" in error
        for error in result["errors"]
    )


def test_v3_requires_observed_counters() -> None:
    checkpoint, now = _v3_fixture("runtime-new-tranche-reset.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget.pop("observed_tool_calls")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget.observed_tool_calls must be a recorded non-negative integer" in error
        for error in result["errors"]
    )


def test_v3_full_test_count_requires_head_sha() -> None:
    checkpoint, now = _v3_fixture("runtime-new-tranche-reset.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget["observed_full_test_runs_current_head"] = 1

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget.full_test_head_sha is required" in error for error in result["errors"]
    )


def test_v3_stale_full_test_head_must_reset() -> None:
    checkpoint, now = _v3_fixture("runtime-full-test-runs-exceeded-blocked.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget["full_test_head_sha"] = "1234567890abcdef1234567890abcdef12345678"
    budget["observed_full_test_runs_current_head"] = 1

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "does not match the current PR head" in error for error in result["errors"]
    )


def test_v3_rejects_legacy_single_budget_override() -> None:
    checkpoint, now = _v3_fixture("runtime-override-per-dimension.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget["budget_override"] = {
        "scope": "keep going",
        "conversation_marker": "user message: keep going",
    }

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget.budget_override is a version-2 structure" in error
        for error in result["errors"]
    )


def test_v3_unavailable_telemetry_flags_self_reported_provenance() -> None:
    checkpoint, now = _v3_fixture("runtime-wall-clock-exceeded-blocked.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert any(
        "provenance: self_reported: tool_calls" in warning
        for warning in result["warnings"]
    )


def test_overridden_overrun_stays_visible_as_warning() -> None:
    checkpoint, now = _v3_fixture("runtime-override-per-dimension.json")

    result = evaluate_checkpoint(checkpoint, now=now)

    assert any(
        "budget overridden: tool_calls observed" in warning
        for warning in result["warnings"]
    )
    assert any(
        "tool_calls budget exceeded under a recorded per-dimension" in entry
        for entry in result["satisfied"]
    )


def test_v3_item_cap_is_enforced_against_item_records() -> None:
    checkpoint, now = _v3_fixture("runtime-new-tranche-reset.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget["basis"] = "item_cap"
    budget["item_cap"] = 1
    items = checkpoint["items"]
    assert isinstance(items, list)
    items.append(dict(items[0]))

    result = evaluate_checkpoint(checkpoint, now=now)

    assert result["decision"] == "blocked"
    assert any(
        "budget exceeded: item_cap observed 2 > limit 1" in error
        for error in result["errors"]
    )


def test_v3_item_cap_overrun_with_override_is_allowed_with_warning() -> None:
    checkpoint, now = _v3_fixture("runtime-new-tranche-reset.json")
    budget = checkpoint["budget"]
    assert isinstance(budget, dict)
    budget["basis"] = "item_cap"
    budget["item_cap"] = 1
    budget["budget_overrides"] = [
        {
            "dimension": "item_cap",
            "scope": "finish the second item in this tranche",
            "conversation_marker": "user message: keep going past the cap",
        }
    ]
    items = checkpoint["items"]
    assert isinstance(items, list)
    items.append(dict(items[0]))

    result = evaluate_checkpoint(checkpoint, now=now)

    assert not any("item_cap" in error for error in result["errors"])
    assert any(
        "budget overridden: item_cap observed 2 > limit 1" in warning
        for warning in result["warnings"]
    )


def test_v3_future_tranche_started_at_is_rejected() -> None:
    checkpoint, _ = _v3_fixture("runtime-new-tranche-reset.json")
    early_now = _v3_now(checkpoint, minutes=-10)

    result = evaluate_checkpoint(checkpoint, now=early_now)

    assert result["decision"] == "blocked"
    assert any(
        "tranche_started_at" in error and "in the future" in error
        for error in result["errors"]
    )


def test_v3_small_clock_skew_is_tolerated() -> None:
    checkpoint, _ = _v3_fixture("runtime-new-tranche-reset.json")
    skew_now = _v3_now(checkpoint, minutes=-1)

    result = evaluate_checkpoint(checkpoint, now=skew_now)

    assert result["decision"] == "allowed"
    assert not any("in the future" in error for error in result["errors"])


def test_v2_budget_fixtures_keep_their_decisions() -> None:
    expectations = {
        "runtime-budget-exhausted-handoff.json": "allowed",
        "runtime-budget-over-continuation.json": "blocked",
        "runtime-budget-override.json": "allowed",
        "runtime-drain-missing-budget.json": "blocked",
    }
    for name, expected in expectations.items():
        result = evaluate_checkpoint(_fixture_checkpoint(name))
        assert result["decision"] == expected, name


def test_skill_md_has_no_goal_active_compaction_exemption() -> None:
    skill = (
        ROOT / "skills" / "specrail-implement-queue" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "not a handoff trigger" not in skill
    assert "Goal-active compaction exemption" not in skill
    assert "Goal/session decoupling" in skill
    assert "checks/session_telemetry.py" in skill


# --- GH-143: tiered merge authorization ---


HEAD_SHA = "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"


def _review_artifact_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_id": "pr718-head1-reviewer1",
        "pr": 718,
        "reviewer_lane": "merge-reviewer-1",
        "producer_identity": "reviewer-1",
        "review_source": "independent_lane",
        "head_sha": HEAD_SHA,
        "review_started_at": "2026-06-30T11:55:00Z",
        "review_completed_at": "2026-06-30T12:00:00Z",
        "status": "completed",
        "verdict": "clean",
        "human_final_review_required": False,
        "findings": [],
        "prior_findings": [],
        "body": "## Summary\nTier-attested review.\n\n## Verdict\nclean",
        "comments": [],
        "tier_attestation": {
            "pr_tier": "standard",
            "attested": True,
            "basis": "changed-line count and touched paths verified by reviewer lane",
        },
    }
    payload.update(overrides)
    return payload


def _standard_auto_checkpoint(
    tmp_path: Path, **artifact_overrides: object
) -> dict[str, object]:
    checkpoint = clean_checkpoint()
    checkpoint["auth_mode"] = "review"
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["pr_tier"] = "standard"
    item["pr_tier_evidence"] = {
        "changed_lines": 42,
        "touched_paths": ["checks/example.py", "tests/test_example.py"],
    }
    item["authorization_tier"] = "standard_auto"
    item["merge_authorization"] = {
        "actor": "specrail-tier-policy",
        "source": "tier_policy_gh143",
        "summary": "GH-143 decision B tier authorization",
    }
    artifact_path = tmp_path / "review-artifact.json"
    artifact_path.write_text(
        json.dumps(_review_artifact_payload(**artifact_overrides)),
        encoding="utf-8",
    )
    review = item["review"]
    assert isinstance(review, dict)
    review["evidence"] = str(artifact_path)
    return checkpoint


def test_standard_auto_merge_ready_allowed(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path)

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_standard_auto_allowed_via_ci_tier_check_artifact(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    artifact_path = tmp_path / "review-artifact.json"
    payload = _review_artifact_payload()
    payload.pop("tier_attestation")
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    ci_path = tmp_path / "ci-tier-check.json"
    ci_path.write_text(
        json.dumps({"pr_tier": "standard", "status": "passed"}), encoding="utf-8"
    )
    item["ci_tier_check"] = {"evidence": str(ci_path)}

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_standard_auto_requires_review_auth_mode(tmp_path: Path) -> None:
    for auth_mode in ["auto", None]:
        checkpoint = _standard_auto_checkpoint(tmp_path)
        if auth_mode is None:
            checkpoint.pop("auth_mode")
        else:
            checkpoint["auth_mode"] = auth_mode

        result = evaluate_checkpoint(checkpoint)

        assert result["decision"] == "blocked"
        assert any(
            "only valid when checkpoint auth_mode is review" in error
            for error in result["errors"]
        )


def test_heavy_or_sensitive_rejects_standard_auto(tmp_path: Path) -> None:
    heavy = _standard_auto_checkpoint(tmp_path)
    heavy_item = heavy["items"][0]  # type: ignore[index]
    assert isinstance(heavy_item, dict)
    heavy_item["pr_tier"] = "heavy"

    result = evaluate_checkpoint(heavy)

    assert result["decision"] == "blocked"
    assert any(
        "pr_tier heavy requires heavy_manual" in error for error in result["errors"]
    )

    sensitive = _standard_auto_checkpoint(tmp_path)
    sensitive_item = sensitive["items"][0]  # type: ignore[index]
    assert isinstance(sensitive_item, dict)
    sensitive_item["enforcement_sensitive"] = True

    result = evaluate_checkpoint(sensitive)

    assert result["decision"] == "blocked"
    assert any(
        "enforcement-sensitive item cannot use standard_auto" in error
        for error in result["errors"]
    )


def test_missing_or_unevidenced_tier_fails_closed(tmp_path: Path) -> None:
    missing_tier = _standard_auto_checkpoint(tmp_path)
    item = missing_tier["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item.pop("pr_tier")

    result = evaluate_checkpoint(missing_tier)

    assert result["decision"] == "blocked"
    assert any("fails closed to heavy_manual" in error for error in result["errors"])

    invalid_tier = _standard_auto_checkpoint(tmp_path)
    item = invalid_tier["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["pr_tier"] = "express"

    result = evaluate_checkpoint(invalid_tier)

    assert result["decision"] == "blocked"
    assert any("missing or invalid pr_tier" in error for error in result["errors"])

    no_evidence = _standard_auto_checkpoint(tmp_path)
    item = no_evidence["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item.pop("pr_tier_evidence")

    result = evaluate_checkpoint(no_evidence)

    assert result["decision"] == "blocked"
    assert any(
        "requires pr_tier_evidence" in error for error in result["errors"]
    )


def test_invalid_authorization_tier_value_blocked(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["authorization_tier"] = "self_auto"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "authorization_tier must be one of" in error for error in result["errors"]
    )


def test_disputed_tier_blocks_standard_auto(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path, tier_dispute=True)

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "reviewer lane recorded tier_dispute" in error for error in result["errors"]
    )


def test_attestation_tier_mismatch_treated_as_dispute(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(
        tmp_path,
        tier_attestation={
            "pr_tier": "fastlane",
            "attested": True,
            "basis": "reviewer counted the diff differently",
        },
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "tier dispute" in error and "tier_attestation" in error
        for error in result["errors"]
    )


def test_implementer_side_dispute_flag_not_trusted(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path, tier_dispute=True)
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["tier_dispute"] = False

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "reviewer lane recorded tier_dispute" in error for error in result["errors"]
    )


def test_evidence_gap_not_covered_by_tier_authorization(tmp_path: Path) -> None:
    def gapped(mutate) -> dict[str, object]:
        checkpoint = _standard_auto_checkpoint(tmp_path)
        item = checkpoint["items"][0]  # type: ignore[index]
        assert isinstance(item, dict)
        mutate(item)
        return checkpoint

    gaps = [
        lambda item: item["ci"].update({"status": "pending"}),
        lambda item: item["review_threads"].update({"unresolved_count": 2}),
        lambda item: item["pr_gate"].update({"status": "blocked"}),
        lambda item: item["review"].update({"verdict": "blocking"}),
    ]
    for mutate in gaps:
        result = evaluate_checkpoint(gapped(mutate))
        assert result["decision"] == "blocked"


def test_standard_auto_requires_independent_tier_substantiation(
    tmp_path: Path,
) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path)
    payload = _review_artifact_payload()
    payload.pop("tier_attestation")
    (tmp_path / "review-artifact.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "independent tier substantiation" in error for error in result["errors"]
    )


def test_standard_auto_stale_attestation_head_not_substantiating(
    tmp_path: Path,
) -> None:
    checkpoint = _standard_auto_checkpoint(
        tmp_path, head_sha="1234567890abcdef1234567890abcdef12345678"
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "artifact head_sha must match item head_sha" in error
        for error in result["errors"]
    )


def test_standard_auto_missing_audit_fields_blocked(tmp_path: Path) -> None:
    for field in ["pr_tier", "pr_tier_evidence", "authorization_tier"]:
        checkpoint = _standard_auto_checkpoint(tmp_path)
        item = checkpoint["items"][0]  # type: ignore[index]
        assert isinstance(item, dict)
        item.pop(field)

        result = evaluate_checkpoint(checkpoint)

        assert result["decision"] == "blocked", field


def test_standard_auto_wrong_source_for_tier_blocked(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["merge_authorization"] = {
        "actor": "maintainer",
        "source": "chat",
        "summary": "you can merge",
    }

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "standard_auto requires merge_authorization.source tier_policy_gh143"
        in error
        for error in result["errors"]
    )


def test_heavy_manual_with_tier_policy_source_blocked(tmp_path: Path) -> None:
    checkpoint = _standard_auto_checkpoint(tmp_path)
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["authorization_tier"] = "heavy_manual"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "heavy_manual requires per-PR human authorization" in error
        for error in result["errors"]
    )


# --- GH-143: graded re-confirmation of post-authorization findings ---


def _findings_checkpoint(
    tmp_path: Path,
    findings: list[dict[str, object]],
    classifications: list[dict[str, object]] | None,
) -> dict[str, object]:
    checkpoint = clean_checkpoint()
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["post_authorization_findings"] = findings
    payload = _review_artifact_payload()
    payload.pop("tier_attestation")
    if classifications is not None:
        payload["finding_classifications"] = classifications
    artifact_path = tmp_path / "review-artifact.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    review = item["review"]
    assert isinstance(review, dict)
    review["evidence"] = str(artifact_path)
    return checkpoint


def test_mechanical_findings_merge_within_original_authorization(
    tmp_path: Path,
) -> None:
    checkpoint = _findings_checkpoint(
        tmp_path,
        findings=[
            {
                "finding_ref": "F-1",
                "severity": "important",
                "mechanical": True,
                "disposition": "fixed_re_reviewed",
            }
        ],
        classifications=[
            {"finding_ref": "F-1", "severity": "important", "mechanical": True}
        ],
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_critical_finding_requires_re_authorization(tmp_path: Path) -> None:
    checkpoint = _findings_checkpoint(
        tmp_path,
        findings=[
            {
                "finding_ref": "F-2",
                "severity": "critical",
                "mechanical": False,
                "disposition": "paused_re_authorized",
            }
        ],
        classifications=[
            {"finding_ref": "F-2", "severity": "critical", "mechanical": False}
        ],
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("requires a new" in error and "re_authorization" in error for error in result["errors"])

    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["re_authorization"] = {
        "actor": "maintainer",
        "source": "chat",
        "summary": "re-authorized after critical finding review",
    }

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "allowed"
    assert result["errors"] == []


def test_unknown_severity_treated_as_critical(tmp_path: Path) -> None:
    checkpoint = _findings_checkpoint(
        tmp_path,
        findings=[
            {
                "finding_ref": "F-3",
                "severity": "mystery",
                "mechanical": True,
                "disposition": "fixed_re_reviewed",
            }
        ],
        classifications=[
            {"finding_ref": "F-3", "severity": "mystery", "mechanical": True}
        ],
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("severity must be one of" in error for error in result["errors"])
    assert any("treated as critical" in error for error in result["errors"])


def test_implementer_only_classification_treated_as_critical(
    tmp_path: Path,
) -> None:
    checkpoint = _findings_checkpoint(
        tmp_path,
        findings=[
            {
                "finding_ref": "F-4",
                "severity": "minor",
                "mechanical": True,
                "disposition": "fixed_re_reviewed",
            }
        ],
        classifications=None,
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "implementer self-classification is not trusted" in error
        for error in result["errors"]
    )


def test_classification_mismatch_treated_as_critical(tmp_path: Path) -> None:
    checkpoint = _findings_checkpoint(
        tmp_path,
        findings=[
            {
                "finding_ref": "F-5",
                "severity": "minor",
                "mechanical": True,
                "disposition": "fixed_re_reviewed",
            }
        ],
        classifications=[
            {"finding_ref": "F-5", "severity": "important", "mechanical": False}
        ],
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "disagrees with the reviewer-lane record" in error
        for error in result["errors"]
    )


def test_mechanical_finding_requires_fixed_re_reviewed_disposition(
    tmp_path: Path,
) -> None:
    checkpoint = _findings_checkpoint(
        tmp_path,
        findings=[
            {
                "finding_ref": "F-6",
                "severity": "minor",
                "mechanical": True,
                "disposition": "paused_re_authorized",
            }
        ],
        classifications=[
            {"finding_ref": "F-6", "severity": "minor", "mechanical": True}
        ],
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "requires disposition fixed_re_reviewed" in error
        for error in result["errors"]
    )


def test_gh143_standard_auto_fixture_cli_allowed() -> None:
    fixture_path = ROOT / "tests" / "fixtures" / "gh143-standard-auto.json"
    result = subprocess.run(
        [
            sys.executable,
            "checks/runtime_ledger_gate.py",
            "--checkpoint",
            str(fixture_path),
            "--repo",
            str(ROOT),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
