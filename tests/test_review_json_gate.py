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
    evaluate_review_gate as _evaluate_review_gate,
    parse_unified_diff,
    validate_exact_git_diff,
)


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def review_attestation_for(review: dict[str, object]) -> dict[str, str] | None:
    if (
        review.get("profile") == "fastlane"
        or not isinstance(review.get("artifact_id"), str)
        or not isinstance(review.get("head_sha"), str)
    ):
        return None
    attestation = {
        "artifact_id": str(review["artifact_id"]),
        "lane_id": "review-lane-1",
        "reviewer_actor": "reviewer-agent-1",
        "head_sha": str(review["head_sha"]),
        "invocation_id": "gate-1",
    }
    prior = review.get("prior_review")
    if review.get("round") == 2 and isinstance(prior, dict):
        attestation["prior_artifact_id"] = str(prior["artifact_id"])
        attestation["prior_head_sha"] = str(prior["head_sha"])
    return attestation


_AUTO_ATTESTATION = object()


def evaluate_review_gate(
    review: dict[str, object],
    diff: str,
    *,
    attestation: object = _AUTO_ATTESTATION,
    gate_invocation_id: str | None = "gate-1",
    **kwargs: object,
) -> dict[str, object]:
    resolved = (
        review_attestation_for(review)
        if attestation is _AUTO_ATTESTATION
        else attestation
    )
    return _evaluate_review_gate(
        review,
        diff,
        attestation=resolved,
        gate_invocation_id=gate_invocation_id,
        **kwargs,
    )


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


def test_parse_unified_diff_tracks_binary_paths_without_hunks() -> None:
    index = parse_unified_diff(
        "diff --git a/assets/old.bin b/assets/new.bin\n"
        "similarity index 100%\n"
        "rename from assets/old.bin\n"
        "rename to assets/new.bin\n"
    )

    assert index.paths == {"assets/old.bin", "assets/new.bin"}


def test_parse_unified_diff_handles_git_paths_with_spaces_and_quotes() -> None:
    index = parse_unified_diff(
        "diff --git a/file with space.txt b/file with space.txt\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "diff --git a/owner's.bin b/owner's.bin\n"
        "Binary files a/owner's.bin and b/owner's.bin differ\n"
        "diff --git a/old name.txt b/new name.txt\n"
        "similarity index 100%\n"
        "rename from old name.txt\n"
        "rename to new name.txt\n"
    )

    assert index.paths == {
        "file with space.txt",
        "owner's.bin",
        "old name.txt",
        "new name.txt",
    }


