from __future__ import annotations

import json

from runtime_ledger_test_support import (  # noqa: E402
    ROOT,
    _fixture_checkpoint,
    clean_checkpoint,
)
from pr_review_contract import evaluate_review_contract  # noqa: E402
from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402


def _pr_evidence(name: str) -> dict[str, object]:
    return json.loads(
        (ROOT / "examples" / "fixtures" / name).read_text(encoding="utf-8")
    )


def test_review_contract_rejects_forged_non_actionable_thread_override() -> None:
    evidence = _pr_evidence("pr-clean-authorized.json")
    thread = evidence["review_threads"][0]  # type: ignore[index]
    thread.update(  # type: ignore[union-attr]
        {
            "is_resolved": True,
            "actionable": False,
            "resolved_by": "implementer",
            "resolver_role": "implementer",
        }
    )

    _, _, reasons = evaluate_review_contract(evidence)

    assert any("forbidden implementer" in reason for reason in reasons)


def test_review_contract_requires_exact_self_review_pr_scope() -> None:
    evidence = _pr_evidence("pr-self-review-unauthorized.json")
    evidence["self_review_authorization"] = {
        "actor": "maintainer",
        "source": "chat",
        "scope": f"PR #1718 exact head {evidence['head_sha']}",
    }

    _, _, reasons = evaluate_review_contract(evidence)

    assert "self_review_authorization.scope must bind the same PR and head_sha" in reasons


def test_review_contract_requires_resolver_lane_proof() -> None:
    evidence = _pr_evidence("pr-clean-authorized.json")
    thread = evidence["review_threads"][0]  # type: ignore[index]
    thread.pop("lane_id")  # type: ignore[union-attr]

    _, _, reasons = evaluate_review_contract(evidence)

    assert any("lacks original/successor re-review evidence" in reason for reason in reasons)


def test_review_contract_rejects_unrelated_root_reviewer_resolver() -> None:
    evidence = _pr_evidence("pr-clean-authorized.json")
    thread = evidence["review_threads"][0]  # type: ignore[index]
    thread["original_author"] = "different-reviewer"  # type: ignore[index]

    _, _, reasons = evaluate_review_contract(evidence)

    assert any("lacks original/successor re-review evidence" in reason for reason in reasons)


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


def test_runtime_ledger_gate_blocks_merge_ready_without_review_manifest() -> None:
    checkpoint = clean_checkpoint()
    del checkpoint["items"][0]["review"]["manifest"]  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("review.manifest" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_terminal_review_head_mismatch() -> None:
    checkpoint = clean_checkpoint()
    checkpoint["items"][0]["review"]["head_sha"] = "f" * 40  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("head_sha must match" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_actionable_terminal_finding() -> None:
    checkpoint = clean_checkpoint()
    checkpoint["items"][0]["review"]["findings"] = [  # type: ignore[index]
        {
            "id": "finding-current",
            "severity": "important",
            "actionable": True,
            "summary": "Current blocking finding.",
        }
    ]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("blocking/actionable finding" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_self_review_without_human_final_gate() -> None:
    checkpoint = _fixture_checkpoint("runtime-self-review-merged-unauthorized.json")
    checkpoint["items"][0]["self_review_authorization"] = {  # type: ignore[index]
        "scope": "merge PR #718 after self-review only",
        "conversation_marker": "user message: reviewer lanes are down, self-review this one",
    }
    checkpoint["items"][0]["review"]["human_final_review_required"] = False  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("human_final_review_required" in error for error in result["errors"])
