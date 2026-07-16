from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pr_gate_test_support import (
    ROOT,
    clean_evidence,
    evaluate_pr_gate,
    fixture,
    sensitive_evidence,
)


def test_pr_gate_revalidates_explicit_sensitive_approved_spec(tmp_path: Path) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "allowed"
    assert result["enforcement_sensitive"] is True
    assert "approved spec evidence revalidated" in result["satisfied"]


def test_pr_gate_blocks_missing_origin_head_even_with_adapter_default(
    tmp_path: Path,
) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--delete", "refs/remotes/origin/HEAD"],
        check=True,
    )

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert any("origin/HEAD is missing" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    ("field", "value"),
    [("default_base_ref", "forged"), ("default_base_sha", "0" * 40)],
)
def test_pr_gate_blocks_forged_adapter_default_identity(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    evidence[field] = value

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert any("default base" in reason for reason in result["reasons"])


def test_pr_gate_blocks_changed_file_snapshot_digest_mismatch(tmp_path: Path) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    evidence["changed_files_sha256"] = "0" * 64

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert any("changed_files_sha256" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    "forgery",
    ["hash", "head", "traversal", "body_hint", "not_ancestor", "base_mismatch"],
)
def test_pr_gate_blocks_forged_sensitive_approved_spec(forgery: str, tmp_path: Path) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    approval = evidence["approved_spec"]
    if forgery == "hash":
        path = approval["spec_paths"][0]
        approval["content_hashes"][path] = "0" * 64
    elif forgery == "head":
        approval["spec_revisions"][approval["spec_paths"][0]]["merge_commit_sha"] = "0" * 40
    elif forgery == "traversal":
        approval["spec_paths"][0] = "../product.md"
    else:
        if forgery == "not_ancestor":
            feature_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            approval["spec_revisions"][approval["spec_paths"][0]]["merge_commit_sha"] = feature_head
        elif forgery == "base_mismatch":
            evidence["base_sha"] = "0" * 40
        else:
            approval["state_source"] = "body_hint"
            approval["state_trusted"] = False

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert "sensitive_enforcement" in result["missing"]


@pytest.mark.parametrize("stale_kind", ["stale_evidence", "base_checkout"])
def test_pr_gate_blocks_checkout_that_does_not_match_gated_head(
    stale_kind: str,
    tmp_path: Path,
) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    if stale_kind == "stale_evidence":
        evidence["gate_query_head_sha"] = "f" * 40
    else:
        base_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "origin/main"], check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        evidence["head_sha"] = base_head
        evidence["gate_query_head_sha"] = base_head

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert any("local checkout HEAD" in reason for reason in result["reasons"])


def test_pr_gate_blocks_pr_that_changes_an_approved_spec(tmp_path: Path) -> None:
    evidence, repo, config = sensitive_evidence(tmp_path)
    (repo / "specs" / "GH97" / "tech.md").write_text("# changed in PR\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid", "commit", "-qm", "change spec",
        ],
        check=True,
    )
    changed_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    evidence["head_sha"] = changed_head
    evidence["gate_query_head_sha"] = changed_head

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert any("changed since approval" in reason for reason in result["reasons"])


def test_pr_gate_allows_clean_authorized_merge() -> None:
    result = evaluate_pr_gate(clean_evidence())

    assert result["decision"] == "allowed"
    assert result["missing"] == []
    assert result["reasons"] == []


def test_pr_gate_allows_legacy_linked_issue_without_structured_reference() -> None:
    evidence = clean_evidence()

    result = evaluate_pr_gate(evidence)

    assert "issue_reference" not in evidence
    assert result["decision"] == "allowed"


@pytest.mark.parametrize("invalid_relation", [None, [], "partial"])
def test_pr_gate_blocks_present_non_object_issue_reference(
    invalid_relation: object,
) -> None:
    evidence = clean_evidence()
    evidence["issue_reference"] = invalid_relation

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "issue_reference must be an object" in result["reasons"]


