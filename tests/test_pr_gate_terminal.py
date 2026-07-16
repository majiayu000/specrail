from __future__ import annotations

from pr_gate_test_support import ROOT, clean_evidence, evaluate_pr_gate, fixture


def test_pr_gate_blocks_missing_review_source() -> None:
    evidence = clean_evidence()
    del evidence["review_source"]
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review_source" in result["missing"]


def test_pr_gate_blocks_self_review_source() -> None:
    evidence = fixture("pr-self-review-source.json")
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("self_review" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unknown_review_source() -> None:
    evidence = clean_evidence()
    evidence["review_source"] = "coordinator_summary"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("review_source must be one of" in reason for reason in result["reasons"])


def test_pr_gate_allows_confirmed_merge_record() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-confirmed.json"))

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_allows_confirmed_api_fallback_merge() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-api-fallback-confirmed.json"))

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_unconfirmed_merge_record() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-unconfirmed-local-failure.json"))

    assert result["decision"] == "blocked"
    assert any("remote_confirmed" in reason for reason in result["reasons"])


def test_pr_gate_blocks_merge_record_missing_path() -> None:
    result = evaluate_pr_gate(fixture("pr-merge-missing-path.json"))

    assert result["decision"] == "blocked"
    assert "merge_record.merge_path" in result["missing"]


def test_pr_gate_allows_merged_by_other_terminal() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_record"]["merge_path"] = "merged_by_other"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_review_source_without_terminal_manifest_evidence() -> None:
    evidence = clean_evidence()
    evidence.pop("review_evidence")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("review_source alone" in reason for reason in result["reasons"])


def test_pr_gate_blocks_review_completed_after_gate_started() -> None:
    evidence = clean_evidence()
    evidence["review_completed_at"] = "2026-07-04T00:00:01Z"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review must complete at or before gate start" in result["reasons"]


def test_pr_gate_blocks_gate_started_after_query_completed() -> None:
    evidence = clean_evidence()
    evidence["gate_started_at"] = "2026-07-04T00:00:01Z"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate_started_at must be at or before gate_query_completed_at" in result["reasons"]


def test_pr_gate_rejects_noncanonical_gate_completed_alias() -> None:
    evidence = clean_evidence()
    evidence["gate_completed_at"] = evidence["gate_query_completed_at"]

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("alias is unsupported" in reason for reason in result["reasons"])


def test_pr_gate_blocks_current_head_actionable_artifact_finding() -> None:
    evidence = clean_evidence()
    artifact = evidence["review_evidence"]["artifacts"][0]
    artifact["verdict"] = "blocking"
    artifact["findings"] = [
        {
            "id": "finding-current",
            "severity": "important",
            "actionable": True,
            "summary": "Current blocking finding.",
        }
    ]

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("blocking current-head finding" in reason for reason in result["reasons"])


def test_pr_gate_allows_successor_resolver_with_current_head_rereview() -> None:
    evidence = clean_evidence()
    original = evidence["review_evidence"]["artifacts"][0]
    successor = dict(original)
    successor.update(
        {
            "artifact_id": "pr718-head1-successor",
            "reviewer_lane": "reviewer-successor",
            "producer_identity": "reviewer-2",
        }
    )
    evidence["review_evidence"]["artifacts"].append(successor)
    evidence["review_evidence"]["current_artifact_ids"].append(
        "pr718-head1-successor"
    )
    evidence["review_evidence"]["lane_roster"].append(
        {
            "lane_id": "reviewer-successor",
            "producer_identity": "reviewer-2",
            "successor_of": "merge-reviewer-2",
        }
    )
    thread = evidence["review_threads"][0]
    thread.update(
        {
            "resolved_by": "reviewer-2",
            "resolver_role": "reviewer_lane",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed", result["reasons"]


def test_pr_gate_blocks_successor_with_mismatched_trusted_lineage() -> None:
    evidence = clean_evidence()
    original = evidence["review_evidence"]["artifacts"][0]
    successor = dict(original)
    successor.update(
        {
            "artifact_id": "pr718-head1-successor",
            "reviewer_lane": "reviewer-successor",
            "producer_identity": "reviewer-2",
        }
    )
    evidence["review_evidence"]["artifacts"].append(successor)
    evidence["review_evidence"]["current_artifact_ids"].append(
        "pr718-head1-successor"
    )
    evidence["review_evidence"]["lane_roster"].append(
        {
            "lane_id": "reviewer-successor",
            "producer_identity": "reviewer-2",
            "successor_of": "unrelated-reviewer",
        }
    )
    evidence["review_threads"][0].update(
        {
            "resolved_by": "reviewer-2",
            "resolver_role": "reviewer_lane",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("lacks original/successor re-review evidence" in reason for reason in result["reasons"])


def test_pr_gate_blocks_successor_when_original_reviewer_lane_is_ambiguous() -> None:
    evidence = clean_evidence()
    original = evidence["review_evidence"]["artifacts"][0]
    successor = dict(original)
    successor.update(
        {
            "artifact_id": "pr718-head1-successor",
            "reviewer_lane": "reviewer-successor",
            "producer_identity": "reviewer-2",
        }
    )
    evidence["review_evidence"]["artifacts"].append(successor)
    evidence["review_evidence"]["current_artifact_ids"].append(
        "pr718-head1-successor"
    )
    evidence["review_evidence"]["lane_roster"].extend(
        [
            {
                "lane_id": "duplicate-original",
                "producer_identity": "reviewer-1",
            },
            {
                "lane_id": "reviewer-successor",
                "producer_identity": "reviewer-2",
                "successor_of": "merge-reviewer-2",
            },
        ]
    )
    evidence["review_threads"][0].update(
        {
            "resolved_by": "reviewer-2",
            "resolver_role": "reviewer_lane",
            "original_author": "reviewer-1",
            "original_comment_id": "PRRC_fixture-root",
            "lane_id": "reviewer-successor",
            "successor_of": "merge-reviewer-2",
            "re_review_artifact_id": "pr718-head1-successor",
        }
    )

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("lacks original/successor re-review evidence" in reason for reason in result["reasons"])


def test_pr_gate_blocks_confirmed_merge_without_commit_sha() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_record"]["merge_commit_sha"] = None
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "merge_record.merge_commit_sha" in result["missing"]


def test_pr_gate_blocks_unknown_merge_path() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_record"]["merge_path"] = "force_push"
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("merge_path must be one of" in reason for reason in result["reasons"])


def test_pr_gate_blocks_naive_merge_dispatch_timestamp() -> None:
    evidence = fixture("pr-merge-confirmed.json")
    evidence["merge_dispatched_at"] = "2026-07-04T07:01:00"
    evidence["merge_head_sha"] = evidence["gate_query_head_sha"]
    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("timezone-aware" in reason for reason in result["reasons"])
