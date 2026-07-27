#!/usr/bin/env python3
"""GH-143 tiered merge authorization rules.

Split out of runtime_gate_rules.py to keep both rule files within the size
guard. These rules encode the GH-143 contract: standard_auto tier
authorization for fastlane/standard PRs with full green evidence plus
independent tier substantiation, heavy_manual per-PR human authorization for
everything else, and graded re-confirmation for post-authorization findings.
Every ambiguity fails closed to the heavy/critical side.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


# Audit anchor for merge_authorization.source; do not rename it.
TIER_POLICY_SOURCE = "tier_policy_gh143"
# Audit anchor for self_review_authorization.basis; do not rename it.
FASTLANE_SELF_REVIEW_BASIS = "fastlane_policy"
FASTLANE_MAX_CHANGED_LINES = 50
# specs/GH204 B-005: the coordinator self-review exception covers a small
# SINGLE-file PR only.
FASTLANE_MAX_CHANGED_FILES = 1
FASTLANE_TIER_EVIDENCE_SOURCE = "github_changed_files"
PR_TIERS = {"fastlane", "standard", "heavy"}
STANDARD_AUTO_TIERS = {"fastlane", "standard"}
AUTHORIZATION_TIERS = {"standard_auto", "heavy_manual"}
CI_TIER_CHECK_PASSED_STATUSES = {"passed", "success", "successful", "green"}
POST_AUTH_FINDING_SEVERITIES = {"critical", "important", "minor", "nit"}
POST_AUTH_FINDING_DISPOSITIONS = {"fixed_re_reviewed", "paused_re_authorized"}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _git_oid(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-fA-F]{40}([0-9a-fA-F]{24})?", value) is not None
    )


def _nonnegative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _valid_pr_tier_evidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not _nonnegative_int(value.get("changed_lines")):
        return False
    if not _nonnegative_int(value.get("changed_files")):
        return False
    touched_paths = value.get("touched_paths")
    return (
        isinstance(touched_paths, list)
        and bool(touched_paths)
        and all(_nonempty_string(path) for path in touched_paths)
        and value.get("source") == FASTLANE_TIER_EVIDENCE_SOURCE
        and _git_oid(value.get("head_sha"))
        and _nonempty_string(value.get("base_ref"))
        and _git_oid(value.get("base_sha"))
        and isinstance(value.get("paths_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["paths_sha256"]) is not None
    )


PROTECTED_PATH_PREFIXES = (
    ".buildkite/",
    ".circleci/",
    ".github/",
    ".gitlab/",
    "checks/",
    "integrations/",
    "migrations/",
    "review/",
    "schemas/",
    "skills/",
    "templates/",
)
# Workflow and policy contract assets. `skills/implx/SKILL.md:72-74` classifies
# contracts and authorization semantics as enforcement-sensitive surfaces, so a
# consumer repository with an empty sensitive registry must still fail closed on
# them rather than fall through to coordinator self-review.
PROTECTED_CONTRACT_FILES = {
    "agent_usage.md",
    "agents.md",
    "azure-pipelines.yaml",
    "azure-pipelines.yml",
    "claude.md",
    "jenkinsfile",
    "labels.yaml",
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "skills-lock.json",
    "spec.md",
    "states.yaml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
    "workflow.yaml",
    ".gitlab-ci.yml",
    ".gitlab-ci.yaml",
}
# Mirrors the enforcement-sensitive surfaces named in
# skills/implx/SKILL.md:72-74: gate code, enforcement, contracts, authorization
# semantics, schemas/migrations, security.
PROTECTED_TOKENS = {
    "api",
    "auth",
    "authentication",
    "authorization",
    "contract",
    "contracts",
    "enforcement",
    "gate",
    "gates",
    "migration",
    "migrations",
    "schema",
    "schemas",
    "security",
}


def _name_tokens(name: str) -> set[str]:
    """Split a path component into lowercase tokens on separator and case
    boundaries, so `auth_service.py`, `securityUtils.ts` and `auth.test.ts` all
    expose their protected token.

    Known limitation: matching is boundary-based, so a name that concatenates
    the token with no separator and no case change — `authservice.py`,
    `apiclient.py` — is not detected. Substring matching is not a safe
    substitute: short tokens like `api` and `gate` would also flag `capital`
    and `delegate`. Repositories that need those names covered must list them
    in the sensitive-path registry, which takes precedence over this fallback
    classifier.
    """

    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return {token for token in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if token}


def _fastlane_protected_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("/") or any(
        part in {".", ".."} for part in normalized.split("/")
    ):
        return True
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [part for part in normalized.split("/") if part]
    if normalized.lower().startswith(PROTECTED_PATH_PREFIXES):
        return True
    if parts and parts[-1].lower() in PROTECTED_CONTRACT_FILES:
        return True
    if any(part.lower() in PROTECTED_TOKENS for part in parts):
        return True
    filename = parts[-1] if parts else ""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return bool(_name_tokens(stem) & PROTECTED_TOKENS)


def pr_tier_evidence_identity_errors(
    value: Any,
    *,
    expected_head_sha: Any = None,
    expected_base_ref: Any = None,
    expected_base_sha: Any = None,
) -> list[str]:
    """Validate adapter provenance and the complete PR diff identity."""

    if not isinstance(value, dict):
        return ["pr_tier_evidence must be an object"]
    errors: list[str] = []
    if value.get("source") != FASTLANE_TIER_EVIDENCE_SOURCE:
        errors.append(
            "pr_tier_evidence.source must be "
            f"{FASTLANE_TIER_EVIDENCE_SOURCE}"
        )
    evidence_head = value.get("head_sha")
    if not _git_oid(evidence_head):
        errors.append("pr_tier_evidence.head_sha is required")
    elif _nonempty_string(expected_head_sha) and evidence_head != expected_head_sha:
        errors.append("pr_tier_evidence.head_sha must match current head_sha")
    evidence_base_ref = value.get("base_ref")
    if not _nonempty_string(evidence_base_ref):
        errors.append("pr_tier_evidence.base_ref is required")
    elif (
        _nonempty_string(expected_base_ref)
        and evidence_base_ref != expected_base_ref
    ):
        errors.append("pr_tier_evidence.base_ref must match current base_ref")
    evidence_base_sha = value.get("base_sha")
    if not _git_oid(evidence_base_sha):
        errors.append("pr_tier_evidence.base_sha is required")
    elif _nonempty_string(expected_base_sha) and evidence_base_sha != expected_base_sha:
        errors.append("pr_tier_evidence.base_sha must match current base_sha")
    return errors


def fastlane_tier_evidence_errors(
    value: Any,
    *,
    expected_head_sha: Any = None,
    expected_base_ref: Any = None,
    expected_base_sha: Any = None,
) -> list[str]:
    """Validate exact-diff, adapter-derived evidence for fastlane self-review."""

    if not _valid_pr_tier_evidence(value):
        if not isinstance(value, dict):
            return [
                "fastlane_policy requires pr_tier_evidence with changed_lines, "
                "touched_paths, and complete diff identity"
            ]
    assert isinstance(value, dict)
    errors = pr_tier_evidence_identity_errors(
        value,
        expected_head_sha=expected_head_sha,
        expected_base_ref=expected_base_ref,
        expected_base_sha=expected_base_sha,
    )
    changed_lines = value.get("changed_lines")
    if not _nonnegative_int(changed_lines):
        errors.append("fastlane_policy pr_tier_evidence.changed_lines is invalid")
    elif changed_lines > FASTLANE_MAX_CHANGED_LINES:
        errors.append(
            f"fastlane_policy changed_lines must be at most "
            f"{FASTLANE_MAX_CHANGED_LINES}; got {changed_lines}"
        )
    # specs/GH204 B-005 limits the coordinator self-review exception to a small
    # single-file PR. touched_paths cannot carry that condition because a rename
    # contributes both its previous and current path, so require the trusted
    # adapter file count instead.
    # A binary or otherwise non-textual change reports zero additions and
    # deletions, so an arbitrarily large one would satisfy the line bound
    # without ever being measured.
    if value.get("changed_lines_countable") is not True:
        errors.append(
            "fastlane_policy requires a countable textual diff; "
            "pr_tier_evidence.changed_lines_countable must be true"
        )
    changed_files = value.get("changed_files")
    if not _nonnegative_int(changed_files):
        errors.append("fastlane_policy pr_tier_evidence.changed_files is invalid")
    elif changed_files != FASTLANE_MAX_CHANGED_FILES:
        errors.append(
            f"fastlane_policy changed_files must be exactly "
            f"{FASTLANE_MAX_CHANGED_FILES}; got {changed_files}"
        )
    touched_paths = value.get("touched_paths")
    valid_paths = (
        isinstance(touched_paths, list)
        and bool(touched_paths)
        and all(_nonempty_string(path) for path in touched_paths)
    )
    normalized_paths = (
        sorted(str(path).strip() for path in touched_paths)
        if valid_paths
        else []
    )
    if not valid_paths:
        errors.append("fastlane_policy pr_tier_evidence.touched_paths is invalid")
    elif touched_paths != normalized_paths or len(set(normalized_paths)) != len(
        normalized_paths
    ):
        errors.append(
            "fastlane_policy touched_paths must be the complete sorted unique snapshot"
        )
    protected = [path for path in normalized_paths if _fastlane_protected_path(path)]
    if protected:
        errors.append(
            "fastlane_policy cannot cover protected path(s): "
            + ", ".join(protected)
        )
    expected_digest = hashlib.sha256(
        json.dumps(normalized_paths, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if value.get("paths_sha256") != expected_digest:
        errors.append(
            "fastlane_policy pr_tier_evidence.paths_sha256 must bind touched_paths"
        )
    return errors


def _validate_fastlane_self_review(
    raw_item: dict[str, Any],
    authorization: dict[str, Any],
    label: str,
    errors: list[str],
) -> None:
    """Fastlane self-review policy: a `fastlane`-tier item with valid tier
    evidence on a non-enforcement-sensitive surface may use coordinator
    self-review without recorded reviewer-lane failures. Every other
    review_source rule (local review artifact, passed status, evidence)
    still applies; eligibility gaps fail closed to the strict lane-failure
    path requirements."""
    if raw_item.get("pr_tier") != "fastlane":
        errors.append(
            f"{label}: self_review_authorization.basis {FASTLANE_SELF_REVIEW_BASIS} "
            "requires pr_tier fastlane"
        )
    if raw_item.get("enforcement_sensitive") is not False:
        errors.append(
            f"{label}: {FASTLANE_SELF_REVIEW_BASIS} self-review requires "
            "enforcement_sensitive false"
        )
    errors.extend(
        f"{label}: {error}"
        for error in fastlane_tier_evidence_errors(
            raw_item.get("pr_tier_evidence"),
            expected_head_sha=raw_item.get("head_sha"),
        )
    )
    for key in ["scope", "conversation_marker"]:
        if not _nonempty_string(authorization.get(key)):
            errors.append(f"{label}: self_review_authorization.{key} is required")


def _item_review_source(raw_item: dict[str, Any]) -> str:
    review = raw_item.get("review")
    review = review if isinstance(review, dict) else {}
    for value in [review.get("review_source"), raw_item.get("review_source")]:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _tier_authorization_declared(raw_item: dict[str, Any]) -> bool:
    authorization = raw_item.get("merge_authorization")
    source = authorization.get("source") if isinstance(authorization, dict) else None
    return source == TIER_POLICY_SOURCE or "authorization_tier" in raw_item


def _validate_tier_authorization(
    raw_item: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    auth_mode: str = "",
    review_artifact: dict[str, Any] | None = None,
    ci_tier_check: dict[str, Any] | None = None,
    ci_tier_check_declared: bool = False,
) -> None:
    """GH-143 B-002..B-006: validate tier-scoped merge authorization.

    Dispute state and tier attestation are trusted only from the
    reviewer-lane review artifact, never from implementer-side checkpoint
    fields. Self-reported pr_tier_evidence alone is never sufficient for
    standard_auto.
    """
    authorization = raw_item.get("merge_authorization")
    authorization = authorization if isinstance(authorization, dict) else {}
    source = authorization.get("source")
    tier = raw_item.get("authorization_tier")

    if tier is not None and (not isinstance(tier, str) or tier not in AUTHORIZATION_TIERS):
        allowed = ", ".join(sorted(AUTHORIZATION_TIERS))
        errors.append(f"{label}: authorization_tier must be one of: {allowed}")
        return

    if source != TIER_POLICY_SOURCE:
        if tier == "standard_auto":
            errors.append(
                f"{label}: authorization_tier standard_auto requires "
                f"merge_authorization.source {TIER_POLICY_SOURCE}"
            )
        return

    if str(auth_mode).strip().lower() != "review":
        errors.append(
            f"{label}: tier authorization ({TIER_POLICY_SOURCE}) is only valid "
            "when checkpoint auth_mode is review"
        )
    if tier != "standard_auto":
        errors.append(
            f"{label}: merge_authorization.source {TIER_POLICY_SOURCE} requires "
            "authorization_tier standard_auto; heavy_manual requires per-PR "
            "human authorization, not the tier policy source"
        )
        return

    if raw_item.get("enforcement_sensitive") is True:
        errors.append(
            f"{label}: enforcement-sensitive item cannot use standard_auto; "
            "fall back to heavy_manual per-PR human authorization"
        )

    pr_tier = raw_item.get("pr_tier")
    if not isinstance(pr_tier, str) or pr_tier not in PR_TIERS:
        errors.append(
            f"{label}: standard_auto requires pr_tier fastlane or standard; "
            "missing or invalid pr_tier fails closed to heavy_manual"
        )
        return
    if pr_tier not in STANDARD_AUTO_TIERS:
        errors.append(
            f"{label}: pr_tier {pr_tier} requires heavy_manual per-PR human "
            "authorization; standard_auto is not applicable"
        )
        return

    tier_errors = pr_tier_evidence_identity_errors(
        raw_item.get("pr_tier_evidence"),
        expected_head_sha=raw_item.get("head_sha"),
    )
    if not _valid_pr_tier_evidence(raw_item.get("pr_tier_evidence")) or tier_errors:
        detail = "; ".join(tier_errors)
        suffix = f": {detail}" if detail else ""
        errors.append(
            f"{label}: standard_auto requires pr_tier_evidence derived by the "
            f"adapter and bound to the current head and base{suffix}; missing tier evidence "
            "fails closed to heavy_manual"
        )

    item_is_self_review = _item_review_source(raw_item) == "self_review"
    if item_is_self_review:
        errors.append(
            f"{label}: review_source self_review cannot qualify for "
            "standard_auto; there is no independent party, so the item fails "
            "closed to heavy_manual regardless of attestation content"
        )

    substantiated: list[str] = []
    if ci_tier_check_declared and ci_tier_check is not None:
        ci_status = str(
            ci_tier_check.get("status") or ci_tier_check.get("conclusion") or ""
        ).lower()
        ci_pr_tier = ci_tier_check.get("pr_tier")
        if ci_status not in CI_TIER_CHECK_PASSED_STATUSES:
            errors.append(
                f"{label}: ci_tier_check artifact status must be a passing tier check"
            )
        elif ci_pr_tier != pr_tier:
            errors.append(
                f"{label}: ci_tier_check pr_tier {ci_pr_tier!r} disagrees with "
                f"checkpoint pr_tier {pr_tier!r}; the disagreement is a tier "
                "dispute and fails closed to heavy_manual"
            )
        else:
            substantiated.append("ci_tier_check artifact")

    attestation: dict[str, Any] | None = None
    artifact_head: Any = None
    artifact_review_source: Any = None
    if isinstance(review_artifact, dict):
        artifact_head = review_artifact.get("head_sha")
        artifact_review_source = review_artifact.get("review_source")
        if review_artifact.get("tier_dispute") is True:
            errors.append(
                f"{label}: reviewer lane recorded tier_dispute; standard_auto "
                "is blocked until the dispute is resolved by a human decision"
            )
        raw_attestation = review_artifact.get("tier_attestation")
        if isinstance(raw_attestation, dict):
            attestation = raw_attestation

    if attestation is not None:
        item_head = raw_item.get("head_sha")
        if artifact_review_source != "independent_lane" or item_is_self_review:
            errors.append(
                f"{label}: tier_attestation is trusted only from a review "
                "artifact whose own review_source is independent_lane on a "
                "non-self_review item; a self-authored attestation cannot "
                "grant standard_auto (fails closed to heavy_manual)"
            )
        elif attestation.get("attested") is not True or not _nonempty_string(
            attestation.get("basis")
        ):
            errors.append(
                f"{label}: reviewer tier_attestation requires attested true "
                "and a non-empty basis"
            )
        elif attestation.get("pr_tier") != pr_tier:
            errors.append(
                f"{label}: reviewer tier_attestation pr_tier "
                f"{attestation.get('pr_tier')!r} disagrees with checkpoint "
                f"pr_tier {pr_tier!r}; the mismatch is a tier dispute and "
                "fails closed to heavy_manual"
            )
        elif (
            _nonempty_string(artifact_head)
            and _nonempty_string(item_head)
            and artifact_head != item_head
        ):
            errors.append(
                f"{label}: reviewer tier_attestation artifact head_sha must "
                "match item head_sha"
            )
        else:
            substantiated.append("reviewer-lane tier_attestation")

    if not substantiated:
        errors.append(
            f"{label}: standard_auto requires independent tier substantiation "
            "beyond self-reported pr_tier_evidence: a gate-verifiable "
            "ci_tier_check artifact or a reviewer-lane tier_attestation in "
            "the review artifact; both are missing (fails closed to "
            "heavy_manual)"
        )


def _validate_post_authorization_findings(
    raw_item: dict[str, Any],
    label: str,
    errors: list[str],
    *,
    review_artifact: dict[str, Any] | None = None,
) -> None:
    """GH-143 B-008..B-010: graded re-confirmation for post-authorization findings.

    Severity/mechanical classifications are trusted only from the
    reviewer-lane review artifact finding_classifications records.
    Implementer-only or mismatched classifications are treated as critical
    (fail-closed), which voids the original authorization and requires
    re_authorization.
    """
    findings = raw_item.get("post_authorization_findings")
    if findings is None:
        return
    if not isinstance(findings, list):
        errors.append(f"{label}: post_authorization_findings must be a list")
        return

    classifications: dict[str, dict[str, Any]] = {}
    if isinstance(review_artifact, dict):
        raw_entries = review_artifact.get("finding_classifications")
        if isinstance(raw_entries, list):
            for entry in raw_entries:
                if isinstance(entry, dict) and _nonempty_string(entry.get("finding_ref")):
                    classifications[entry["finding_ref"].strip()] = entry

    re_authorization = raw_item.get("re_authorization")
    has_re_authorization = (
        isinstance(re_authorization, dict)
        and _nonempty_string(re_authorization.get("actor"))
        and _nonempty_string(re_authorization.get("source"))
    )

    for index, finding in enumerate(findings, start=1):
        flabel = f"{label}: post_authorization_findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{flabel} must be an object")
            continue
        severity = finding.get("severity")
        mechanical = finding.get("mechanical")
        disposition = finding.get("disposition")
        finding_ref = finding.get("finding_ref")

        if severity is not None and severity not in POST_AUTH_FINDING_SEVERITIES:
            allowed = ", ".join(sorted(POST_AUTH_FINDING_SEVERITIES))
            errors.append(f"{flabel}.severity must be one of: {allowed}")
        if disposition is not None and disposition not in POST_AUTH_FINDING_DISPOSITIONS:
            allowed = ", ".join(sorted(POST_AUTH_FINDING_DISPOSITIONS))
            errors.append(f"{flabel}.disposition must be one of: {allowed}")

        reviewer_entry = (
            classifications.get(finding_ref.strip())
            if _nonempty_string(finding_ref)
            else None
        )
        treat_as_critical = False
        reason = ""
        if reviewer_entry is None:
            treat_as_critical = True
            reason = (
                "no reviewer-lane finding_classifications record; implementer "
                "self-classification is not trusted"
            )
        else:
            reviewer_severity = reviewer_entry.get("severity")
            reviewer_mechanical = reviewer_entry.get("mechanical")
            if (
                reviewer_severity not in POST_AUTH_FINDING_SEVERITIES
                or not isinstance(reviewer_mechanical, bool)
            ):
                treat_as_critical = True
                reason = "reviewer-lane classification is missing or invalid"
            elif reviewer_severity != severity or reviewer_mechanical != mechanical:
                treat_as_critical = True
                reason = (
                    "implementer classification disagrees with the "
                    "reviewer-lane record"
                )
            elif reviewer_severity == "critical" or reviewer_mechanical is False:
                treat_as_critical = True
                reason = "reviewer-lane classification is critical or non-mechanical"

        if treat_as_critical:
            if not has_re_authorization:
                errors.append(
                    f"{flabel}: treated as critical ({reason}); the original "
                    "authorization is void and merging requires a new "
                    "re_authorization with actor and source"
                )
            continue

        if disposition != "fixed_re_reviewed":
            errors.append(
                f"{flabel}: mechanical finding requires disposition "
                "fixed_re_reviewed with a post-fix independent re-review"
            )
