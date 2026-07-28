#!/usr/bin/env python3
"""Evaluate the compact, advisory SpecRail review contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rejection_items import (
    add_prior_rejection_argument,
    apply_prior_rejection,
    finalize_items,
    item_from_reason,
    items_from_legacy,
)


CONTRACT_VERSION = 3
PROFILES = {"fastlane", "standard", "heavy"}
DEFAULT_PROFILE_ROUND_CAPS = {"fastlane": 1, "standard": 2, "heavy": 2}
REVIEW_SOURCES = {"independent_lane", "self_review"}
REVIEW_MODES = {"full", "diff_only"}
VERDICTS = {"clean", "blocking", "non_blocking"}
SEVERITIES = {"P0", "P1", "P2", "P3"}
FINDING_STATUSES = {"unresolved", "resolved"}
FINDING_ORIGINS = {"local", "hosted"}
REVIEW_TOP_LEVEL_KEYS = {
    "artifact_id",
    "base_head_sha",
    "body",
    "contract_version",
    "diff_sha256",
    "findings",
    "head_sha",
    "mode",
    "pr",
    "prior_review",
    "profile",
    "repository",
    "review_source",
    "round",
    "verdict",
}
FINDING_KEYS = {
    "id",
    "introduced_by_diff",
    "line",
    "origin",
    "outdated",
    "path",
    "severity",
    "status",
    "summary",
}
LEGACY_REVIEW_FIELDS = {
    "comments",
    "content_binding_evidence",
    "content_binding_version",
    "content_bindings",
    "covered_categories",
    "finding_classifications",
    "gate_authorization",
    "gate_status",
    "human_final_review_required",
    "human_full_review_request",
    "prior_findings",
    "producer_identity",
    "review_completed_at",
    "review_execution",
    "review_mode",
    "review_round",
    "review_started_at",
    "reviewer_lane",
    "round_cap_escalation",
    "round_policy_version",
    "spec_alignment",
    "status",
    "tier_attestation",
    "tier_dispute",
}
FORBIDDEN_FINAL_AUTHORITY = {
    "approved for merge": re.compile(r"\bapproved\s+for\s+merge\b", re.IGNORECASE),
    "I approve this PR": re.compile(r"\bi\s+approve\s+this\s+pr\b", re.IGNORECASE),
    "merge now": re.compile(r"\bmerge\s+now\b", re.IGNORECASE),
    "ready to merge": re.compile(r"\bready\s+to\s+merge\b", re.IGNORECASE),
    "you can merge": re.compile(r"\byou\s+can\s+merge\b", re.IGNORECASE),
    "go ahead and merge": re.compile(
        r"\bgo\s+ahead\s+and\s+merge\b", re.IGNORECASE
    ),
    "looks good to merge": re.compile(
        r"\blooks\s+good\s+to\s+merge\b", re.IGNORECASE
    ),
    "safe to merge": re.compile(r"\bsafe\s+to\s+merge\b", re.IGNORECASE),
    "LGTM, merge": re.compile(r"\blgtm\b[^.\\n]{0,40}\bmerge\b", re.IGNORECASE),
    "ship it": re.compile(r"\bship\s+it\b", re.IGNORECASE),
    "中文授权合并": re.compile(
        r"(?:批准|同意|允许|准许|可以|可|立即)\s*(?:予以)?合并"
    ),
    "合并即可": re.compile(r"合并\s*即可"),
    "合并吧": re.compile(r"合并吧"),
}
HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>[0-9]+)(?:,[0-9]+)? "
    r"\+(?P<new_start>[0-9]+)(?:,[0-9]+)? @@"
)
SUMMARY_HEADING_RE = re.compile(r"^## Summary\s*$", re.MULTILINE)
VERDICT_HEADING_RE = re.compile(r"^## Verdict\s*$", re.MULTILINE)


@dataclass(frozen=True)
class DiffIndex:
    left: dict[str, set[int]]
    right: dict[str, set[int]]


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read review file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid review JSON {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("review JSON must be an object")
    return data


def _clean_diff_path(raw_path: str) -> str | None:
    path = raw_path.strip().split("\t", 1)[0]
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path or None


def _add_line(lines: dict[str, set[int]], path: str | None, line: int) -> None:
    if path is not None and line > 0:
        lines.setdefault(path, set()).add(line)


def parse_unified_diff(diff_text: str) -> DiffIndex:
    """Index old and new line numbers in a unified diff."""

    left: dict[str, set[int]] = {}
    right: dict[str, set[int]] = {}
    old_path: str | None = None
    new_path: str | None = None
    old_line = 0
    new_line = 0
    in_hunk = False
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            old_path = new_path = None
            in_hunk = False
            continue
        if not in_hunk and raw_line.startswith("--- "):
            old_path = _clean_diff_path(raw_line[4:])
            continue
        if not in_hunk and raw_line.startswith("+++ "):
            new_path = _clean_diff_path(raw_line[4:])
            continue
        hunk = HUNK_RE.match(raw_line)
        if hunk:
            if old_path is None and new_path is None:
                raise ValueError("diff hunk is missing file paths")
            old_line = int(hunk.group("old_start"))
            new_line = int(hunk.group("new_start"))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw_line.startswith(" "):
            _add_line(left, old_path, old_line)
            _add_line(right, new_path, new_line)
            old_line += 1
            new_line += 1
        elif raw_line.startswith("-"):
            _add_line(left, old_path, old_line)
            old_line += 1
        elif raw_line.startswith("+"):
            _add_line(right, new_path, new_line)
            new_line += 1
        elif not raw_line.startswith("\\"):
            raise ValueError(f"unsupported diff line inside hunk: {raw_line!r}")
    return DiffIndex(left=left, right=right)


def validate_exact_git_diff(
    repo: Path,
    base: object,
    head: object,
    diff_sha256: object,
    *,
    supplied_bytes: bytes | None = None,
) -> list[str]:
    """Verify an option-safe exact Git range and its digest."""

    if not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40}", value)
        for value in (base, head)
    ):
        return ["exact Git diff requires 40-character Git SHAs before execution"]
    if not isinstance(diff_sha256, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", diff_sha256
    ):
        return ["exact Git diff requires a 64-character diff_sha256 before execution"]
    try:
        process = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary", f"{base}..{head}", "--"],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return [f"cannot execute exact Git diff: {exc}"]
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        return [f"exact Git diff failed for {base}..{head}: {detail}"]
    reasons: list[str] = []
    if supplied_bytes is not None and supplied_bytes != process.stdout:
        reasons.append("provided diff bytes do not equal exact Git base_head_sha..head_sha output")
    if hashlib.sha256(process.stdout).hexdigest() != diff_sha256:
        reasons.append("diff_sha256 does not match exact Git base_head_sha..head_sha output")
    return reasons


def _find_forbidden_language(review: dict[str, Any]) -> list[str]:
    body = review.get("body")
    if not isinstance(body, str):
        return []
    return [
        f"body grants final approval or merge authority: {label!r}"
        for label, pattern in FORBIDDEN_FINAL_AUTHORITY.items()
        if pattern.search(body)
    ]


def _result(
    review: dict[str, Any],
    *,
    decision: str,
    reasons: list[str],
    missing: list[str],
    satisfied: list[str],
    blocking: list[str],
    follow_ups: list[str],
    outdated: list[str],
) -> dict[str, Any]:
    rejection_items = (
        []
        if decision == "allowed"
        else finalize_items(
            items_from_legacy(
                sorted(set(missing)),
                sorted(set(reasons)),
                missing_category="missing_evidence_field",
                reason_category="contract_violation",
            )
        )
    )
    return {
        "decision": decision,
        "verdict": review.get("verdict"),
        "comment_count": 0,
        "advisory_only": True,
        "reasons": sorted(set(reasons)),
        "satisfied": sorted(set(satisfied)),
        "missing": sorted(set(missing)),
        "rejection_items": rejection_items,
        "blocking_findings": sorted(set(blocking)),
        "follow_ups": sorted(set(follow_ups)),
        "outdated_hosted_findings": sorted(set(outdated)),
        "blocked_actions": ["final_approval", "merge"],
        "verification_commands": [
            "python3 checks/review_json_gate.py --repo . --review <review.json> --diff <patch>",
            "python3 checks/check_workflow.py --repo .",
        ],
    }


def evaluate_review_gate(
    review: dict[str, Any],
    diff_text: str,
    *,
    repo: Path | None = None,
    diff_bytes: bytes | None = None,
    verify_diff: bool = True,
    max_review_rounds: int | None = None,
    requires_independent_review: bool | None = None,
) -> dict[str, Any]:
    """Validate a v3 review artifact and return all failures in one result."""

    reasons: list[str] = []
    missing: list[str] = []
    satisfied: list[str] = []
    blocking: list[str] = []
    follow_ups: list[str] = []
    outdated: list[str] = []
    required = {
        "artifact_id",
        "base_head_sha",
        "body",
        "contract_version",
        "diff_sha256",
        "findings",
        "head_sha",
        "mode",
        "pr",
        "profile",
        "repository",
        "review_source",
        "round",
        "verdict",
    }
    missing.extend(key for key in sorted(required) if key not in review)
    for key in sorted(set(review) - REVIEW_TOP_LEVEL_KEYS):
        prefix = "unsupported legacy review field" if key in LEGACY_REVIEW_FIELDS else "unknown top-level field"
        reasons.append(f"{prefix}: {key}")

    for key in ("artifact_id", "repository"):
        if key in review and not _non_empty_string(review.get(key)):
            reasons.append(f"{key} must be a non-empty string")
    if "pr" in review and not _positive_int(review.get("pr")):
        reasons.append("pr must be a positive integer")
    if review.get("contract_version") != CONTRACT_VERSION:
        reasons.append(
            f"contract_version must be {CONTRACT_VERSION}; rebuild legacy review "
            "evidence from the current GitHub state"
        )
    if not isinstance(review.get("head_sha"), str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", str(review.get("head_sha", ""))
    ):
        reasons.append("head_sha must be a 40-character Git SHA")

    profile = review.get("profile")
    source = review.get("review_source")
    if profile not in PROFILES:
        reasons.append("profile must be fastlane, standard, or heavy")
    if source not in REVIEW_SOURCES:
        reasons.append("review_source must be independent_lane or self_review")
    independent_required = (
        requires_independent_review
        if isinstance(requires_independent_review, bool)
        else profile in {"standard", "heavy"}
    )
    if independent_required and source != "independent_lane":
        reasons.append(f"{profile} profile requires an independent_lane review")

    review_round = review.get("round")
    mode = review.get("mode")
    if not _positive_int(review_round):
        reasons.append("round must be a positive integer")
    if mode not in REVIEW_MODES:
        reasons.append("mode must be full or diff_only")
    if review_round == 1 and mode != "full":
        reasons.append("round 1 must use full mode")
    if review_round == 2 and mode != "diff_only":
        reasons.append("round 2 must use diff_only mode")
    prior_review = review.get("prior_review")
    if review_round == 1 and prior_review is not None:
        reasons.append("round 1 must not include prior_review")
    if review_round == 2:
        if prior_review is None:
            missing.append("prior_review")
        elif not isinstance(prior_review, dict):
            reasons.append("prior_review must be an object")
        elif "prior_review" in prior_review:
            reasons.append("prior_review must not contain another prior_review")
        else:
            expected_prior = {
                "repository": review.get("repository"),
                "pr": review.get("pr"),
                "profile": review.get("profile"),
                "review_source": review.get("review_source"),
                "head_sha": review.get("base_head_sha"),
                "round": 1,
                "mode": "full",
            }
            for field, expected_value in expected_prior.items():
                if prior_review.get(field) != expected_value:
                    reasons.append(
                        f"prior_review.{field} must equal {expected_value!r}"
                    )
            prior_result = evaluate_review_gate(
                prior_review,
                "",
                verify_diff=False,
                requires_independent_review=independent_required,
            )
            if verify_diff and repo is not None:
                reasons.extend(
                    "prior_review: " + reason
                    for reason in validate_exact_git_diff(
                        repo,
                        prior_review.get("base_head_sha"),
                        prior_review.get("head_sha"),
                        prior_review.get("diff_sha256"),
                    )
                )
            reasons.extend(
                f"prior_review: {reason}"
                for reason in prior_result["reasons"]
            )
            missing.extend(
                f"prior_review.{field}"
                for field in prior_result["missing"]
            )
            current_findings = review.get("findings")
            current_by_id = (
                {
                    str(finding.get("id")): finding
                    for finding in current_findings
                    if isinstance(finding, dict)
                    and _non_empty_string(finding.get("id"))
                }
                if isinstance(current_findings, list)
                else {}
            )
            prior_findings = {
                str(finding.get("id")): finding
                for finding in prior_review.get("findings", [])
                if isinstance(finding, dict)
                and _non_empty_string(finding.get("id"))
            }
            for finding_id in prior_result["blocking_findings"]:
                current_finding = current_by_id.get(finding_id)
                if current_finding is None:
                    reasons.append(
                        "prior unresolved P0/P1 finding must be carried into "
                        f"round 2: {finding_id}"
                    )
                    continue
                prior_finding = prior_findings[finding_id]
                for field in ("severity", "summary"):
                    if current_finding.get(field) != prior_finding.get(field):
                        reasons.append(
                            f"round 2 finding {finding_id} must preserve prior "
                            f"{field}"
                        )
                prior_origin = prior_finding.get("origin", "local")
                current_origin = current_finding.get("origin", "local")
                if current_origin != prior_origin:
                    reasons.append(
                        f"round 2 finding {finding_id} must preserve prior origin"
                    )
            if not prior_result["reasons"] and not prior_result["missing"]:
                satisfied.append("round 1 full-review evidence validated")

    supplied = diff_bytes if diff_bytes is not None else diff_text.encode("utf-8")
    if review_round in {1, 2}:
        base = review.get("base_head_sha")
        digest = review.get("diff_sha256")
        if not verify_diff:
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                reasons.append("diff_sha256 must be a 64-character SHA-256 digest")
            if not isinstance(base, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", base):
                reasons.append("base_head_sha must be a 40-character Git SHA")
        elif repo is not None and base is not None and digest is not None:
            reasons.extend(
                validate_exact_git_diff(
                    repo,
                    base,
                    review.get("head_sha"),
                    digest,
                    supplied_bytes=supplied,
                )
            )
        elif digest is not None:
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                reasons.append("diff_sha256 must be a 64-character SHA-256 digest")
            elif hashlib.sha256(supplied).hexdigest() != digest:
                reasons.append("diff_sha256 does not match the supplied diff")
            if not isinstance(base, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", base):
                reasons.append("base_head_sha must be a 40-character Git SHA")

    body = review.get("body")
    if not _non_empty_string(body):
        reasons.append("body must be a non-empty string")
    elif isinstance(body, str):
        for heading, pattern in (
            ("body includes ## Summary", SUMMARY_HEADING_RE),
            ("body includes ## Verdict", VERDICT_HEADING_RE),
        ):
            (satisfied if pattern.search(body) else missing).append(heading)
    reasons.extend(_find_forbidden_language(review))

    try:
        diff_index = parse_unified_diff(diff_text)
    except ValueError as exc:
        diff_index = DiffIndex(left={}, right={})
        reasons.append(str(exc))

    findings = review.get("findings")
    if not isinstance(findings, list):
        reasons.append("findings must be an array")
        findings = []
    seen_ids: set[str] = set()
    for index, finding in enumerate(findings, start=1):
        prefix = f"finding #{index}"
        if not isinstance(finding, dict):
            reasons.append(f"{prefix} must be an object")
            continue
        for key in sorted(set(finding) - FINDING_KEYS):
            reasons.append(f"{prefix} has unknown field: {key}")
        finding_id = finding.get("id")
        if not _non_empty_string(finding_id):
            reasons.append(f"{prefix} id must be a non-empty string")
            finding_id = f"finding-{index}"
        elif str(finding_id) in seen_ids:
            reasons.append(f"{prefix} id must be unique: {finding_id}")
        seen_ids.add(str(finding_id))
        if not _non_empty_string(finding.get("summary")):
            reasons.append(f"{prefix} summary must be a non-empty string")

        severity = finding.get("severity")
        status = finding.get("status")
        origin = finding.get("origin", "local")
        is_outdated = finding.get("outdated", False)
        if severity not in SEVERITIES:
            reasons.append(f"{prefix} severity must be P0, P1, P2, or P3")
        if status not in FINDING_STATUSES:
            reasons.append(f"{prefix} status must be unresolved or resolved")
        if origin not in FINDING_ORIGINS:
            reasons.append(f"{prefix} origin must be local or hosted")
        if not isinstance(is_outdated, bool):
            reasons.append(f"{prefix} outdated must be a boolean")
            is_outdated = False
        if is_outdated and origin != "hosted":
            reasons.append(f"{prefix} outdated is only valid for hosted findings")

        has_path, has_line = "path" in finding, "line" in finding
        if has_path != has_line:
            reasons.append(f"{prefix} path and line must be provided together")
        elif has_path and not is_outdated and verify_diff:
            path, line = finding.get("path"), finding.get("line")
            if not _non_empty_string(path) or not _positive_int(line):
                reasons.append(f"{prefix} path must be non-empty and line must be positive")
            elif (
                int(line) not in diff_index.left.get(str(path), set())
                and int(line) not in diff_index.right.get(str(path), set())
            ):
                reasons.append(f"{prefix} {path}:{line} is not present in the diff")

        if (
            review_round == 2
            and status == "unresolved"
            and severity in {"P0", "P1"}
            and not is_outdated
            and not isinstance(finding.get("introduced_by_diff"), bool)
        ):
            reasons.append(f"{prefix} round 2 P0/P1 must declare introduced_by_diff")
        if status != "unresolved":
            continue
        if is_outdated and origin == "hosted":
            outdated.append(str(finding_id))
        elif severity in {"P0", "P1"}:
            blocking.append(str(finding_id))
        elif severity in {"P2", "P3"}:
            follow_ups.append(str(finding_id))

    verdict = review.get("verdict")
    if verdict not in VERDICTS:
        reasons.append(
            "verdict must be clean, blocking, or non_blocking; "
            f"got {verdict!r}"
        )
    expected = "blocking" if blocking else "non_blocking" if follow_ups else "clean"
    if verdict in VERDICTS and verdict != expected:
        reasons.append(f"verdict {verdict!r} does not match current findings; expected {expected!r}")

    configured_round_cap = (
        max_review_rounds
        if _positive_int(max_review_rounds)
        else DEFAULT_PROFILE_ROUND_CAPS.get(str(profile), 2)
    )
    round_cap_exceeded = (
        _positive_int(review_round)
        and review_round > configured_round_cap
    )
    if reasons or missing or blocking:
        decision = "blocked"
    elif round_cap_exceeded:
        decision = "needs_human"
    else:
        decision = "allowed"
    if round_cap_exceeded:
        satisfied.append(
            f"review round cap {configured_round_cap} reached; human review required"
        )
    if not reasons and not missing:
        satisfied.append("compact review contract v3 valid")
    if follow_ups:
        satisfied.append("P2/P3 findings recorded as non-blocking follow-ups")
    if outdated:
        satisfied.append("outdated hosted findings treated as non-blocking")
    return _result(
        review,
        decision=decision,
        reasons=reasons,
        missing=missing,
        satisfied=satisfied,
        blocking=blocking,
        follow_ups=follow_ups,
        outdated=outdated,
    )


def print_review_gate_human(result: dict[str, Any]) -> None:
    print(f"decision: {result['decision']}")
    if result.get("verdict"):
        print(f"verdict: {result['verdict']}")
    print("advisory_only: true")
    for name in ("reasons", "missing"):
        if result[name]:
            print(f"{name}:")
            for item in result[name]:
                print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a SpecRail advisory review JSON artifact."
    )
    parser.add_argument("--repo", default=".", help="Workflow pack root")
    parser.add_argument("--review", required=True, help="Review artifact JSON file")
    parser.add_argument("--diff", required=True, help="Unified diff patch file")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    add_prior_rejection_argument(parser)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        review_path = Path(args.review)
        diff_path = Path(args.diff)
        review = _load_json(review_path if review_path.is_absolute() else repo / review_path)
        from specrail_lib import load_pack, verification_profiles

        _default_profile, profiles = verification_profiles(load_pack(repo))
        profile_policy = profiles.get(str(review.get("profile")), {})
        resolved_diff = diff_path if diff_path.is_absolute() else repo / diff_path
        diff_bytes = resolved_diff.read_bytes()
        result = evaluate_review_gate(
            review,
            diff_bytes.decode("utf-8"),
            repo=repo,
            diff_bytes=diff_bytes,
            max_review_rounds=profile_policy.get("max_review_rounds"),
            requires_independent_review=profile_policy.get(
                "requires_independent_review"
            ),
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        result = _result(
            {},
            decision="blocked",
            reasons=[str(exc)],
            missing=[],
            satisfied=[],
            blocking=[],
            follow_ups=[],
            outdated=[],
        )
        result["rejection_items"] = finalize_items(
            [item_from_reason(str(exc), "config_error")]
        )
    result = apply_prior_rejection(
        result,
        args.prior_rejection,
        blocked_actions=["final_approval", "merge"],
    )
    print(
        json.dumps(result, indent=2, sort_keys=True)
        if args.json
        else "",
        end="\n" if args.json else "",
    )
    if not args.json:
        print_review_gate_human(result)
    return 0 if result["decision"] == "allowed" else 1


if __name__ == "__main__":
    sys.exit(main())
