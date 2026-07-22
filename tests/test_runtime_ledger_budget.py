from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from runtime_ledger_test_support import (  # noqa: E402
    ROOT,
    _fixture_checkpoint,
)
from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402


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
