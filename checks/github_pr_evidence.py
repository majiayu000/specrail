#!/usr/bin/env python3
"""Collect the compact current GitHub state consumed by pr_gate.py."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _lib.review_attestation import validate_review_attestation
from github_evidence_common import (
    EvidenceError,
    collect_head_push_boundary as _collect_head_push_boundary,
    collect_hosted_findings as _collect_hosted_findings,
    combine_review_findings,
    json_object,
    normalize_checks,
)
from github_issue_reference import normalize_issue_reference, relation_snapshot
from sensitive_enforcement import classify_sensitive_changes, sensitive_registry
from specrail_lib import (
    PackConfig,
    SpecRailError,
    load_pack,
    resolve_path,
    spec_packet_artifact_paths,
    validate_verification_profiles,
    verification_profiles,
)


PR_VIEW_FIELDS = [
    "number",
    "state",
    "isDraft",
    "headRefOid",
    "headRefName",
    "headRepository",
    "headRepositoryOwner",
    "baseRefName",
    "baseRefOid",
    "mergeStateStatus",
    "body",
    "closingIssuesReferences",
    "statusCheckRollup",
    "changedFiles",
]
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PROFILES = {"fastlane", "standard", "heavy"}
def parse_github_repo(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if not REPO_PATTERN.fullmatch(value):
        raise EvidenceError("GitHub repository must use OWNER/REPO format")
    owner, name = value.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise EvidenceError("GitHub repository owner and name must be explicit")
    return owner, name


def _parse_positive(raw: str, label: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be a positive integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{label} must be a positive integer")
    return value


def parse_pr_number(raw: str) -> int:
    return _parse_positive(raw, "PR number")


def parse_issue_number(raw: str) -> int:
    return _parse_positive(raw, "issue number")


def run_gh_json(args: list[str]) -> Any:
    try:
        completed = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise EvidenceError("gh executable was not found in PATH") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise EvidenceError(f"gh command failed: {' '.join(args[:3])}: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"gh command returned invalid JSON: {exc.msg}") from exc


def collect_head_push_boundary(
    github_repo: str,
    head_ref: str,
    head_sha: str,
) -> str:
    parse_github_repo(github_repo)
    return _collect_head_push_boundary(
        run_gh_json,
        github_repo,
        head_ref,
        head_sha,
    )


def collect_hosted_findings(
    github_repo: str,
    pr_number: int,
    expected_head: str,
) -> list[dict[str, Any]]:
    parse_github_repo(github_repo)
    return _collect_hosted_findings(
        run_gh_json,
        github_repo,
        pr_number,
        expected_head,
    )


def collect_pr_view(github_repo: str, pr_number: int) -> dict[str, Any]:
    payload = json_object(
        run_gh_json(
            [
                "pr",
                "view",
                str(pr_number),
                "--repo",
                github_repo,
                "--json",
                ",".join(PR_VIEW_FIELDS),
            ]
        ),
        "gh pr view response",
    )
    count = payload.get("changedFiles")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise EvidenceError("changedFiles must be a non-negative integer")
    payload["files"] = [
        {"path": path}
        for path in collect_changed_files(github_repo, pr_number, count)
    ]
    return payload


def collect_changed_files(
    github_repo: str,
    pr_number: int,
    expected_count: int,
) -> list[str]:
    """Collect the complete REST-paginated current changed-file set."""
    owner, name = parse_github_repo(github_repo)
    paths: list[str] = []
    if expected_count == 0:
        return paths
    for page in range(1, 1001):
        raw = run_gh_json(
            [
                "api",
                "--method",
                "GET",
                f"repos/{owner}/{name}/pulls/{pr_number}/files",
                "-F",
                "per_page=100",
                "-F",
                f"page={page}",
            ]
        )
        if not isinstance(raw, list):
            raise EvidenceError("pull files REST response must be an array")
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
                raise EvidenceError(
                    f"pull files page {page} item #{index} requires filename"
                )
            filename = item["filename"].strip()
            if not filename:
                raise EvidenceError(
                    f"pull files page {page} item #{index} filename must be non-empty"
                )
            paths.append(filename)
        if len(paths) >= expected_count:
            break
        if len(raw) < 100:
            break
    else:
        raise EvidenceError("pull files REST pagination exceeded 1000 pages")
    if len(paths) != expected_count:
        raise EvidenceError(
            f"pull files REST snapshot incomplete: collected {len(paths)} "
            f"of {expected_count}"
        )
    if len(set(paths)) != len(paths):
        raise EvidenceError("pull files REST snapshot contains duplicate paths")
    return sorted(paths)


def _effective_collection_profile(
    profile: str,
    paths: list[str],
    *,
    linked_issue: int,
    repo: Path | None,
    config: PackConfig | None,
) -> str:
    if repo is None or config is None:
        return profile
    spec_refs: list[str] = []
    if sensitive_registry(config)["specs"]:
        packet = spec_packet_artifact_paths(config, linked_issue)
        spec_refs = [
            packet[name]
            for name in ("product_spec", "tech_spec", "task_plan")
        ]
    try:
        classification = classify_sensitive_changes(
            config,
            repo,
            paths,
            spec_refs,
            source="github_changed_files",
        )
    except SpecRailError as exc:
        raise EvidenceError(str(exc)) from exc
    return "heavy" if classification["enforcement_sensitive"] else profile


def collect_issue_view(github_repo: str, issue_number: int) -> dict[str, Any]:
    return json_object(
        run_gh_json(
            [
                "issue",
                "view",
                str(issue_number),
                "--repo",
                github_repo,
                "--json",
                "number,state,url",
            ]
        ),
        "gh issue view response",
    )


def _require_positive_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return value


def _require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a non-empty string")
    return value.strip()


def _head_repository_name(payload: dict[str, Any]) -> str:
    repository = payload.get("headRepository")
    if not isinstance(repository, dict) or "nameWithOwner" not in repository:
        raise EvidenceError("headRepository.nameWithOwner is required")
    name_with_owner = repository.get("nameWithOwner")
    if not isinstance(name_with_owner, str):
        raise EvidenceError("headRepository.nameWithOwner must be a string")
    owner = payload.get("headRepositoryOwner")
    owner_login = owner.get("login") if isinstance(owner, dict) else None
    repository_name = repository.get("name")
    if name_with_owner.strip():
        normalized = "/".join(parse_github_repo(name_with_owner))
        if (
            isinstance(owner_login, str)
            and owner_login.strip()
            and owner_login.strip() != normalized.split("/", 1)[0]
        ):
            raise EvidenceError("headRepository owner metadata is inconsistent")
        if (
            isinstance(repository_name, str)
            and repository_name.strip()
            and repository_name.strip() != normalized.split("/", 1)[1]
        ):
            raise EvidenceError("headRepository name metadata is inconsistent")
        return normalized
    if (
        not isinstance(owner_login, str)
        or not owner_login.strip()
        or not isinstance(repository_name, str)
        or not repository_name.strip()
    ):
        raise EvidenceError(
            "empty headRepository.nameWithOwner requires owner login and repository name"
        )
    return "/".join(
        parse_github_repo(f"{owner_login.strip()}/{repository_name.strip()}")
    )


def _require_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise EvidenceError(f"{field} must be a boolean")
    return value


def _changed_files(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("files")
    if not isinstance(raw, list):
        raise EvidenceError("PR files must be a complete array")
    paths: list[str] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise EvidenceError(f"PR file #{index} must contain a path")
        path = item["path"].strip()
        if not path:
            raise EvidenceError(f"PR file #{index} path must be non-empty")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise EvidenceError("PR file snapshot contains duplicate paths")
    return sorted(paths)


def _paths_digest(paths: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(paths, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalized_checks(payload: dict[str, Any], head_sha: str) -> list[dict[str, Any]]:
    checks = normalize_checks(payload.get("statusCheckRollup"))
    for check in checks:
        check["head_sha"] = head_sha
    return checks


def _linked_issue(
    payload: dict[str, Any],
    expected_issue: int | None,
    issue_payload: dict[str, Any] | None,
) -> int:
    linked, _reference = normalize_issue_reference(
        payload,
        expected_issue,
        issue_payload,
    )
    if linked is None:
        raise EvidenceError("PR must link exactly one issue")
    return linked


def _validate_review_attestation_input(
    review: dict[str, Any],
    attestation: dict[str, Any] | None,
    *,
    head_sha: str,
    invocation_id: str,
    required: bool,
) -> dict[str, Any]:
    prior = review.get("prior_review")
    if "review_attestation" in review or (
        isinstance(prior, dict) and "review_attestation" in prior
    ):
        raise EvidenceError(
            "review_attestation must be injected separately by a trusted "
            "host or coordinator"
        )
    missing, reasons = validate_review_attestation(
        review,
        attestation,
        gate_invocation_id=invocation_id,
        required=required,
    )
    if missing or reasons:
        raise EvidenceError("; ".join([*missing, *reasons]))
    if attestation is not None and attestation.get("head_sha") != head_sha:
        raise EvidenceError("review attestation head_sha must match PR head")
    return dict(review)


def build_evidence(
    pr_payload: dict[str, Any],
    *,
    repository: str,
    profile: str,
    gate_invocation_id: str,
    review: dict[str, Any],
    expected_issue: int | None = None,
    issue_payload: dict[str, Any] | None = None,
    repo: Path | None = None,
    config: PackConfig | None = None,
    authorization: dict[str, Any] | None = None,
    checks_unavailable: dict[str, Any] | None = None,
    review_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a single trusted PR snapshot into the compact contract."""

    parse_github_repo(repository)
    if profile not in PROFILES:
        raise EvidenceError("profile must be fastlane, standard, or heavy")
    if not isinstance(gate_invocation_id, str) or not gate_invocation_id.strip():
        raise EvidenceError("gate_invocation_id must be a non-empty string")
    head_sha = _require_string(pr_payload, "headRefOid")
    paths = _changed_files(pr_payload)
    linked_issue = _linked_issue(pr_payload, expected_issue, issue_payload)
    classification = None
    enforcement_sensitive = False
    if repo is not None and config is not None:
        spec_refs: list[str] = []
        if sensitive_registry(config)["specs"]:
            packet = spec_packet_artifact_paths(config, linked_issue)
            spec_refs = [
                packet[name]
                for name in ("product_spec", "tech_spec", "task_plan")
            ]
        try:
            classification = classify_sensitive_changes(
                config,
                repo,
                paths,
                spec_refs,
                source="github_changed_files",
            )
        except SpecRailError as exc:
            raise EvidenceError(str(exc)) from exc
        enforcement_sensitive = bool(classification["enforcement_sensitive"])
        if enforcement_sensitive:
            profile = "heavy"
    review = _validate_review_attestation_input(
        review,
        review_attestation,
        head_sha=head_sha,
        invocation_id=gate_invocation_id.strip(),
        required=profile in {"standard", "heavy"},
    )
    evidence: dict[str, Any] = {
        "contract_version": 3,
        "repository": repository,
        "pr": _require_positive_int(pr_payload, "number"),
        "linked_issue": linked_issue,
        "state": _require_string(pr_payload, "state").upper(),
        "is_draft": _require_bool(pr_payload, "isDraft"),
        "base_sha": _require_string(pr_payload, "baseRefOid"),
        "base_ref": _require_string(pr_payload, "baseRefName"),
        "head_sha": head_sha,
        "gate_query_head_sha": head_sha,
        "changed_files": paths,
        "changed_files_count": len(paths),
        "changed_files_sha256": _paths_digest(paths),
        "checks": _normalized_checks(pr_payload, head_sha),
        "merge_state": _require_string(pr_payload, "mergeStateStatus").upper(),
        "profile": profile,
        "enforcement_sensitive": enforcement_sensitive,
        "review": review,
        "gate_invocation_id": gate_invocation_id.strip(),
    }
    if classification is not None:
        evidence["sensitive_classification"] = classification
    if authorization is not None:
        evidence["human_merge_authorization"] = authorization
    if review_attestation is not None:
        evidence["review_attestation"] = dict(review_attestation)
    if checks_unavailable is not None:
        evidence["checks_unavailable"] = checks_unavailable
        default_base_ref = checks_unavailable.get("default_base_ref")
        if isinstance(default_base_ref, str):
            evidence["default_base_ref"] = default_base_ref
    return evidence


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvidenceError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid {label} JSON {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} JSON must be an object")
    return value


