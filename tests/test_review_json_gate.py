from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from shutil import copyfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from evidence_content_binding import build_content_binding_evidence  # noqa: E402
from review_json_gate import (  # noqa: E402
    REVIEW_TOP_LEVEL_KEYS,
    evaluate_review_gate,
    validate_exact_git_diff,
)
from pr_review_contract import evaluate_review_contract  # noqa: E402
from review_result_semantics import (  # noqa: E402
    UNGATED_DISCLOSURE_MARKER,
    validate_review_artifact,
)


def load_review(name: str) -> dict[str, object]:
    review = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    review.setdefault("artifact_id", f"fixture-{name.removesuffix('.json')}")
    review.setdefault("pr", 489)
    review.setdefault("reviewer_lane", "reviewer-1")
    review.setdefault("producer_identity", "agent-reviewer-1")
    review.setdefault("review_source", "independent_lane")
    review.setdefault("review_execution", "local")
    review.setdefault("head_sha", "aaaa000000000000000000000000000000000001")
    review.setdefault("review_started_at", "2026-07-16T00:00:00Z")
    review.setdefault("review_completed_at", "2026-07-16T00:01:00Z")
    review.setdefault("status", "completed")
    review["verdict"] = "blocking"
    review.setdefault("human_final_review_required", False)
    review.setdefault(
        "findings",
        [
            {
                "id": "fixture-finding",
                "severity": "important",
                "actionable": True,
                "summary": "Fixture review finding.",
            }
        ],
    )
    if name != "review-resumed-no-checklist.json":
        review.setdefault("prior_findings", [])
    for index, finding in enumerate(review.get("prior_findings", []), start=1):
        finding.setdefault("id", f"prior-{index}")
        finding.setdefault("source_head_sha", "aaaa000000000000000000000000000000000000")
        if finding.get("status") in {"resolved", "obsolete"}:
            finding.setdefault("closure_evidence", f"review round {index} evidence")
    return review


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def test_review_json_gate_allows_valid_review() -> None:
    result = evaluate_review_gate(load_review("review-valid.json"), load_diff())

    assert result["decision"] == "allowed"
    assert result["verdict"] == "blocking"
    assert result["comment_count"] == 2
    assert result["advisory_only"] is True
    assert result["reasons"] == []
    assert result["missing"] == []
    assert "body includes ## Summary" in result["satisfied"]
    assert "body includes ## Verdict" in result["satisfied"]


def test_review_json_gate_allows_v1_content_binding_fields(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    copyfile(
        ROOT / "schemas" / "content_binding_evidence.schema.json",
        schema_dir / "content_binding_evidence.schema.json",
    )
    review = load_review("review-valid.json")
    binding = {
        "content_binding_version": 1,
        "snapshot": {
            "head_sha": review["head_sha"],
            "base_tree_oid": "b" * 40,
            "algorithm": "sha256",
            "normalization": "specrail-v1",
            "collector": "github_pr_evidence",
        },
        "content_hashes": {
            "code_inputs": "1" * 64,
            "spec_files": "2" * 64,
            "pr_metadata": "3" * 64,
        },
    }
    sidecar = build_content_binding_evidence(review["pr"], binding)
    sidecar_path = tmp_path / "artifacts" / "binding.json"
    sidecar_path.parent.mkdir()
    raw = json.dumps(sidecar, sort_keys=True).encode("utf-8")
    sidecar_path.write_bytes(raw)
    review.update({
        "content_binding_version": 1,
        "covered_categories": ["code_inputs", "spec_files"],
        "content_bindings": {
            key: binding["content_hashes"][key]
            for key in ["code_inputs", "spec_files"]
        },
        "content_binding_evidence": {
            "artifact_id": sidecar["artifact_id"],
            "path": "artifacts/binding.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    })

    result = evaluate_review_gate(review, load_diff(), repo=tmp_path)

    assert result["decision"] == "allowed", result["reasons"]
    assert not any("unknown top-level field" in item for item in result["reasons"])


def test_review_json_gate_top_level_keys_match_schema() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "review_result.schema.json").read_text(encoding="utf-8")
    )

    assert REVIEW_TOP_LEVEL_KEYS == set(schema["properties"])


def test_review_json_gate_blocks_unknown_top_level_field() -> None:
    review = load_review("review-valid.json")
    review["undeclared_field"] = True

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "unknown top-level field: undeclared_field" in result["reasons"]


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("tier_attestation", {}),
        ("tier_dispute", "false"),
        ("finding_classifications", [{}]),
    ],
)
def test_review_json_gate_blocks_schema_invalid_tier_evidence(
    field: str, malformed: object
) -> None:
    review = load_review("review-valid.json")
    review[field] = malformed

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any(field in reason for reason in result["reasons"])


