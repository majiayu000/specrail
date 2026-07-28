"""Shared errors for read-only GitHub evidence adapters."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from schema_validation import (
    InstanceMismatch,
    SchemaDefinitionError,
    load_json_schema,
    validate_instance,
)
from rejection_items import finalize_items, item_from_reason


STATUS_CONTEXT_STATES = {"SUCCESS", "FAILURE", "ERROR", "PENDING", "EXPECTED"}
OUTCOME_LABELS = {"duplicate", "abandoned", "security_private"}


class EvidenceError(ValueError):
    """Raised when GitHub evidence cannot be collected or normalized."""


def _schema_mismatch_errors(
    schema: dict[str, Any],
    value: Any,
    path: str,
) -> list[str]:
    try:
        validate_instance(schema, value, path)
    except SchemaDefinitionError:
        raise
    except InstanceMismatch as exc:
        fallback = str(exc)
    else:
        return []

    errors: list[str] = []
    properties = schema.get("properties", {})
    if isinstance(value, dict) and isinstance(properties, dict):
        errors.extend(
            f"{path}.{field}: missing required field"
            for field in schema.get("required", [])
            if field not in value
        )
        additional = schema.get("additionalProperties", True)
        extra_fields = sorted(set(value) - set(properties))
        if additional is False:
            errors.extend(
                f"{path}.{field}: additional property is not allowed"
                for field in extra_fields
            )
        for field, child in properties.items():
            if field in value and isinstance(child, dict):
                errors.extend(
                    _schema_mismatch_errors(
                        child,
                        value[field],
                        f"{path}.{field}",
                    )
                )
        if isinstance(additional, dict):
            for field in extra_fields:
                errors.extend(
                    _schema_mismatch_errors(
                        additional,
                        value[field],
                        f"{path}.{field}",
                    )
                )
    items = schema.get("items")
    if isinstance(value, list) and isinstance(items, dict):
        for index, item in enumerate(value):
            errors.extend(
                _schema_mismatch_errors(items, item, f"{path}[{index}]")
            )
    return list(dict.fromkeys(errors or [fallback]))


def _issue_schema_errors(
    schema: dict[str, Any],
    evidence: dict[str, Any],
) -> list[str]:
    return _schema_mismatch_errors(schema, evidence, "issue evidence")


def json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def json_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be a JSON array")
    return value


def valid_testable_plan(value: Any) -> bool:
    """Return whether compact Issue-body plan evidence is complete."""
    if not isinstance(value, dict):
        return False
    items = value.get("items")
    digest = value.get("body_sha256")
    return (
        value.get("source") == "issue_body_checklist"
        and isinstance(items, list)
        and bool(items)
        and all(isinstance(item, str) and bool(item.strip()) for item in items)
        and isinstance(digest, str)
        and len(digest) == 64
        and set(digest.lower()) <= set("0123456789abcdef")
    )


def issue_route_evidence_errors(
    repo: Path,
    evidence: dict[str, Any],
    issue: int | None,
    github_repo: str | None,
    *,
    require_collector: bool = False,
    cli_state: str | None = None,
) -> list[str]:
    """Validate collector-shaped Issue evidence and bind it to this invocation."""
    if not require_collector and "issue" not in evidence and "repository" not in evidence:
        return []
    errors: list[str] = []
    try:
        schema = load_json_schema(repo / "schemas" / "issue_evidence.schema.json")
        errors.extend(_issue_schema_errors(schema, evidence))
    except SchemaDefinitionError as exc:
        errors.append(str(exc))
    if evidence.get("issue") != issue:
        errors.append(
            f"issue evidence number must match --issue {issue}; "
            f"got {evidence.get('issue')!r}"
        )
    repository = evidence.get("repository")
    if not github_repo:
        errors.append("collector Issue evidence requires --github-repo OWNER/REPO")
    elif repository != github_repo:
        errors.append(
            f"issue evidence repository must match --github-repo {github_repo}; "
            f"got {repository!r}"
        )
    if cli_state is not None and cli_state != evidence.get("state"):
        errors.append(
            f"--state {cli_state} conflicts with collector state "
            f"{evidence.get('state')!r}"
        )
    labels = evidence.get("labels")
    if isinstance(labels, list):
        label_set = {label for label in labels if isinstance(label, str)}
        state = evidence.get("state")
        trusted = evidence.get("state_trusted")
        source = evidence.get("state_source")
        if source == "label" and trusted is True and state not in label_set:
            errors.append("trusted label state must be present in issue evidence labels")
        if source != "label" and trusted is True:
            errors.append("state_trusted=true requires state_source=label")
        expected_outcomes = sorted(label_set & OUTCOME_LABELS)
        if evidence.get("outcomes") != expected_outcomes:
            errors.append("issue evidence outcomes must exactly match outcome labels")
    plan = evidence.get("testable_plan")
    if isinstance(plan, dict) and plan.get("body_sha256") != evidence.get("body_sha256"):
        errors.append("testable_plan.body_sha256 must match issue evidence body_sha256")
    return errors


def valid_security_evidence(
    repo: Path,
    approved_revision: Any,
    expected_spec_paths: list[str],
) -> bool:
    """Bind the current heavy spec packet to an approved immutable revision."""
    if (
        not isinstance(approved_revision, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40}", approved_revision)
        or not expected_spec_paths
    ):
        return False
    ancestry = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", approved_revision, "HEAD"],
        check=False,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        return False
    for path in expected_spec_paths:
        approved = subprocess.run(
            ["git", "-C", str(repo), "show", f"{approved_revision}:{path}"],
            check=False,
            capture_output=True,
        )
        try:
            current = (repo / path).read_bytes()
        except OSError:
            return False
        if approved.returncode != 0 or approved.stdout != current:
            return False
    return True


def blocked_route_result(
    route: str,
    current_state: str | None,
    args: Any,
    reasons: list[str],
    item_category: str = "invalid_state",
) -> dict[str, Any]:
    """Build the compact fail-closed route result used by early exits."""
    return {
        "decision": "blocked",
        "route": route,
        "profile": getattr(args, "profile", None) or "standard",
        "mode": args.mode,
        "current_state": current_state,
        "issue": args.issue,
        "pr": args.pr,
        "reasons": reasons,
        "satisfied": [],
        "missing": [],
        "rejection_items": finalize_items(
            item_from_reason(reason, item_category) for reason in reasons
        ),
        "required_artifacts": [],
        "human_gates": [],
        "allowed_actions": [],
        "blocked_actions": [route],
        "verification_commands": ["python3 checks/check_workflow.py --repo ."],
    }


def _rollup_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        return value["nodes"]
    raise EvidenceError("statusCheckRollup must be a list or nodes object")


def _normalize_status_context(item: dict[str, Any]) -> tuple[str, str]:
    state = str(item.get("state") or "").upper()
    if state not in STATUS_CONTEXT_STATES:
        return "", ""
    if state == "SUCCESS":
        return "COMPLETED", "SUCCESS"
    if state in {"PENDING", "EXPECTED"}:
        return "IN_PROGRESS", ""
    return "COMPLETED", state


def normalize_checks(value: Any) -> list[dict[str, Any]]:
    """Normalize the current GitHub check rollup."""
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(_rollup_items(value), start=1):
        if not isinstance(item, dict):
            raise EvidenceError(f"statusCheckRollup item #{index} must be an object")
        name = str(
            item.get("name")
            or item.get("context")
            or item.get("workflowName")
            or f"check #{index}"
        )
        status = str(item.get("status") or "").upper()
        conclusion = str(item.get("conclusion") or "").upper()
        if not status and not conclusion:
            status, conclusion = _normalize_status_context(item)
        if not status and conclusion == "SUCCESS":
            status = "COMPLETED"
        check = {"name": name, "status": status, "conclusion": conclusion}
        url = item.get("detailsUrl") or item.get("targetUrl")
        if isinstance(url, str) and url.strip():
            check["url"] = url.strip()
        checks.append(check)
    return checks


def normalize_reviews(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise EvidenceError("reviews must be a list")
    latest_by_author: dict[str, dict[str, str]] = {}
    author_order: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise EvidenceError(f"review item #{index} must be an object")
        state = str(item.get("state") or "").upper()
        if not state:
            continue
        raw_author = item.get("author")
        if isinstance(raw_author, dict):
            raw_author = raw_author.get("login")
        author = (
            raw_author.strip()
            if isinstance(raw_author, str) and raw_author.strip()
            else f"review #{index}"
        )
        if author not in latest_by_author:
            author_order.append(author)
        latest_by_author[author] = {"author": author, "state": state}
    return [latest_by_author[author] for author in author_order]


HOSTED_SEVERITY_RE = re.compile(
    r"(?i)(?:^|[^A-Z0-9])\[?(P[0-3])\]?(?=$|[^A-Z0-9])"
)
HOSTED_REVIEW_QUERY = """
query SpecRailHostedFindings(
  $owner: String!, $name: String!, $number: Int!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          path
          subjectType
          isResolved
          isOutdated
          comments(first: 1) {
            nodes {
              body
              createdAt
              lastEditedAt
              line
              originalLine
              path
              originalCommit { oid }
              pullRequestReview {
                id
                submittedAt
                commit { oid }
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


def _review_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a non-empty string")
    return value.strip()


def _review_timestamp(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise EvidenceError(f"{label} must be a GitHub timestamp")
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{label} must be a GitHub timestamp") from exc
    if value.tzinfo is None:
        raise EvidenceError(f"{label} must include a timezone")
    return value


def collect_head_push_boundary(
    run_github: Callable[[list[str]], Any],
    github_repo: str,
    head_ref: str,
    head_sha: str,
) -> str:
    """Return GitHub's exact-ref/exact-SHA server timestamp for the current head."""
    owner, name = github_repo.split("/", 1)
    expected_ref = f"refs/heads/{head_ref}"
    payload = run_github(
        [
            "api",
            "--method",
            "GET",
            "-H",
            "X-GitHub-Api-Version: 2026-03-10",
            f"repos/{owner}/{name}/activity",
            "-F",
            f"ref={head_ref}",
            "-F",
            "per_page=100",
        ]
    )
    if not isinstance(payload, list):
        raise EvidenceError("repository activity response must be an array")
    matches = [
        item
        for item in payload
        if isinstance(item, dict)
        and item.get("ref") == expected_ref
        and item.get("after") == head_sha
        and item.get("activity_type")
        in {"push", "force_push", "branch_creation"}
    ]
    if len(matches) != 1:
        raise EvidenceError(
            "current PR head requires exactly one trusted repository push activity"
        )
    timestamp = _review_string(matches[0], "timestamp")
    _review_timestamp(timestamp, "repository activity timestamp")
    return timestamp


def _hosted_thread_finding(thread: dict[str, Any]) -> dict[str, Any] | None:
    thread_id = _review_string(thread, "id")
    subject_type = _review_string(thread, "subjectType")
    if subject_type not in {"FILE", "LINE"}:
        raise EvidenceError(
            f"hosted review thread {thread_id} subjectType is malformed"
        )
    path = _review_string(thread, "path")
    if (
        path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise EvidenceError(f"hosted review thread {thread_id} path is malformed")
    resolved = thread.get("isResolved")
    outdated = thread.get("isOutdated")
    comments = thread.get("comments")
    if not isinstance(resolved, bool) or not isinstance(outdated, bool):
        raise EvidenceError(f"hosted review thread {thread_id} requires resolution state")
    if not isinstance(comments, dict) or not isinstance(comments.get("nodes"), list):
        raise EvidenceError(
            f"hosted review thread {thread_id} requires root comment evidence"
        )
    nodes = comments["nodes"]
    if not nodes or not isinstance(nodes[0], dict):
        raise EvidenceError(f"hosted review thread {thread_id} requires a root comment")
    root = nodes[0]
    body = root.get("body")
    if not isinstance(body, str):
        raise EvidenceError(
            f"hosted review thread {thread_id} root comment requires body"
        )
    severity = HOSTED_SEVERITY_RE.search(body.strip())
    if severity is None:
        return None
    created_at = _review_string(root, "createdAt")
    _review_timestamp(created_at, f"hosted review thread {thread_id} createdAt")
    if "lastEditedAt" not in root:
        raise EvidenceError(
            f"hosted review thread {thread_id} lastEditedAt is required"
        )
    last_edited_at = root.get("lastEditedAt")
    if last_edited_at is not None:
        _review_timestamp(
            last_edited_at,
            f"hosted review thread {thread_id} lastEditedAt",
        )
    summary = next((line.strip() for line in body.splitlines() if line.strip()), "")
    finding: dict[str, Any] = {
        "id": f"hosted:{thread_id}",
        "severity": severity.group(1).upper(),
        "status": "resolved" if resolved else "unresolved",
        "summary": summary[:240],
        "origin": "hosted",
        "outdated": outdated,
        "fix_paths": [path],
        "_created_at": created_at,
        "_last_edited_at": last_edited_at,
        "_subject_type": subject_type,
    }
    root_path = root.get("path")
    if root_path is not None and root_path != path:
        raise EvidenceError(
            f"hosted review thread {thread_id} root path does not match thread path"
        )
    if subject_type == "LINE":
        line = root.get("originalLine")
        if not isinstance(line, int) or isinstance(line, bool) or line <= 0:
            line = root.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line <= 0:
            raise EvidenceError(
                f"hosted line review thread {thread_id} requires a positive line"
            )
        finding.update({"path": path, "line": line})
    original = root.get("originalCommit")
    if original is not None:
        oid = original.get("oid") if isinstance(original, dict) else None
        if not isinstance(oid, str) or re.fullmatch(r"[0-9a-fA-F]{40}", oid) is None:
            raise EvidenceError(
                f"hosted review thread {thread_id} original commit is malformed"
            )
        finding["_original_head_sha"] = oid
    review = root.get("pullRequestReview")
    if review is not None:
        if not isinstance(review, dict):
            raise EvidenceError(f"hosted review thread {thread_id} review is malformed")
        submitted_at = _review_string(review, "submittedAt")
        _review_timestamp(submitted_at, f"hosted review thread {thread_id} submittedAt")
        commit = review.get("commit")
        oid = commit.get("oid") if isinstance(commit, dict) else None
        if not isinstance(oid, str) or re.fullmatch(r"[0-9a-fA-F]{40}", oid) is None:
            raise EvidenceError(
                f"hosted review thread {thread_id} review commit is malformed"
            )
        finding.update(
            {
                "_review_id": _review_string(review, "id"),
                "_review_submitted_at": submitted_at,
                "_review_head_sha": oid,
            }
        )
    return finding


def collect_hosted_findings(
    run_github: Callable[[list[str]], Any],
    github_repo: str,
    pr_number: int,
    expected_head: str,
) -> list[dict[str, Any]]:
    """Collect hosted findings and their server-owned historical provenance."""
    owner, name = github_repo.split("/", 1)
    cursor: str | None = None
    seen_cursors: set[str] = set()
    findings: list[dict[str, Any]] = []
    for _page in range(1, 1001):
        args = [
            "api", "graphql",
            "-F", f"owner={owner}",
            "-F", f"name={name}",
            "-F", f"number={pr_number}",
            "-f", f"query={HOSTED_REVIEW_QUERY}",
        ]
        if cursor is not None:
            args[2:2] = ["-F", f"cursor={cursor}"]
        try:
            pull_request = run_github(args)["data"]["repository"]["pullRequest"]
            threads = pull_request["reviewThreads"]
        except (KeyError, TypeError) as exc:
            raise EvidenceError("hosted review query returned malformed evidence") from exc
        if (
            not isinstance(pull_request, dict)
            or not isinstance(threads, dict)
            or _review_string(pull_request, "headRefOid") != expected_head
        ):
            raise EvidenceError("PR head changed while collecting hosted findings")
        nodes = threads.get("nodes")
        page_info = threads.get("pageInfo")
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            raise EvidenceError("hosted review thread page is malformed")
        for index, thread in enumerate(nodes, start=1):
            if not isinstance(thread, dict):
                raise EvidenceError(f"hosted review thread #{index} must be an object")
            finding = _hosted_thread_finding(thread)
            if finding is not None:
                findings.append(finding)
        if page_info.get("hasNextPage") is False:
            break
        if page_info.get("hasNextPage") is not True:
            raise EvidenceError("hosted review pageInfo.hasNextPage must be boolean")
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            raise EvidenceError("hosted review pagination requires endCursor")
        cursor = next_cursor.strip()
        if cursor in seen_cursors:
            raise EvidenceError("hosted review pagination cursor did not advance")
        seen_cursors.add(cursor)
    else:
        raise EvidenceError("hosted review pagination exceeded 1000 pages")
    identifiers = [str(finding["id"]) for finding in findings]
    if len(set(identifiers)) != len(identifiers):
        raise EvidenceError("hosted review findings contain duplicate thread ids")
    return sorted(findings, key=lambda item: str(item["id"]))


def _trusted_hosted_history(
    artifact: dict[str, Any],
    finding: dict[str, Any] | None,
    boundary_raw: str | None,
) -> bool:
    if finding is None or boundary_raw is None:
        return False
    path = finding.get("path")
    subject_type = finding.get("_subject_type")
    scope_valid = (
        subject_type == "FILE"
        and "path" not in finding
        and "line" not in finding
        and isinstance(finding.get("fix_paths"), list)
        and len(finding["fix_paths"]) == 1
        and isinstance(finding["fix_paths"][0], str)
    ) or (
        subject_type == "LINE"
        and isinstance(path, str)
        and finding.get("fix_paths") == [path]
        and isinstance(finding.get("line"), int)
        and not isinstance(finding["line"], bool)
        and finding["line"] > 0
    )
    if (
        finding.get("severity") not in {"P0", "P1", "P2", "P3"}
        or not isinstance(finding.get("summary"), str)
        or not finding["summary"].strip()
        or not scope_valid
        or not isinstance(finding.get("_review_id"), str)
        or not finding["_review_id"].strip()
    ):
        return False
    try:
        created_at = _review_timestamp(finding.get("_created_at"), "createdAt")
        submitted_at = _review_timestamp(
            finding.get("_review_submitted_at"),
            "submittedAt",
        )
        boundary = _review_timestamp(boundary_raw, "prior review boundary")
        last_edited_at = finding.get("_last_edited_at")
        edited_at = (
            None
            if last_edited_at is None
            else _review_timestamp(last_edited_at, "lastEditedAt")
        )
    except EvidenceError:
        return False
    authenticated = (
        finding.get("_original_head_sha") == artifact.get("head_sha")
        and finding.get("_review_head_sha") == artifact.get("head_sha")
        and created_at < boundary
        and submitted_at < boundary
        and (edited_at is None or edited_at < boundary)
    )
    if not authenticated:
        return False
    if finding.get("severity") in {"P0", "P1"} and (
        finding.get("status") != "unresolved"
        or finding.get("outdated") is not True
    ):
        raise EvidenceError(
            f"hosted prior blocker {finding.get('id')} has no verifiable historical "
            "resolution state; start a new current-head full review (round 1)"
        )
    return True


def combine_review_findings(
    review: dict[str, Any],
    hosted_findings: list[dict[str, Any]],
    *,
    prior_review_boundary: str | None = None,
) -> dict[str, Any]:
    """Reconcile local findings with current and authenticated historical threads."""
    hosted_by_id: dict[str, dict[str, Any]] = {}
    for finding in hosted_findings:
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not finding_id:
            raise EvidenceError("hosted review finding id must be a non-empty string")
        if finding_id in hosted_by_id:
            raise EvidenceError("hosted review findings contain duplicate thread ids")
        hosted_by_id[finding_id] = dict(finding)

    def normalize_artifact(
        artifact: dict[str, Any],
        *,
        trusted_history: bool = False,
    ) -> dict[str, Any]:
        local = artifact.get("findings")
        if not isinstance(local, list):
            raise EvidenceError("review.findings must be an array")
        normalized = dict(artifact)
        normalized["findings"] = []
        for finding in local:
            if not isinstance(finding, dict):
                normalized["findings"].append(finding)
                continue
            excluded = {"origin", "outdated", "subject_type"}
            if trusted_history:
                excluded.update(
                    {
                        "severity",
                        "status",
                        "summary",
                        "fix_paths",
                        "path",
                        "line",
                        "introduced_by_diff",
                    }
                )
            sanitized = {
                key: value
                for key, value in finding.items()
                if not key.startswith("_") and key not in excluded
            }
            canonical = hosted_by_id.get(str(sanitized.get("id")))
            if trusted_history and _trusted_hosted_history(
                artifact,
                canonical,
                prior_review_boundary,
            ):
                assert canonical is not None
                sanitized.update(
                    {
                        key: value
                        for key, value in canonical.items()
                        if not key.startswith("_")
                    }
                )
                sanitized.update(
                    {
                        "status": "unresolved",
                        "origin": "hosted",
                        "outdated": False,
                    }
                )
            normalized["findings"].append(sanitized)
        prior = artifact.get("prior_review")
        if isinstance(prior, dict):
            normalized["prior_review"] = normalize_artifact(
                prior,
                trusted_history=True,
            )
        return normalized

    combined = normalize_artifact(review)
    local_findings = combined["findings"]
    merged: list[Any] = []
    matched: set[str] = set()
    for finding in local_findings:
        if not isinstance(finding, dict):
            merged.append(finding)
            continue
        canonical = hosted_by_id.get(str(finding.get("id")))
        if canonical is None:
            merged.append(finding)
            continue
        merged.append(
            {
                **finding,
                **{
                    key: value
                    for key, value in canonical.items()
                    if not key.startswith("_")
                },
            }
        )
        matched.add(str(finding.get("id")))
    merged.extend(
        {key: value for key, value in finding.items() if not key.startswith("_")}
        for finding_id, finding in hosted_by_id.items()
        if finding_id not in matched
    )
    if review.get("round") == 2:
        prior = combined.get("prior_review")
        prior_ids = (
            {
                str(finding.get("id"))
                for finding in prior.get("findings", [])
                if isinstance(finding, dict)
                and finding.get("origin") == "hosted"
            }
            if isinstance(prior, dict)
            else set()
        )
        merged = [
            {
                **finding,
                **(
                    {"introduced_by_diff": finding.get("id") not in prior_ids}
                    if finding.get("origin") == "hosted"
                    and finding.get("severity") in {"P0", "P1"}
                    else {}
                ),
            }
            for finding in merged
        ]
    combined["findings"] = merged
    unresolved = [
        finding
        for finding in merged
        if isinstance(finding, dict)
        and finding.get("status") == "unresolved"
        and not finding.get("outdated", False)
    ]
    if any(finding.get("severity") in {"P0", "P1"} for finding in unresolved):
        combined["verdict"] = "blocking"
    elif any(finding.get("severity") in {"P2", "P3"} for finding in unresolved):
        combined["verdict"] = "non_blocking"
    else:
        combined["verdict"] = "clean"
    return combined
