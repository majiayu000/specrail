"""Validate ephemeral host review attestation outside raw review artifacts."""

from __future__ import annotations

from typing import Any


COMMON_FIELDS = {
    "artifact_id",
    "head_sha",
    "invocation_id",
    "lane_id",
    "reviewer_actor",
}
PRIOR_FIELDS = {"prior_artifact_id", "prior_head_sha"}


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_review_attestation(
    review: dict[str, Any],
    attestation: dict[str, Any] | None,
    *,
    gate_invocation_id: str | None,
    required: bool,
) -> tuple[list[str], list[str]]:
    """Return (missing, reasons) for one current host-injected attestation."""

    missing: list[str] = []
    reasons: list[str] = []
    if not required:
        if attestation is not None:
            reasons.append("self_review must not include review_attestation")
        return missing, reasons
    if not isinstance(attestation, dict):
        return ["review_attestation"], reasons
    if not _non_empty(gate_invocation_id):
        missing.append("gate_invocation_id")

    unknown = sorted(set(attestation) - COMMON_FIELDS - PRIOR_FIELDS)
    absent = sorted(COMMON_FIELDS - set(attestation))
    if unknown:
        reasons.append(
            "review_attestation contains unsupported fields: "
            + ", ".join(unknown)
        )
    missing.extend(f"review_attestation.{field}" for field in absent)
    for field in ("artifact_id", "invocation_id", "lane_id", "reviewer_actor"):
        if field in attestation and not _non_empty(attestation.get(field)):
            reasons.append(f"review_attestation.{field} must be non-empty")
    if attestation.get("head_sha") != review.get("head_sha"):
        reasons.append("review_attestation.head_sha must match review head_sha")
    if attestation.get("artifact_id") != review.get("artifact_id"):
        reasons.append("review_attestation.artifact_id must match review")
    if _non_empty(gate_invocation_id) and (
        attestation.get("invocation_id") != gate_invocation_id
    ):
        reasons.append(
            "review_attestation.invocation_id must match gate invocation"
        )

    prior = review.get("prior_review")
    if review.get("round") == 2 and isinstance(prior, dict):
        expected = {
            "prior_artifact_id": prior.get("artifact_id"),
            "prior_head_sha": prior.get("head_sha"),
        }
        for field, value in expected.items():
            if attestation.get(field) != value:
                reasons.append(
                    f"review_attestation.{field} must match prior review"
                )
    elif set(attestation) & PRIOR_FIELDS:
        reasons.append("round 1 review_attestation must not bind prior review")
    return missing, reasons