def test_pr_gate_allows_verified_partial_reference_without_treating_it_as_closing() -> None:
    evidence = clean_evidence()
    evidence["linked_issue"] = 671
    evidence["issue_reference"] = {
        "number": 671,
        "kind": "partial",
        "source": "pr_body",
        "verified": True,
        "state": "OPEN",
        "url": "https://github.com/majiayu000/remem/issues/671",
        "closing_issue_numbers": [806],
    }

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed"
    assert "issue_reference: verified partial GH-671" in result["satisfied"]
    assert result["issue_reference"]["closing_issue_numbers"] == [806]
    assert "issue_closure" not in result
    assert "completion_mode" not in result
    assert "close_issue" not in result["blocked_actions"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"number": 670}, "must match linked_issue"),
        ({"verified": False}, "verified must be true"),
        ({"source": "closingIssuesReferences"}, "partial source must be pr_body"),
        ({"state": "CLOSED"}, "partial state must be OPEN"),
        ({"closing_issue_numbers": [671, 806]}, "partial target must not be closing"),
        ({"closing_issue_numbers": "806"}, "list of positive integers"),
        ({"closing_issue_numbers": [806, 806]}, "must not contain duplicates"),
        ({"number": True}, "issue_reference.number"),
        ({"closure_authorized": True}, "unsupported fields"),
        ({"kind": "unknown"}, "kind must be one of"),
    ],
)
def test_pr_gate_blocks_inconsistent_partial_reference(
    change: dict[str, object],
    reason: str,
) -> None:
    evidence = clean_evidence()
    evidence["linked_issue"] = 671
    relation = {
        "number": 671,
        "kind": "partial",
        "source": "pr_body",
        "verified": True,
        "state": "OPEN",
        "closing_issue_numbers": [806],
    }
    relation.update(change)
    evidence["issue_reference"] = relation

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any(reason in item for item in result["reasons"] + result["missing"])


def test_pr_gate_allows_verified_closing_reference() -> None:
    evidence = clean_evidence()
    evidence["issue_reference"] = {
        "number": evidence["linked_issue"],
        "kind": "closing",
        "source": "closingIssuesReferences",
        "verified": True,
        "closing_issue_numbers": [evidence["linked_issue"]],
    }

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed"
    assert any("verified closing" in item for item in result["satisfied"])


def test_pr_gate_blocks_closing_reference_without_target_in_closing_numbers() -> None:
    evidence = clean_evidence()
    evidence["issue_reference"] = {
        "number": evidence["linked_issue"],
        "kind": "closing",
        "source": "closingIssuesReferences",
        "verified": True,
        "closing_issue_numbers": [806],
    }

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("closing target must appear" in item for item in result["reasons"])


def test_pr_gate_blocks_closing_reference_with_partial_source() -> None:
    evidence = clean_evidence()
    evidence["issue_reference"] = {
        "number": evidence["linked_issue"],
        "kind": "closing",
        "source": "pr_body",
        "verified": True,
        "closing_issue_numbers": [evidence["linked_issue"]],
    }

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("closing source" in item for item in result["reasons"])




def test_pr_gate_blocks_missing_lane_failures_evidence() -> None:
    evidence = clean_evidence()
    evidence.pop("lane_failures")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "lane_failures" in result["missing"]


def test_pr_gate_allows_human_resolved_thread() -> None:
    evidence = clean_evidence()
    thread = evidence["review_threads"][0]
    thread["resolved_by"] = "maintainer"
    thread["resolver_role"] = "human"
    thread["authorized_human_maintainer"] = True

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed"
    assert any("resolved by human" in item for item in result["satisfied"])