def collect_evidence(
    github_repo: str,
    pr_number: int,
    *,
    profile: str,
    gate_invocation_id: str,
    review: dict[str, Any],
    authorization: dict[str, Any] | None = None,
    checks_unavailable: dict[str, Any] | None = None,
    review_attestation: dict[str, Any] | None = None,
    expected_issue: int | None = None,
    repo: Path | None = None,
    config: PackConfig | None = None,
) -> dict[str, Any]:
    """Collect twice and reject a moving head, issue relation, or file set."""

    parse_github_repo(github_repo)
    before = collect_pr_view(github_repo, pr_number)
    issue_payload = (
        collect_issue_view(github_repo, expected_issue)
        if expected_issue is not None
        else None
    )
    before_head = _require_string(before, "headRefOid")
    before_head_repository = _head_repository_name(before)
    prior_review_boundary = None
    if isinstance(review.get("prior_review"), dict):
        prior_review_boundary = collect_head_push_boundary(
            before_head_repository,
            _require_string(before, "headRefName"),
            before_head,
        )
    before_relation = relation_snapshot(before)
    before_paths = _changed_files(before)
    linked_issue = _linked_issue(before, expected_issue, issue_payload)
    collection_profile = _effective_collection_profile(
        profile,
        before_paths,
        linked_issue=linked_issue,
        repo=repo,
        config=config,
    )
    if config is not None and "verification_profiles" in config.workflow:
        profile_errors = validate_verification_profiles(config)
        if profile_errors:
            raise EvidenceError("; ".join(profile_errors))
    collect_hosted = collection_profile != "fastlane"
    if config is not None and "verification_profiles" in config.workflow:
        _default_profile, profiles = verification_profiles(config)
        collect_hosted = (
            profiles.get(collection_profile, {}).get(
                "requires_independent_review"
            )
            is True
        )
    before_hosted = (
        []
        if not collect_hosted
        else collect_hosted_findings(github_repo, pr_number, before_head)
    )

    after = collect_pr_view(github_repo, pr_number)
    if _require_string(after, "headRefOid") != before_head:
        raise EvidenceError(
            "PR head changed while collecting gate evidence; rerun collection"
        )
    if relation_snapshot(after) != before_relation:
        raise EvidenceError(
            "PR issue relation changed while collecting gate evidence; rerun collection"
        )
    if _changed_files(after) != before_paths:
        raise EvidenceError(
            "PR file set changed while collecting gate evidence; rerun collection"
        )
    after_head = _require_string(after, "headRefOid")
    if _head_repository_name(after) != before_head_repository:
        raise EvidenceError(
            "PR head repository changed while collecting gate evidence; "
            "rerun collection"
        )
    if prior_review_boundary is not None:
        after_boundary = collect_head_push_boundary(
            before_head_repository,
            _require_string(after, "headRefName"),
            after_head,
        )
        if after_boundary != prior_review_boundary:
            raise EvidenceError(
                "PR head push activity changed while collecting gate evidence; "
                "rerun collection"
            )
    after_hosted = (
        []
        if not collect_hosted
        else collect_hosted_findings(github_repo, pr_number, after_head)
    )
    if after_hosted != before_hosted:
        raise EvidenceError(
            "hosted review findings changed while collecting gate evidence; "
            "rerun collection"
        )
    return build_evidence(
        after,
        repository=github_repo,
        profile=profile,
        gate_invocation_id=gate_invocation_id,
        review=combine_review_findings(
            review,
            after_hosted,
            prior_review_boundary=prior_review_boundary,
        ),
        expected_issue=expected_issue,
        issue_payload=issue_payload,
        repo=repo,
        config=config,
        authorization=authorization,
        checks_unavailable=checks_unavailable,
        review_attestation=review_attestation,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect read-only compact GitHub PR evidence."
    )
    parser.add_argument("--github-repo", required=True, help="OWNER/REPO")
    parser.add_argument("--repo", default=".", help="Local repository checkout")
    parser.add_argument("--pr", required=True, type=parse_pr_number)
    parser.add_argument("--issue", type=parse_issue_number)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="standard")
    parser.add_argument("--gate-invocation-id", required=True)
    parser.add_argument("--review", required=True, help="Compact review JSON")
    parser.add_argument("--authorization", help="Current-invocation authorization JSON")
    parser.add_argument(
        "--review-attestation",
        help="Trusted current-invocation reviewer lane attestation JSON",
    )
    parser.add_argument(
        "--checks-unavailable",
        help="Trusted hosted-checks-unavailable declaration JSON",
    )
    parser.add_argument("--json", action="store_true", help="Retained for CLI symmetry")
    args = parser.parse_args()
    repo = resolve_path(Path(args.repo), label="repository")
    try:
        review_path = Path(args.review)
        if not review_path.is_absolute():
            review_path = repo / review_path
        authorization = None
        if args.authorization:
            auth_path = Path(args.authorization)
            if not auth_path.is_absolute():
                auth_path = repo / auth_path
            authorization = _load_json(auth_path, "authorization")
        checks_unavailable = None
        if args.checks_unavailable:
            unavailable_path = Path(args.checks_unavailable)
            if not unavailable_path.is_absolute():
                unavailable_path = repo / unavailable_path
            checks_unavailable = _load_json(
                unavailable_path,
                "checks-unavailable declaration",
            )
        review_attestation = None
        if args.review_attestation:
            attestation_path = Path(args.review_attestation)
            if not attestation_path.is_absolute():
                attestation_path = repo / attestation_path
            review_attestation = _load_json(
                attestation_path,
                "review attestation",
            )
        evidence = collect_evidence(
            args.github_repo,
            args.pr,
            profile=args.profile,
            gate_invocation_id=args.gate_invocation_id,
            review=_load_json(review_path, "review"),
            authorization=authorization,
            checks_unavailable=checks_unavailable,
            review_attestation=review_attestation,
            expected_issue=args.issue,
            repo=repo,
            config=load_pack(repo),
        )
    except (EvidenceError, SpecRailError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
