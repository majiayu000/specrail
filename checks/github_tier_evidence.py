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

import json
from pathlib import Path
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

    `changed_lines_countable` is false when any file carries no textual diff
    (a binary change reports zero additions and deletions), so a size-bounded
    tier can fail closed instead of measuring an unmeasured change as 0.
    """

    return {
        "changed_lines": pr_snapshot.get("changed_lines"),
        "changed_lines_countable": pr_snapshot.get("changed_lines_countable"),
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

    # A dispute blocks tier authorization on its own, so it must be checked
    # before any per-artifact filtering. A reviewer that raises a dispute
    # without writing an attestation of their own is the ordinary case, and
    # skipping such an artifact would let a second lane's attestation through
    # — the runtime-side check in runtime_tier_authorization.py is likewise
    # unconditional.
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("head_sha") != head_sha:
            continue
        if artifact.get("tier_dispute") is True:
            raise TierEvidenceError(
                "reviewer lane recorded tier_dispute at the current head; "
                "tier authorization is blocked until a human resolves it"
            )

    endorsements: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        attestation = artifact.get("tier_attestation")
        if not isinstance(attestation, dict):
            continue
        if artifact.get("head_sha") != head_sha:
            continue
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


def manifest_may_carry_tier_attestation(repo: Any, manifest_path: Any) -> bool:
    """Cheap, unvalidated pre-scan: does this review manifest reference any
    artifact carrying a `tier_attestation`?

    The collector must decide whether to fetch the PR file snapshot *before*
    the manifest is authoritatively loaded. Forcing the snapshot for every
    manifest breaks stacked PRs, whose base differs from the default branch and
    which `collect_pr_file_snapshot` therefore rejects. This read only gates
    that decision — the authoritative validation still happens in
    `load_review_manifest`. Any parse or IO problem errs toward True so a real
    attestation is never missed on the strength of a failed guess.
    """

    if not isinstance(manifest_path, str) or not manifest_path.strip():
        return False
    root = Path(repo) if repo is not None else Path(".")
    try:
        manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    if not isinstance(manifest, dict):
        return True
    lanes = manifest.get("lanes")
    if not isinstance(lanes, list):
        return True
    for lane in lanes:
        if not isinstance(lane, dict):
            return True
        paths = lane.get("artifact_paths")
        if not isinstance(paths, list):
            return True
        for artifact_path in paths:
            if not isinstance(artifact_path, str):
                return True
            try:
                artifact = json.loads(
                    (root / artifact_path).read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                return True
            if not isinstance(artifact, dict):
                return True
            if artifact.get("tier_attestation") is not None:
                return True
    return False