def test_review_semantics_blocks_missing_execution_provenance() -> None:
    review = load_review("review-valid.json")
    del review["review_execution"]

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert any("review_execution" in error for error in result["errors"])


def test_review_semantics_blocks_hosted_review_as_primary() -> None:
    review = load_review("review-valid.json")
    review["review_execution"] = "hosted"

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert any("supplemental only" in error for error in result["errors"])


def test_review_json_gate_blocks_clean_verdict_with_findings() -> None:
    review = load_review("review-valid.json")
    review["verdict"] = "clean"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "clean verdict requires zero findings" in result["reasons"]


def test_review_json_gate_blocks_invalid_line() -> None:
    result = evaluate_review_gate(load_review("review-invalid-line.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("src/app.py:99 is not present in the diff" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_severity() -> None:
    result = evaluate_review_gate(load_review("review-invalid-severity.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("severity must be critical" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_range() -> None:
    result = evaluate_review_gate(load_review("review-invalid-range.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("includes lines not present in the diff" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_unpaired_start_range_fields() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment.pop("start_side")

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("start_line and start_side must appear together" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_cross_side_range() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment["start_side"] = "LEFT"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "comment #1 start_side must match side for a range" in result["reasons"]


def test_review_json_gate_blocks_left_side_suggestion() -> None:
    result = evaluate_review_gate(load_review("review-invalid-suggestion-side.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("suggestions are only allowed on RIGHT-side comments" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_empty_suggestion_field() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment["suggestion"] = " "

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("suggestion must be a non-empty string" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_empty_fenced_suggestion() -> None:
    result = evaluate_review_gate(load_review("review-invalid-empty-suggestion.json"), load_diff())

    assert result["decision"] == "blocked"
    assert any("suggestion block #1 must be non-empty" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_unclosed_fenced_suggestion() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    comments = review["comments"]
    assert isinstance(comments, list)
    first_comment = comments[0]
    assert isinstance(first_comment, dict)
    first_comment["body"] = "Use a complete suggestion block.\n\n```suggestion\n    return title.strip()"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "comment #1 has unterminated suggestion block" in result["reasons"]


def test_review_json_gate_blocks_missing_body_headings() -> None:
    result = evaluate_review_gate(load_review("review-invalid-body.json"), load_diff())

    assert result["decision"] == "blocked"
    assert "body must include ## Summary heading" in result["reasons"]
    assert "body must include ## Verdict heading" in result["reasons"]


def test_review_contract_blocks_tampered_top_level_completion_time() -> None:
    evidence = json.loads(
        (FIXTURES / "pr-clean-authorized.json").read_text(encoding="utf-8")
    )
    evidence["review_completed_at"] = "2026-07-03T23:57:00Z"
    evidence["gate_started_at"] = "2026-07-03T23:57:30Z"
    evidence["gate_query_completed_at"] = "2026-07-03T23:59:00Z"

    _, _, reasons = evaluate_review_contract(evidence, ROOT)

    assert (
        "review_completed_at must match trusted review_evidence.review_completed_at"
        in reasons
    )


def test_review_json_gate_blocks_spec_drift() -> None:
    result = evaluate_review_gate(load_review("review-spec-drift.json"), load_diff())

    assert result["decision"] == "blocked"
    assert "spec_alignment reports drift" in result["reasons"]


def test_review_json_gate_blocks_final_authority_language() -> None:
    review = copy.deepcopy(load_review("review-valid.json"))
    review["body"] = (
        "## Summary\nI approve this PR. It is approved for merge. You can merge; ship it. "
        "Go ahead and merge. Looks good to merge. Safe to merge. LGTM, merge.\n\n"
        "## Verdict\nThis advisory artifact still cannot grant merge authority."
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("final approval or merge authority" in reason for reason in result["reasons"])


def test_review_json_gate_cli_json_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "checks/review_json_gate.py",
            "--repo",
            ".",
            "--review",
            "examples/fixtures/review-valid.json",
            "--diff",
            "examples/fixtures/pr-diff.patch",
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
        "verdict",
        "comment_count",
        "advisory_only",
        "reasons",
        "satisfied",
        "missing",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)


def test_review_json_gate_allows_round_two_full_review() -> None:
    result = evaluate_review_gate(load_review("review-round2-full.json"), load_diff())

    assert result["decision"] == "allowed", result["reasons"]


def test_review_json_gate_blocks_round_three_full_without_request() -> None:
    result = evaluate_review_gate(
        load_review("review-round3-full-no-request.json"), load_diff()
    )

    assert result["decision"] == "blocked"
    assert any("exceeds the cap" in reason for reason in result["reasons"])


def test_review_json_gate_allows_round_three_full_with_human_request() -> None:
    result = evaluate_review_gate(
        load_review("review-round3-full-with-request.json"), load_diff()
    )

    assert result["decision"] == "allowed", result["reasons"]


def test_review_json_gate_allows_round_three_diff_only_with_checklist() -> None:
    result = evaluate_review_gate(
        load_review("review-round3-diff-only-checklist.json"), load_diff()
    )

    assert result["decision"] == "allowed", result["reasons"]


def test_review_json_gate_blocks_resumed_round_without_checklist() -> None:
    result = evaluate_review_gate(
        load_review("review-resumed-no-checklist.json"), load_diff()
    )

    assert result["decision"] == "blocked"
    assert any("prior_findings" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_diff_only_without_base_head_sha() -> None:
    review = load_review("review-round3-diff-only-checklist.json")
    del review["base_head_sha"]
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("base_head_sha" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_round_without_mode() -> None:
    review = load_review("review-round2-full.json")
    del review["review_mode"]
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("provided together" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_first_round_diff_only() -> None:
    review = load_review("review-round3-diff-only-checklist.json")
    review["review_round"] = 1
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("review_round >= 2" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_invalid_prior_finding_status() -> None:
    review = load_review("review-round3-diff-only-checklist.json")
    review["prior_findings"][0]["status"] = "handled"
    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("status must be one of" in reason for reason in result["reasons"])


def test_review_json_gate_blocks_legacy_review_without_v2_terminal_fields() -> None:
    review = load_review("review-valid.json")
    for field in [
        "artifact_id",
        "reviewer_lane",
        "producer_identity",
        "review_source",
        "review_started_at",
        "review_completed_at",
        "status",
        "human_final_review_required",
        "findings",
        "prior_findings",
    ]:
        review.pop(field)

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("artifact_id" in reason for reason in result["reasons"])


@pytest.mark.parametrize("status", ["pending", "failed", "cancelled", "superseded"])
def test_review_semantics_terminal_lifecycle_blocks_merge_readiness(status: str) -> None:
    review = load_review("review-valid.json")
    review["status"] = status
    if status == "pending":
        review["review_completed_at"] = None

    result = validate_review_artifact(review)

    assert result["valid"] is True
    assert any("status is not completed" in item for item in result["blocking_reasons"])


def test_review_semantics_blocks_duplicate_finding_ids() -> None:
    review = load_review("review-valid.json")
    review["findings"].append(dict(review["findings"][0]))

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert "findings IDs must be unique" in result["errors"]


def test_review_semantics_requires_prior_finding_closure_evidence() -> None:
    review = load_review("review-valid.json")
    review["prior_findings"] = [
        {
            "id": "finding-old",
            "source_head_sha": "b" * 40,
            "summary": "Old blocking finding.",
            "status": "resolved",
        }
    ]

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert any("closure_evidence" in item for item in result["errors"])


def test_review_semantics_blocks_unresolved_prior_finding() -> None:
    review = load_review("review-valid.json")
    review["prior_findings"] = [
        {
            "id": "finding-old",
            "source_head_sha": "b" * 40,
            "summary": "Old blocking finding.",
            "status": "unresolved",
        }
    ]

    result = validate_review_artifact(review)

    assert result["valid"] is True
    assert any("unresolved prior finding" in item for item in result["blocking_reasons"])


def test_review_semantics_requires_self_review_human_final_gate() -> None:
    review = load_review("review-valid.json")
    review["review_source"] = "self_review"
    review["human_final_review_required"] = False

    result = validate_review_artifact(review)

    assert result["valid"] is False
    assert "self_review requires human_final_review_required=true" in result["errors"]


def test_review_json_gate_rejection_items_cover_missing_and_reasons() -> None:
    result = evaluate_review_gate({}, load_diff())

    assert result["decision"] == "blocked"
    items = result["rejection_items"]
    assert items
    item_ids = {item["item_id"] for item in items}
    for field in ["verdict", "body", "comments"]:
        assert f"missing_evidence_field:{field}" in item_ids
    assert len(items) >= len(result["missing"]) + len(result["reasons"])


def test_review_json_gate_allowed_result_has_empty_rejection_items() -> None:
    result = evaluate_review_gate(load_review("review-valid.json"), load_diff())

    assert result["decision"] == "allowed"
    assert result["rejection_items"] == []
    assert "repeat_rejection" not in result


def test_review_json_gate_allows_gate_status_unavailable() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = review["body"].replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "allowed"
    assert "gate_status: unavailable" in result["satisfied"]
    assert "gate_authorization present" in result["satisfied"]
    assert "body discloses unavailable SpecRail gate" in result["satisfied"]


def test_review_json_gate_blocks_unavailable_without_authorization() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["body"] = review["body"].replace(
        "## Summary", "## Summary\n\nSpecRail gate status: unavailable"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires a non-empty gate_authorization" in item for item in result["reasons"])


def test_review_json_gate_blocks_unavailable_without_summary_disclosure() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires the ## Summary marker" in item for item in result["reasons"])


def test_review_json_gate_blocks_unavailable_marker_outside_summary() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = f"{review['body']}\n\n{UNGATED_DISCLOSURE_MARKER}"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires the ## Summary marker" in item for item in result["reasons"])


def test_review_json_gate_requires_exact_case_unavailable_marker() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = review["body"].replace(
        "## Summary", "## Summary\n\nspecrail gate status: unavailable"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires the ## Summary marker" in item for item in result["reasons"])


@pytest.mark.parametrize(
    "claim",
    [
        "This review is SpecRail-gated.",
        "This review is verified.",
        "This review is fully verified and suitable for delivery.",
        "This result is merge-ready.",
    ],
)
def test_review_json_gate_blocks_degraded_positive_gate_claims(claim: str) -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = review["body"].replace(
        "## Summary",
        f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}\n\n{claim}",
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("must not claim" in item for item in result["reasons"])


@pytest.mark.parametrize("location", ["verdict", "comment"])
def test_review_json_gate_blocks_degraded_claims_in_all_published_text(
    location: str,
) -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "unavailable"
    review["gate_authorization"] = "Human authorization: continue without gate"
    review["body"] = review["body"].replace(
        "## Summary", f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}"
    )
    if location == "verdict":
        review["body"] = review["body"].replace(
            "## Verdict", "## Verdict\n\nThis review is verified and merge-ready."
        )
    else:
        comments = review["comments"]
        assert isinstance(comments, list)
        assert isinstance(comments[0], dict)
        comments[0]["body"] = "This review is verified and merge-ready."

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("must not claim" in item for item in result["reasons"])


@pytest.mark.parametrize("gate_status", [None, "gated"])
def test_review_json_gate_blocks_unavailable_marker_without_matching_status(
    gate_status: str | None,
) -> None:
    review = load_review("review-valid.json")
    if gate_status is not None:
        review["gate_status"] = gate_status
    review["body"] = review["body"].replace(
        "## Summary", f"## Summary\n\n{UNGATED_DISCLOSURE_MARKER}"
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("requires gate_status unavailable" in item for item in result["reasons"])


def test_review_json_gate_blocks_unknown_gate_status() -> None:
    review = load_review("review-valid.json")
    review["gate_status"] = "skipped"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "gate_status must be one of: gated, unavailable" in result["reasons"]


def test_review_json_gate_blocks_authorization_without_unavailable_status() -> None:
    review = load_review("review-valid.json")
    review["gate_authorization"] = "stale authorization"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("allowed only when gate_status is unavailable" in item for item in result["reasons"])


def git(repo: Path, *args: str) -> bytes:
    process = subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    return process.stdout


def commit_file(repo: Path, name: str, content: bytes, message: str) -> str:
    (repo / name).write_bytes(content)
    git(repo, "add", "--", name)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").decode().strip()


def bounded_review(base: str, head: str, diff: bytes, mode: str = "resumed") -> dict[str, object]:
    review = load_review("review-valid.json")
    review.update({
        "round_policy_version": 1,
        "review_round": 2,
        "review_mode": mode,
        "base_head_sha": base,
        "head_sha": head,
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
        "prior_findings": [],
        "comments": [],
    })
    return review


def git_history(tmp_path: Path) -> tuple[str, str, str, bytes, bytes]:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "SpecRail Test")
    git(tmp_path, "config", "user.email", "specrail@example.invalid")
    first = commit_file(tmp_path, "tracked.txt", b"one\n", "first")
    second = commit_file(tmp_path, "tracked.txt", b"two\n", "second")
    third = commit_file(tmp_path, "tracked.txt", b"three\n", "third")
    scoped = git(tmp_path, "diff", "--no-ext-diff", "--binary", f"{second}..{third}", "--")
    full = git(tmp_path, "diff", "--no-ext-diff", "--binary", f"{first}..{third}", "--")
    return first, second, third, scoped, full


@pytest.mark.parametrize("mode", ["resumed", "diff_only"])
def test_bounded_gate_accepts_exact_git_range(tmp_path: Path, mode: str) -> None:
    _, base, head, diff, _ = git_history(tmp_path)
    result = evaluate_review_gate(
        bounded_review(base, head, diff, mode), diff.decode(), repo=tmp_path, diff_bytes=diff
    )
    assert result["decision"] == "allowed", result["reasons"]


def test_bounded_gate_rejects_full_pr_diff_and_forged_hash(tmp_path: Path) -> None:
    _, base, head, scoped, full = git_history(tmp_path)
    review = bounded_review(base, head, scoped)
    full_result = evaluate_review_gate(
        review, full.decode(), repo=tmp_path, diff_bytes=full
    )
    assert any("provided diff bytes" in reason for reason in full_result["reasons"])
    review["diff_sha256"] = "0" * 64
    hash_result = evaluate_review_gate(
        review, scoped.decode(), repo=tmp_path, diff_bytes=scoped
    )
    assert any("diff_sha256" in reason for reason in hash_result["reasons"])


def test_bounded_gate_rejects_missing_git_object(tmp_path: Path) -> None:
    _, base, head, diff, _ = git_history(tmp_path)
    review = bounded_review(base, head, diff)
    review["base_head_sha"] = "f" * 40
    result = evaluate_review_gate(
        review, diff.decode(), repo=tmp_path, diff_bytes=diff
    )
    assert any("exact Git diff failed" in reason for reason in result["reasons"])


def test_bounded_gate_rejects_git_option_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = bounded_review("a" * 40, "b" * 40, b"")
    review["base_head_sha"] = "--output=/tmp/specrail-gh167-proof"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Git executed"))

    result = evaluate_review_gate(review, "", repo=tmp_path, diff_bytes=b"")

    assert any("40-character Git SHAs" in reason for reason in result["reasons"])


def test_bounded_gate_blocks_string_round_without_crashing(tmp_path: Path) -> None:
    review = bounded_review("a" * 40, "b" * 40, b"")
    review["review_round"] = "2"

    result = evaluate_review_gate(review, "", repo=tmp_path, diff_bytes=b"")

    assert result["decision"] == "blocked"
    assert any("positive integer" in reason for reason in result["reasons"])


def test_exact_diff_rejects_bad_hash_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Git executed"))
    reasons = validate_exact_git_diff(tmp_path, "a" * 40, "b" * 40, "bad")
    assert reasons == ["exact Git diff requires a 64-character diff_sha256 before execution"]


def test_exact_diff_reports_subprocess_start_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("git unavailable")

    monkeypatch.setattr(subprocess, "run", fail)
    reasons = validate_exact_git_diff(tmp_path, "a" * 40, "b" * 40, "c" * 64)
    assert reasons == ["cannot execute exact Git diff: git unavailable"]


def test_bounded_gate_accepts_binary_and_empty_exact_diffs(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "SpecRail Test")
    git(tmp_path, "config", "user.email", "specrail@example.invalid")
    base = commit_file(tmp_path, "blob.bin", b"\x00old\xff", "base")
    binary_head = commit_file(tmp_path, "blob.bin", b"\x00new\xfe", "binary")
    binary = git(tmp_path, "diff", "--no-ext-diff", "--binary", f"{base}..{binary_head}", "--")
    binary_result = evaluate_review_gate(
        bounded_review(base, binary_head, binary),
        binary.decode(), repo=tmp_path, diff_bytes=binary,
    )
    assert binary_result["decision"] == "allowed", binary_result["reasons"]
    git(tmp_path, "commit", "--allow-empty", "-m", "empty")
    empty_head = git(tmp_path, "rev-parse", "HEAD").decode().strip()
    empty = git(tmp_path, "diff", "--no-ext-diff", "--binary", f"{binary_head}..{empty_head}", "--")
    empty_result = evaluate_review_gate(
        bounded_review(binary_head, empty_head, empty, "diff_only"),
        "", repo=tmp_path, diff_bytes=empty,
    )
    assert empty_result["decision"] == "allowed", empty_result["reasons"]
