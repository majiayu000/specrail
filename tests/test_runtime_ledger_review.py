from __future__ import annotations

from runtime_ledger_test_support import (  # noqa: E402
    ROOT,
    _fixture_checkpoint,
    clean_checkpoint,
)
from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402


def test_runtime_ledger_gate_blocks_merge_ready_without_review_source() -> None:
    checkpoint = clean_checkpoint()
    del checkpoint["items"][0]["review"]["review_source"]  # type: ignore[index]
    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("review.review_source" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_unauthorized_self_review_merge() -> None:
    result = evaluate_checkpoint(
        _fixture_checkpoint("runtime-self-review-merged-unauthorized.json")
    )

    assert result["decision"] == "blocked"
    assert any("self_review_authorization" in error for error in result["errors"])


def test_runtime_ledger_gate_allows_authorized_self_review_merge() -> None:
    checkpoint = _fixture_checkpoint("runtime-self-review-merged-unauthorized.json")
    checkpoint["items"][0]["self_review_authorization"] = {  # type: ignore[index]
        "scope": "merge PR #718 after self-review only",
        "conversation_marker": "user message: reviewer lanes are down, self-review this one",
    }
    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] in {"allowed", "warn"}, result["errors"]


def test_runtime_ledger_gate_blocks_authorized_self_review_without_lane_failure() -> None:
    checkpoint = _fixture_checkpoint("runtime-self-review-merged-unauthorized.json")
    item = checkpoint["items"][0]  # type: ignore[index]
    item["lane_failures"] = []
    item["self_review_authorization"] = {
        "scope": "merge PR #718 after self-review only",
        "conversation_marker": "user message: reviewer lanes are down, self-review this one",
    }

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("self_review requires recorded lane_failures" in error for error in result["errors"])


def test_runtime_ledger_gate_allows_blocked_lane_failure_fixture() -> None:
    result = evaluate_checkpoint(_fixture_checkpoint("runtime-lane-failure-blocked.json"))

    assert result["decision"] in {"allowed", "warn"}, result["errors"]


def test_runtime_ledger_gate_allows_retried_lane_failure_fixture() -> None:
    result = evaluate_checkpoint(_fixture_checkpoint("runtime-lane-failure-retried.json"))

    assert result["decision"] in {"allowed", "warn"}, result["errors"]


def test_runtime_ledger_gate_blocks_unreported_lane_failure_fixture() -> None:
    result = evaluate_checkpoint(
        _fixture_checkpoint("runtime-lane-failure-unreported.json")
    )

    assert result["decision"] == "blocked"
    assert any("reviewer lane failure" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_lane_failure_downgrade_without_reason() -> None:
    checkpoint = _fixture_checkpoint("runtime-lane-failure-blocked.json")
    del checkpoint["items"][0]["blocked_reason"]  # type: ignore[index]
    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("blocked_reason" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_retry_from_failed_lane() -> None:
    checkpoint = _fixture_checkpoint("runtime-lane-failure-retried.json")
    checkpoint["items"][0]["review"]["reviewer_lane"] = "merge-reviewer-1"  # type: ignore[index]
    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("reviewer lane failure" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_self_review_as_retry() -> None:
    checkpoint = _fixture_checkpoint("runtime-lane-failure-retried.json")
    checkpoint["items"][0]["review"]["review_source"] = "self_review"  # type: ignore[index]
    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("reviewer lane failure" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_other_failure_kind_without_detail() -> None:
    checkpoint = _fixture_checkpoint("runtime-lane-failure-blocked.json")
    checkpoint["items"][0]["lane_failures"][0]["failure_kind"] = "other"  # type: ignore[index]
    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("requires detail" in error for error in result["errors"])
