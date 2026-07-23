from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from runtime_ledger_test_support import ROOT, clean_checkpoint  # noqa: E402
from runtime_ledger_gate import evaluate_checkpoint  # noqa: E402


# --- GH-143: tiered merge authorization ---


HEAD_SHA = "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"


def _review_artifact_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_id": "pr718-head1-reviewer1",
        "pr": 718,
        "reviewer_lane": "merge-reviewer-1",
        "producer_identity": "reviewer-1",
        "review_source": "independent_lane",
        "review_execution": "local",
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


def test_self_review_attestation_cannot_grant_standard_auto(tmp_path: Path) -> None:
    """P0 regression: a self-authored tier_attestation under review_source
    self_review must never substantiate standard_auto; the item fails closed
    to heavy_manual (blocked)."""
    checkpoint = _standard_auto_checkpoint(
        tmp_path,
        review_source="self_review",
        reviewer_lane="implementer-lane",
        producer_identity="implementer",
    )
    item = checkpoint["items"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    item["review_source"] = "self_review"
    review = item["review"]
    assert isinstance(review, dict)
    review["review_source"] = "self_review"

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "review_source self_review cannot qualify for standard_auto" in error
        for error in result["errors"]
    )
    assert any(
        "self-authored attestation cannot grant standard_auto" in error
        for error in result["errors"]
    )


def test_non_independent_artifact_attestation_not_substantiating(
    tmp_path: Path,
) -> None:
    """P0: even when the checkpoint item claims independent_lane, an
    attestation inside an artifact whose own review_source is self_review is
    not independent substantiation."""
    checkpoint = _standard_auto_checkpoint(tmp_path, review_source="self_review")

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any(
        "self-authored attestation cannot grant standard_auto" in error
        for error in result["errors"]
    )


def test_malformed_review_artifact_fails_closed(tmp_path: Path) -> None:
    """P3: a review artifact that fails review_result.schema.json validation
    is a hard error and yields no substantiation."""
    checkpoint = _standard_auto_checkpoint(tmp_path)
    payload = _review_artifact_payload()
    payload.pop("verdict")
    (tmp_path / "review-artifact.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    result = evaluate_checkpoint(checkpoint)

    assert result["decision"] == "blocked"
    assert any("review artifact" in error for error in result["errors"])
    assert any(
        "independent tier substantiation" in error for error in result["errors"]
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
