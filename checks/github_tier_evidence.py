#!/usr/bin/env python3
"""Adapter-derived GH-143 tier evidence and reviewer-lane tier attestation.

Split out of github_pr_evidence.py to keep that collector within the size
guard. Two responsibilities:

* `adapter_tier_evidence` turns a trusted current-head PR file snapshot into
  the objective changed-line / changed-file / path identity that every tier
  decision must rest on.
* `trusted_tier_attestation` picks the reviewer-lane tier endorsement that may
  set `pr_tier`. Only an `independent_lane` artifact at the current head may do
  so; disputes, disagreement and self-authored attestations fail closed.
"""

from __future__ import annotations

from typing import Any

from runtime_tier_authorization import (
    FASTLANE_TIER_EVIDENCE_SOURCE,
    pr_tier_evidence_identity_errors,
)


class TierEvidenceError(Exception):
    """Raised when reviewer tier attestation cannot be trusted."""


def adapter_tier_evidence(pr_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Objective diff identity derived from the trusted GitHub file snapshot.

    `changed_files` is GitHub's own `changedFiles` count, not `len(paths)`:
    a rename contributes both its previous and current path, so the path list
    cannot carry the single-file eligibility condition.
    """

    return {
        "changed_lines": pr_snapshot.get("changed_lines"),
        "changed_files": pr_snapshot.get("file_count"),
        "touched_paths": pr_snapshot.get("paths"),
        "source": FASTLANE_TIER_EVIDENCE_SOURCE,
        "head_sha": pr_snapshot.get("head_sha"),
        "base_ref": pr_snapshot.get("base_ref"),
        "base_sha": pr_snapshot.get("base_sha"),
        "paths_sha256": pr_snapshot.get("paths_sha256"),
    }


def trusted_tier_attestation(
    review_evidence: dict[str, Any],
    head_sha: str,
) -> dict[str, Any] | None:
    """Return `{"pr_tier", "artifact_path"}` when the reviewer lane endorses a
    tier at the current head, or None when no attestation is present.

    Raises TierEvidenceError when an attestation exists but cannot be trusted,
    so the caller fails closed to per-PR human authorization instead of
    silently dropping to an unattested tier.
    """

    artifacts = review_evidence.get("artifacts")
    if not isinstance(artifacts, list):
        return None

    endorsements: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        attestation = artifact.get("tier_attestation")
        if not isinstance(attestation, dict):
            continue
        if artifact.get("head_sha") != head_sha:
            continue
        if artifact.get("tier_dispute") is True:
            raise TierEvidenceError(
                "reviewer lane recorded tier_dispute at the current head; "
                "tier authorization is blocked until a human resolves it"
            )
        if artifact.get("review_source") != "independent_lane":
            raise TierEvidenceError(
                "tier_attestation is trusted only from a review artifact whose "
                "own review_source is independent_lane"
            )
        if attestation.get("attested") is not True:
            raise TierEvidenceError("reviewer tier_attestation requires attested true")
        basis = attestation.get("basis")
        if not isinstance(basis, str) or not basis.strip():
            raise TierEvidenceError(
                "reviewer tier_attestation requires a non-empty basis"
            )
        artifact_path = artifact.get("artifact_path")
        if not isinstance(artifact_path, str) or not artifact_path.strip():
            raise TierEvidenceError(
                "reviewer tier_attestation requires a manifest artifact path"
            )
        endorsements.append(
            {
                "pr_tier": attestation.get("pr_tier"),
                "artifact_path": artifact_path.strip(),
            }
        )

    if not endorsements:
        return None
    tiers = {item["pr_tier"] for item in endorsements}
    if len(tiers) > 1:
        raise TierEvidenceError(
            "reviewer lanes attest disagreeing pr_tier values "
            f"({', '.join(sorted(str(tier) for tier in tiers))}); the mismatch "
            "is a tier dispute and fails closed"
        )
    return endorsements[0]


def apply_independent_lane_tier(
    evidence: dict[str, Any],
    review_evidence: dict[str, Any],
    pr_snapshot: Any,
    head_sha: str,
) -> None:
    """Attach adapter-derived tier evidence for an independently reviewed PR.

    GH-143 `standard_auto` is documented for independently reviewed
    fastlane/standard PRs, but the fastlane self-review branch is the only
    other place the collector emits tier evidence. Without this the documented
    path is unreachable through the supported collector and silently degrades
    to per-PR human authorization.
    """

    if "pr_tier" in evidence:
        return
    attestation = trusted_tier_attestation(review_evidence, head_sha)
    if attestation is None:
        return
    if not isinstance(pr_snapshot, dict) or pr_snapshot.get("head_sha") != head_sha:
        raise TierEvidenceError(
            "reviewer tier_attestation requires a complete current-head PR "
            "file snapshot"
        )
    tier_evidence = adapter_tier_evidence(pr_snapshot)
    tier_errors = pr_tier_evidence_identity_errors(
        tier_evidence,
        expected_head_sha=head_sha,
        expected_base_ref=pr_snapshot.get("base_ref"),
        expected_base_sha=pr_snapshot.get("base_sha"),
    )
    if tier_errors:
        raise TierEvidenceError("; ".join(tier_errors))
    evidence["pr_tier"] = attestation["pr_tier"]
    evidence["pr_tier_evidence"] = tier_evidence
    evidence["tier_attestation_ref"] = attestation["artifact_path"]
    evidence["base_ref"] = pr_snapshot.get("base_ref")
    evidence["base_sha"] = pr_snapshot.get("base_sha")