def test_pr_gate_needs_human_without_authorization() -> None:
    evidence = fixture("pr-missing-human-auth.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "needs_human"
    assert "human_authorization" in result["missing"]
    assert result["blocked_actions"] == ["merge"]


def test_pr_gate_blocks_pending_ci() -> None:
    evidence = fixture("pr-pending-ci.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("workflow-check is not completed" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unresolved_thread() -> None:
    evidence = fixture("pr-unresolved-thread.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("unresolved review threads" in reason for reason in result["reasons"])


def test_pr_gate_blocks_outdated_unresolved_thread() -> None:
    evidence = fixture("pr-outdated-unresolved-thread.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("outdated-unresolved-thread" in reason for reason in result["reasons"])


def test_pr_gate_blocks_implementer_resolved_thread() -> None:
    evidence = fixture("pr-implementer-resolved-thread.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("forbidden implementer" in reason for reason in result["reasons"])


def test_pr_gate_blocks_unknown_resolved_thread() -> None:
    evidence = clean_evidence()
    thread = evidence["review_threads"][0]
    thread["resolved_by"] = "unknown-actor"
    thread["resolver_role"] = "unknown"

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("forbidden unknown" in reason for reason in result["reasons"])


def test_pr_gate_allows_independent_retry_after_lane_failure() -> None:
    evidence = clean_evidence()
    evidence["lane_failures"] = [
        {
            "lane_id": "merge-reviewer-1",
            "failure_kind": "usage_limit",
            "observed_marker": "You've hit your usage limit",
        }
    ]

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed"
    assert any("lane failures recorded: 1" in item for item in result["satisfied"])


def test_pr_gate_blocks_self_review_without_specific_authorization() -> None:
    evidence = fixture("pr-self-review-unauthorized.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "self_review_authorization" in result["missing"]


def test_pr_gate_allows_explicitly_authorized_self_review() -> None:
    evidence = fixture("pr-self-review-unauthorized.json")
    evidence["self_review_authorization"] = {
        "actor": "maintainer",
        "source": "chat after reviewer lane failure",
        "scope": "PR #718 exact head e36d97517d8d0b27faca1abe5e5c63f9f88684d9 after merge-reviewer-1 usage_limit",
    }

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "allowed"
    assert any("self-review authorization" in item for item in result["satisfied"])


def test_pr_gate_blocks_authorized_self_review_without_lane_failure() -> None:
    evidence = fixture("pr-self-review-unauthorized.json")
    evidence["lane_failures"] = []
    evidence["self_review_authorization"] = {
        "actor": "maintainer",
        "source": "chat after reviewer lane failure",
        "scope": "PR #718 exact head e36d97517d8d0b27faca1abe5e5c63f9f88684d9 after merge-reviewer-1 usage_limit",
    }

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert any("self_review requires recorded lane_failures" in reason for reason in result["reasons"])


def test_pr_gate_blocks_missing_thread_resolver_attribution() -> None:
    evidence = fixture("pr-missing-thread-resolver.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "review_threads[1].resolved_by" in result["missing"]
    assert "review_threads[1].resolver_role" in result["missing"]


def test_pr_gate_blocks_missing_gate_query_ordering_fields() -> None:
    evidence = clean_evidence()
    evidence.pop("gate_query_completed_at")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate_query_completed_at" in result["missing"]


def test_pr_gate_blocks_gate_query_after_merge() -> None:
    evidence = fixture("pr-query-after-merge.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate query must complete before merge dispatch" in result["reasons"]


def test_pr_gate_blocks_gate_query_head_mismatch() -> None:
    evidence = fixture("pr-gate-head-mismatch.json")

    result = evaluate_pr_gate(evidence)

    assert result["decision"] == "blocked"
    assert "gate_query_head_sha must match head_sha" in result["reasons"]


def test_pr_gate_cli_json_contract(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(clean_evidence()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "checks/pr_gate.py",
            "--repo",
            ".",
            "--evidence",
            str(evidence_path),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert {
        "decision",
        "pr",
        "linked_issue",
        "head_sha",
        "gate_query_completed_at",
        "gate_query_head_sha",
        "reasons",
        "satisfied",
        "missing",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)
