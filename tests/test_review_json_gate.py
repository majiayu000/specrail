from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from review_json_gate import (  # noqa: E402
    CONTRACT_VERSION,
    LEGACY_REVIEW_FIELDS,
    REVIEW_TOP_LEVEL_KEYS,
    evaluate_review_gate,
    parse_unified_diff,
    validate_exact_git_diff,
)


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def valid_review() -> dict[str, object]:
    diff = load_diff().encode()
    return {
        "artifact_id": "review-pr489-round1",
        "contract_version": CONTRACT_VERSION,
        "repository": "acme/widgets",
        "pr": 489,
        "profile": "standard",
        "base_head_sha": "b" * 40,
        "head_sha": "a" * 40,
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
        "review_source": "independent_lane",
        "round": 1,
        "mode": "full",
        "verdict": "clean",
        "body": "## Summary\nReviewed the complete change.\n\n## Verdict\nNo blocking findings.",
        "findings": [],
    }


def test_review_gate_allows_valid_compact_review() -> None:
    result = evaluate_review_gate(valid_review(), load_diff())

    assert result["decision"] == "allowed"
    assert result["advisory_only"] is True
    assert result["blocking_findings"] == []
    assert result["follow_ups"] == []
    assert result["reasons"] == []
    assert result["missing"] == []
    assert "compact review contract v3 valid" in result["satisfied"]


def test_review_gate_reports_all_missing_fields() -> None:
    result = evaluate_review_gate({}, load_diff())

    assert result["decision"] == "blocked"
    assert {
        "artifact_id",
        "body",
        "contract_version",
        "findings",
        "head_sha",
        "mode",
        "pr",
        "profile",
        "base_head_sha",
        "diff_sha256",
        "repository",
        "review_source",
        "round",
        "verdict",
    } <= set(result["missing"])
    assert len(result["rejection_items"]) >= len(result["missing"])


def test_review_gate_reports_legacy_and_unknown_fields_together() -> None:
    review = valid_review()
    for field in LEGACY_REVIEW_FIELDS:
        review[field] = "legacy"
    review["undeclared_field"] = True

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    legacy_reasons = {
        reason
        for reason in result["reasons"]
        if reason.startswith("unsupported legacy review field:")
    }
    assert legacy_reasons == {
        f"unsupported legacy review field: {field}"
        for field in LEGACY_REVIEW_FIELDS
    }
    assert "unknown top-level field: undeclared_field" in result["reasons"]


def test_review_gate_top_level_contract_is_compact() -> None:
    assert len(REVIEW_TOP_LEVEL_KEYS) == 15
    assert not (LEGACY_REVIEW_FIELDS & REVIEW_TOP_LEVEL_KEYS)


def test_review_gate_blocks_missing_headings_and_final_authority() -> None:
    review = valid_review()
    review["body"] = "I approve this PR. It is ready to merge."

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert {
        "body includes ## Summary",
        "body includes ## Verdict",
    } <= set(result["missing"])
    assert any("final approval or merge authority" in item for item in result["reasons"])


@pytest.mark.parametrize(
    "authority",
    ["批准合并", "允许合并", "可合并", "准许合并", "合并即可"],
)
def test_review_gate_blocks_localized_merge_authority(authority: str) -> None:
    review = valid_review()
    review["body"] = f"## Summary\n检查完成。\n\n## Verdict\n{authority}。"

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("final approval or merge authority" in item for item in result["reasons"])


def test_review_gate_blocks_invalid_finding_location() -> None:
    review = valid_review()
    review["verdict"] = "blocking"
    review["findings"] = [
        {
            "id": "P0-invalid-location",
            "severity": "P0",
            "status": "unresolved",
            "summary": "Unsafe rendering.",
            "path": "src/app.py",
            "line": 99,
        }
    ]

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert any("src/app.py:99 is not present in the diff" in item for item in result["reasons"])


def test_parse_unified_diff_indexes_both_sides() -> None:
    index = parse_unified_diff(load_diff())

    assert {1, 2, 10, 11, 12} <= index.left["src/app.py"]
    assert {1, 2, 3, 11, 12, 13, 14} <= index.right["src/app.py"]


def test_validate_exact_git_diff_rejects_option_like_revisions(tmp_path: Path) -> None:
    reasons = validate_exact_git_diff(
        tmp_path,
        "--output=/tmp/leak",
        "a" * 40,
        "b" * 64,
    )

    assert reasons == ["exact Git diff requires 40-character Git SHAs before execution"]


def test_round_two_digest_can_be_checked_without_git_repo() -> None:
    diff = load_diff()
    review = valid_review()
    prior_review = copy.deepcopy(review)
    prior_review["base_head_sha"] = "c" * 40
    prior_review["head_sha"] = "b" * 40
    prior_review["diff_sha256"] = hashlib.sha256(diff.encode()).hexdigest()
    review.update(
        {
            "round": 2,
            "mode": "diff_only",
            "base_head_sha": "b" * 40,
            "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
            "prior_review": prior_review,
        }
    )

    result = evaluate_review_gate(review, diff)

    assert result["decision"] == "allowed", result["reasons"]


def test_round_one_digest_must_match_supplied_diff() -> None:
    review = valid_review()
    review["diff_sha256"] = "0" * 64

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert "diff_sha256 does not match the supplied diff" in result["reasons"]


def test_round_two_requires_bound_round_one_full_review() -> None:
    diff = load_diff()
    review = valid_review()
    review.update(
        {
            "round": 2,
            "mode": "diff_only",
            "base_head_sha": "b" * 40,
            "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        }
    )

    result = evaluate_review_gate(review, diff)

    assert result["decision"] == "blocked"
    assert "prior_review" in result["missing"]


def test_review_gate_rejects_legacy_artifact_with_rebuild_guidance() -> None:
    result = evaluate_review_gate(
        {"verdict": "clean", "comments": [], "review_round": 1},
        load_diff(),
    )

    assert result["decision"] == "blocked"
    assert any("rebuild legacy review evidence" in item for item in result["reasons"])
    assert "unsupported legacy review field: comments" in result["reasons"]
    assert "unsupported legacy review field: review_round" in result["reasons"]


def test_review_gate_cli_json_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "app.py").write_text("before = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=SpecRail Test", "-c",
         "user.email=specrail@example.invalid", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    (repo / "app.py").write_text("after = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=SpecRail Test", "-c",
         "user.email=specrail@example.invalid", "commit", "-qm", "head"],
        cwd=repo,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary", f"{base}..{head}", "--"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    review = valid_review()
    review.update(
        {
            "base_head_sha": base,
            "head_sha": head,
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
        }
    )
    review_path = repo / "review.json"
    diff_path = repo / "review.patch"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    diff_path.write_bytes(diff)
    for name in ("workflow.yaml", "states.yaml", "labels.yaml"):
        (repo / name).write_bytes((ROOT / name).read_bytes())
    result = subprocess.run(
        [
            sys.executable,
                str(ROOT / "checks" / "review_json_gate.py"),
            "--repo",
            str(repo),
            "--review",
            str(review_path),
            "--diff",
            str(diff_path),
            "--json",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert {
        "decision",
        "verdict",
        "advisory_only",
        "reasons",
        "satisfied",
        "missing",
        "blocking_findings",
        "follow_ups",
        "outdated_hosted_findings",
        "blocked_actions",
        "verification_commands",
    } <= set(payload)


def test_review_gate_output_is_deterministic() -> None:
    review = copy.deepcopy(valid_review())
    review["unexpected"] = True
    review["review_round"] = 7

    first = evaluate_review_gate(review, load_diff())
    second = evaluate_review_gate(review, load_diff())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