@pytest.mark.parametrize(
    ("encoded", "canonical"),
    [
        (r"caf\303\251.py", "café.py"),
        ("中文é.py", "中文é.py"),
        (r'quote\"file.py', 'quote"file.py'),
        (r"backslash\\file.py", r"backslash\file.py"),
        (r"control\tfile.py", "control\tfile.py"),
    ],
)
def test_quoted_paths_are_canonical_across_header_markers_and_findings(
    encoded: str,
    canonical: str,
) -> None:
    diff = (
        f'diff --git "a/{encoded}" "b/{encoded}"\n'
        f'--- "a/{encoded}"\n'
        f'+++ "b/{encoded}"\n'
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    index = parse_unified_diff(diff)

    assert index.paths == {canonical}
    assert index.left[canonical] == {1}
    assert index.right[canonical] == {1}

    review = valid_review()
    review["diff_sha256"] = hashlib.sha256(diff.encode()).hexdigest()
    review["verdict"] = "blocking"
    review["findings"] = [
        {
            "id": "P1-quoted-path",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Quoted path location remains canonical.",
            "path": canonical,
            "line": 1,
        }
    ]
    result = evaluate_review_gate(review, diff)

    assert "P1-quoted-path" in result["blocking_findings"]
    assert not any("is not present in the diff" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    "diff",
    [
        'diff --git "a/bad\\q.py" "b/bad\\q.py"\n',
        'diff --git "a/bad.py" "b/bad.py"\n--- "a/bad\\q.py"\n',
        'diff --git "a/unterminated.py "b/unterminated.py"\n',
    ],
)
def test_malformed_git_quoted_paths_fail_closed(diff: str) -> None:
    with pytest.raises(ValueError):
        parse_unified_diff(diff)


def test_rename_and_copy_metadata_preserve_top_level_a_directory() -> None:
    index = parse_unified_diff(
        "diff --git a/a/old.txt b/a/new.txt\n"
        "similarity index 100%\n"
        "rename from a/old.txt\n"
        "rename to a/new.txt\n"
        "diff --git a/a/source.txt b/a/copied.txt\n"
        "similarity index 100%\n"
        "copy from a/source.txt\n"
        "copy to a/copied.txt\n"
    )

    assert index.paths == {
        "a/old.txt",
        "a/new.txt",
        "a/source.txt",
        "a/copied.txt",
    }


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
    prior_review["verdict"] = "blocking"
    prior_review["findings"] = [
        {
            "id": "P1-prior-fix",
            "severity": "P1",
            "status": "unresolved",
            "summary": "Prior blocking defect.",
            "fix_paths": ["src/app.py"],
        }
    ]
    review.update(
        {
            "round": 2,
            "mode": "diff_only",
            "base_head_sha": "b" * 40,
            "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
            "prior_review": prior_review,
            "findings": [
                {
                    "id": "P1-prior-fix",
                    "severity": "P1",
                    "status": "resolved",
                    "summary": "Prior blocking defect.",
                    "introduced_by_diff": False,
                }
            ],
        }
    )
    result = evaluate_review_gate(review, diff)

    assert result["decision"] == "allowed", result["reasons"]


def test_round_two_rejects_paths_outside_prior_blocker_fix_scope() -> None:
    diff = load_diff() + (
        "diff --git a/docs/extra.md b/docs/extra.md\n"
        "new file mode 100644\n--- /dev/null\n+++ b/docs/extra.md\n"
        "@@ -0,0 +1 @@\n+unrelated scope\n"
    )
    review = valid_review()
    prior = copy.deepcopy(review)
    prior.update(
        {
            "base_head_sha": "c" * 40,
            "head_sha": "b" * 40,
            "verdict": "blocking",
            "findings": [
                {
                    "id": "P1-scoped",
                    "severity": "P1",
                    "status": "unresolved",
                    "summary": "Fix the application defect.",
                    "fix_paths": ["src/app.py"],
                }
            ],
        }
    )
    review.update(
        {
            "round": 2,
            "mode": "diff_only",
            "base_head_sha": "b" * 40,
            "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
            "prior_review": prior,
            "findings": [
                {
                    **prior["findings"][0],
                    "status": "resolved",
                    "introduced_by_diff": False,
                }
            ],
        }
    )
    result = evaluate_review_gate(review, diff)

    assert result["decision"] == "blocked"
    assert any(
        "start a new full review: docs/extra.md" in reason
        for reason in result["reasons"]
    )


def test_round_two_rejects_clean_prior_review() -> None:
    review = valid_review()
    prior_review = copy.deepcopy(review)
    prior_review["base_head_sha"] = "c" * 40
    prior_review["head_sha"] = "b" * 40
    review.update(
        {
            "round": 2,
            "mode": "diff_only",
            "base_head_sha": "b" * 40,
            "prior_review": prior_review,
        }
    )

    result = evaluate_review_gate(review, load_diff())

    assert result["decision"] == "blocked"
    assert (
        "round 2 requires an unresolved P0/P1 finding from round 1"
        in result["reasons"]
    )


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
    attestation = review_attestation_for(review)
    assert attestation is not None
    review_path = repo / "review.json"
    attestation_path = repo / "review-attestation.json"
    diff_path = repo / "review.patch"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
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
            "--review-attestation",
            str(attestation_path),
            "--gate-invocation-id",
            "gate-1",
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
