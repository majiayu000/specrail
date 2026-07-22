from __future__ import annotations

import json
from pathlib import Path

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


def test_runtime_ledger_gate_blocks_merge_ready_without_review_execution() -> None:
    checkpoint = clean_checkpoint()
    del checkpoint["items"][0]["review"]["review_execution"]  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("review.review_execution" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_hosted_review_as_primary() -> None:
    checkpoint = clean_checkpoint()
    checkpoint["items"][0]["review"]["review_execution"] = "hosted"  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("supplemental only" in error for error in result["errors"])


def _checkpoint_with_review_artifact(
    tmp_path: Path,
    *,
    review_execution: str | None,
    **artifact_overrides: object,
) -> dict[str, object]:
    artifact = json.loads(
        (ROOT / "tests" / "fixtures" / "gh143-review-artifact-pr718.json").read_text(
            encoding="utf-8"
        )
    )
    if review_execution is None:
        artifact.pop("review_execution")
    else:
        artifact["review_execution"] = review_execution
    artifact.update(artifact_overrides)
    artifact_path = tmp_path / "review.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    checkpoint = clean_checkpoint()
    checkpoint["items"][0]["review"]["evidence"] = str(artifact_path)  # type: ignore[index]
    return checkpoint


def test_runtime_ledger_gate_blocks_hosted_artifact_behind_local_summary(
    tmp_path: Path,
) -> None:
    result = evaluate_checkpoint(
        _checkpoint_with_review_artifact(tmp_path, review_execution="hosted")
    )

    assert result["decision"] == "blocked"
    assert any("hosted review artifact" in error for error in result["errors"])
    assert any("must match review artifact" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_legacy_artifact_behind_local_summary(
    tmp_path: Path,
) -> None:
    result = evaluate_checkpoint(
        _checkpoint_with_review_artifact(tmp_path, review_execution=None)
    )

    assert result["decision"] == "blocked"
    assert any(
        "review artifact requires review_execution" in error
        for error in result["errors"]
    )


def test_runtime_ledger_gate_blocks_artifact_for_another_pr(tmp_path: Path) -> None:
    result = evaluate_checkpoint(
        _checkpoint_with_review_artifact(
            tmp_path, review_execution="local", pr=999
        )
    )

    assert result["decision"] == "blocked"
    assert any("artifact.pr must match item pr" in error for error in result["errors"])


def test_runtime_ledger_gate_blocks_artifact_from_another_lane(tmp_path: Path) -> None:
    result = evaluate_checkpoint(
        _checkpoint_with_review_artifact(
            tmp_path,
            review_execution="local",
            reviewer_lane="unregistered-reviewer",
        )
    )

    assert result["decision"] == "blocked"
    assert any(
        "review.reviewer_lane must match review artifact.reviewer_lane" in error
        for error in result["errors"]
    )


def test_runtime_ledger_gate_blocks_artifact_with_invalid_timestamps(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint_with_review_artifact(
        tmp_path,
        review_execution="local",
        review_started_at="not-a-time",
        review_completed_at="also-not-a-time",
    )
    checkpoint["items"][0]["review"]["review_completed_at"] = "also-not-a-time"  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "timezone-aware ISO-8601 timestamp" in error for error in result["errors"]
    )


def test_runtime_ledger_gate_blocks_clean_artifact_with_nit_finding(
    tmp_path: Path,
) -> None:
    findings = [
        {
            "id": "nit-present",
            "severity": "nit",
            "actionable": False,
            "summary": "A clean verdict cannot contain findings.",
        }
    ]
    checkpoint = _checkpoint_with_review_artifact(
        tmp_path, review_execution="local", findings=findings
    )
    checkpoint["items"][0]["review"]["findings"] = findings  # type: ignore[index]

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("clean verdict requires zero findings" in error for error in result["errors"])


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


def _auto_self_review_checkpoint(lane_ids: list[str]) -> dict[str, object]:
    checkpoint = _fixture_checkpoint("runtime-self-review-merged-unauthorized.json")
    checkpoint["auth_mode"] = "auto"
    item = checkpoint["items"][0]  # type: ignore[index]
    item["self_review_authorization"] = {
        "scope": "merge PR #718 after double reviewer-lane failure",
        "conversation_marker": "implx auto invocation after two lane failures",
    }
    item["lane_failures"] = [
        {
            "lane_id": lane_id,
            "failure_kind": "crash",
            "observed_marker": f"{lane_id or 'lane'} crashed mid-review",
        }
        for lane_id in lane_ids
    ]
    return checkpoint


def test_auto_self_review_blocks_single_lane_failure() -> None:
    result = evaluate_checkpoint(_auto_self_review_checkpoint(["merge-reviewer-1"]))

    assert result["decision"] == "blocked"
    assert any(
        "two distinct failed reviewer lanes (found 1)" in error
        for error in result["errors"]
    )


def test_auto_self_review_allows_two_distinct_lane_failures() -> None:
    result = evaluate_checkpoint(
        _auto_self_review_checkpoint(["merge-reviewer-1", "merge-reviewer-2"])
    )

    assert result["decision"] in {"allowed", "warn"}, result["errors"]


def test_auto_self_review_blocks_duplicate_lane_ids() -> None:
    result = evaluate_checkpoint(
        _auto_self_review_checkpoint(["merge-reviewer-1", "merge-reviewer-1"])
    )

    assert result["decision"] == "blocked"
    assert any(
        "two distinct failed reviewer lanes (found 1)" in error
        for error in result["errors"]
    )


def test_auto_self_review_ignores_blank_lane_ids() -> None:
    result = evaluate_checkpoint(
        _auto_self_review_checkpoint(["merge-reviewer-1", "   "])
    )

    assert result["decision"] == "blocked"
    assert any(
        "two distinct failed reviewer lanes (found 1)" in error
        for error in result["errors"]
    )


def test_auto_self_review_auth_mode_is_case_insensitive() -> None:
    checkpoint = _auto_self_review_checkpoint(["merge-reviewer-1"])
    checkpoint["auth_mode"] = "  AUTO "

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "two distinct failed reviewer lanes" in error for error in result["errors"]
    )


def test_auto_single_lane_failure_non_merge_state_not_gated() -> None:
    checkpoint = _auto_self_review_checkpoint(["merge-reviewer-1"])
    item = checkpoint["items"][0]  # type: ignore[index]
    item["state"] = "blocked"
    item["blocked_reason"] = "reviewer_lane_failure"

    result = evaluate_checkpoint(checkpoint)

    assert not any(
        "two distinct failed reviewer lanes" in error for error in result["errors"]
    )


def test_review_mode_self_review_keeps_single_lane_behavior() -> None:
    checkpoint = _auto_self_review_checkpoint(["merge-reviewer-1"])
    checkpoint["auth_mode"] = "review"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] in {"allowed", "warn"}, result["errors"]
