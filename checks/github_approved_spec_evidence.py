"""Collect maintainer-controlled approved-spec label evidence from GitHub."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

from github_evidence_common import EvidenceError, json_array, json_object
from spec_revision_evidence import spec_artifacts_sha256_from_hashes
from specrail_lib import SpecRailError


APPROVAL_QUERY = """
query SpecRailApprovalLabels(
  $owner: String!, $name: String!, $number: Int!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name target { oid } }
    issue(number: $number) {
      state
      labels(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { name }
      }
    }
  }
}
""".strip()

DEFAULT_BASE_QUERY = """
query SpecRailDefaultBase($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name target { oid } }
  }
}
""".strip()

APPROVAL_TIMELINE_QUERY = """
query SpecRailApprovalTimeline(
  $owner: String!, $name: String!, $number: Int!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name target { oid } }
    issue(number: $number) {
      state
      timelineItems(first: 100, after: $cursor, itemTypes: [LABELED_EVENT]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          ... on LabeledEvent {
            createdAt
            actor { login }
            label { name }
          }
        }
      }
    }
  }
}
""".strip()

SPEC_REVISION_LABELS_QUERY = """
query SpecRailSpecRevisionLabels(
  $owner: String!, $name: String!, $issue: Int!, $pr: Int!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    issue(number: $issue) {
      state
      labels(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id name }
      }
    }
    pullRequest(number: $pr) { headRefOid }
  }
}
""".strip()

SPEC_REVISION_TIMELINE_QUERY = """
query SpecRailSpecRevisionTimeline(
  $owner: String!, $name: String!, $issue: Int!, $pr: Int!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    issue(number: $issue) {
      state
      timelineItems(first: 100, after: $cursor, itemTypes: [LABELED_EVENT]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          ... on LabeledEvent {
            id createdAt actor { login } label { name }
          }
        }
      }
    }
    pullRequest(number: $pr) { headRefOid }
  }
}
""".strip()

SPEC_REVISION_REVIEWS_QUERY = """
query SpecRailSpecRevisionReviews(
  $owner: String!, $name: String!, $issue: Int!, $pr: Int!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    issue(number: $issue) { state }
    pullRequest(number: $pr) {
      headRefOid
      reviews(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id state submittedAt url author { login } commit { oid }
        }
      }
    }
  }
}
""".strip()

SPEC_LIFECYCLE_LABELS = {"spec_pr_open", "spec_review", "spec_approved"}
MAINTAINER_PERMISSIONS = {"admin", "maintain", "write"}
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def collect_default_base_identity(
    github_repo: str,
    run_json: Callable[[list[str]], Any],
) -> tuple[str, str]:
    owner, name = github_repo.split("/", 1)
    payload = json_object(
        run_json(
            [
                "api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
                "-f", f"query={DEFAULT_BASE_QUERY}",
            ]
        ),
        "default-base GraphQL response",
    )
    try:
        repository = json_object(payload["data"]["repository"], "repository")
        default_branch_ref = json_object(
            repository["defaultBranchRef"], "defaultBranchRef"
        )
        default_branch = default_branch_ref["name"]
        default_base_sha = json_object(
            default_branch_ref["target"], "defaultBranchRef.target"
        )["oid"]
    except (KeyError, TypeError) as exc:
        raise EvidenceError("default-base query returned malformed evidence") from exc
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise EvidenceError("default-base query lacks a trusted default branch")
    if not isinstance(default_base_sha, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", default_base_sha
    ):
        raise EvidenceError("default-base query lacks a trusted default base SHA")
    return default_branch.strip(), default_base_sha.lower()


def collect_approval_metadata(
    github_repo: str,
    issue: int,
    run_json: Callable[[list[str]], Any],
    *,
    spec_source_commits: dict[str, str] | None = None,
    spec_source_commits_provider: Callable[[str, str], dict[str, str]] | None = None,
) -> dict[str, Any]:
    if spec_source_commits is not None and spec_source_commits_provider is not None:
        raise EvidenceError(
            "provide spec_source_commits or spec_source_commits_provider, not both"
        )
    owner, name = github_repo.split("/", 1)
    identity: tuple[str, str, str] | None = None

    def collect_connection(query: str, key: str) -> list[Any]:
        nonlocal identity
        cursor: str | None = None
        seen_cursors: set[str] = set()
        collected: list[Any] = []
        for _page in range(1000):
            args = [
                "api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
                "-F", f"number={issue}", "-f", f"query={query}",
            ]
            if cursor is not None:
                args[2:2] = ["-F", f"cursor={cursor}"]
            payload = json_object(run_json(args), "approved-spec GraphQL response")
            try:
                repository = json_object(payload["data"]["repository"], "repository")
                issue_data = json_object(repository["issue"], "issue")
                default_branch_ref = json_object(
                    repository["defaultBranchRef"], "defaultBranchRef"
                )
                default_branch = default_branch_ref["name"]
                default_base_sha = json_object(
                    default_branch_ref["target"], "defaultBranchRef.target"
                )["oid"]
                connection = json_object(issue_data[key], key)
                nodes = json_array(connection["nodes"], f"{key}.nodes")
                page_info = json_object(connection["pageInfo"], f"{key}.pageInfo")
            except (KeyError, TypeError) as exc:
                raise EvidenceError("approved-spec query returned malformed issue evidence") from exc
            if not isinstance(default_branch, str) or not default_branch.strip():
                raise EvidenceError("approved-spec query lacks a trusted default branch")
            if not isinstance(default_base_sha, str) or not re.fullmatch(
                r"[0-9a-fA-F]{40}", default_base_sha
            ):
                raise EvidenceError("approved-spec query lacks a trusted default base SHA")
            page_identity = (
                default_branch.strip(), default_base_sha.lower(),
                str(issue_data.get("state")),
            )
            if identity is None:
                identity = page_identity
            elif identity != page_identity:
                raise EvidenceError("approved-spec issue evidence drifted during pagination")
            collected.extend(nodes)
            has_next = page_info.get("hasNextPage")
            end_cursor = page_info.get("endCursor")
            if not isinstance(has_next, bool):
                raise EvidenceError(f"approved-spec {key} pageInfo is incomplete")
            if not has_next:
                return collected
            if not isinstance(end_cursor, str) or not end_cursor.strip() or end_cursor in seen_cursors:
                raise EvidenceError(f"approved-spec {key} pagination cursor is invalid")
            seen_cursors.add(end_cursor)
            cursor = end_cursor
        raise EvidenceError(f"approved-spec {key} pagination exceeded 1000 pages")

    labels = collect_connection(APPROVAL_QUERY, "labels")
    events = collect_connection(APPROVAL_TIMELINE_QUERY, "timelineItems")
    assert identity is not None
    default_branch, default_base_sha, issue_state = identity
    if issue_state != "OPEN":
        raise EvidenceError("approved-spec issue must remain OPEN")
    current_labels = {
        item.get("name") for item in labels
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if "ready_to_implement" not in current_labels:
        raise EvidenceError(
            "approved spec requires current ready_to_implement maintainer label"
        )
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        label = event.get("label")
        if not isinstance(label, dict) or label.get("name") != "ready_to_implement":
            continue
        created_at = event.get("createdAt")
        if not isinstance(created_at, str) or not created_at.strip():
            raise EvidenceError(
                "ready_to_implement label lacks maintainer actor/timestamp evidence"
            )
        try:
            created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceError(
                "ready_to_implement label timestamp is invalid"
            ) from exc
        if created_time.tzinfo is None:
            raise EvidenceError(
                "ready_to_implement label timestamp must include timezone"
            )
        candidates.append((created_time, event))
    if not candidates:
        raise EvidenceError(
            "ready_to_implement label lacks maintainer actor/timestamp evidence"
        )
    _approved_time, latest_event = max(candidates, key=lambda item: item[0])
    actor = latest_event.get("actor")
    maintainer_actor = actor.get("login") if isinstance(actor, dict) else None
    approved_at = latest_event["createdAt"].strip()
    if not isinstance(maintainer_actor, str) or not maintainer_actor.strip():
        raise EvidenceError(
            "ready_to_implement label lacks maintainer actor/timestamp evidence"
        )
    maintainer_actor = maintainer_actor.strip()
    result: dict[str, Any] = {
        "approved_at": approved_at,
        "maintainer_actor": maintainer_actor,
        "state_source": "label",
        "state_trusted": True,
        "default_base_ref": default_branch,
        "default_base_sha": default_base_sha,
    }
    if spec_source_commits_provider is not None:
        spec_source_commits = spec_source_commits_provider(
            default_branch, default_base_sha
        )
    if spec_source_commits is None:
        return result
    try:
        approved_time = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("ready_to_implement label timestamp is invalid") from exc
    if approved_time.tzinfo is None:
        raise EvidenceError("ready_to_implement label timestamp must include timezone")
    revisions: dict[str, Any] = {}
    for path, source_commit in spec_source_commits.items():
        if not re.fullmatch(r"[0-9a-fA-F]{40}", source_commit):
            raise EvidenceError(f"approved spec source commit is invalid: {path}")
        pulls = json_array(run_json(
            [
                "api", "--method", "GET",
                f"repos/{owner}/{name}/commits/{source_commit}/pulls",
            ]
        ), f"associated PR response for {path}")
        candidates: list[dict[str, Any]] = []
        for pull in pulls:
            if not isinstance(pull, dict):
                continue
            base = pull.get("base")
            merged_at = pull.get("merged_at")
            merge_commit = pull.get("merge_commit_sha")
            number = pull.get("number")
            if not isinstance(base, dict) or base.get("ref") != default_branch:
                continue
            if not isinstance(merged_at, str) or not isinstance(merge_commit, str):
                continue
            if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                continue
            try:
                merged_time = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if merged_time.tzinfo is None or merged_time > approved_time:
                continue
            if not re.fullmatch(r"[0-9a-fA-F]{40}", merge_commit):
                continue
            candidates.append(pull)
        if len(candidates) != 1:
            raise EvidenceError(
                f"approved spec source must have exactly one merged default-branch PR: {path}"
            )
        pull = candidates[0]
        revisions[path] = {
            "source_commit_sha": source_commit.lower(),
            "pr_number": pull["number"],
            "merged_at": pull["merged_at"],
            "merge_commit_sha": pull["merge_commit_sha"].lower(),
        }
    result["spec_revisions"] = revisions
    return result


def _revision_connection(
    github_repo: str,
    issue: int,
    pr_number: int,
    query: str,
    key: str,
    run_json: Callable[[list[str]], Any],
) -> tuple[tuple[str, str], list[dict[str, Any]]]:
    owner, name = github_repo.split("/", 1)
    identity: tuple[str, str] | None = None
    cursor: str | None = None
    seen_cursors: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for _page in range(1000):
        args = [
            "api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
            "-F", f"issue={issue}", "-F", f"pr={pr_number}",
            "-f", f"query={query}",
        ]
        if cursor is not None:
            args[2:2] = ["-F", f"cursor={cursor}"]
        payload = json_object(run_json(args), "spec-revision GraphQL response")
        try:
            repository = json_object(payload["data"]["repository"], "repository")
            issue_data = json_object(repository["issue"], "issue")
            pull = json_object(repository["pullRequest"], "pullRequest")
            connection_owner = issue_data if key in {"labels", "timelineItems"} else pull
            connection = json_object(connection_owner[key], key)
            raw_nodes = json_array(connection["nodes"], f"{key}.nodes")
            page_info = json_object(connection["pageInfo"], f"{key}.pageInfo")
        except (KeyError, TypeError) as exc:
            raise EvidenceError("spec-revision query returned malformed evidence") from exc
        page_identity = (str(issue_data.get("state")), str(pull.get("headRefOid")))
        if page_identity[0] != "OPEN" or not SHA_PATTERN.fullmatch(page_identity[1]):
            raise EvidenceError("spec-revision issue/head identity is invalid")
        if identity is None:
            identity = page_identity
        elif identity != page_identity:
            raise EvidenceError("spec-revision approval snapshot drifted during pagination")
        if not all(isinstance(node, dict) for node in raw_nodes):
            raise EvidenceError(f"spec-revision {key} nodes must be objects")
        nodes.extend(raw_nodes)
        has_next = page_info.get("hasNextPage")
        end_cursor = page_info.get("endCursor")
        if not isinstance(has_next, bool):
            raise EvidenceError(f"spec-revision {key} pageInfo is incomplete")
        if not has_next:
            assert identity is not None
            return identity, nodes
        if (
            not isinstance(end_cursor, str)
            or not end_cursor.strip()
            or end_cursor in seen_cursors
        ):
            raise EvidenceError(f"spec-revision {key} pagination cursor is invalid")
        seen_cursors.add(end_cursor)
        cursor = end_cursor
    raise EvidenceError(f"spec-revision {key} pagination exceeded 1000 pages")


def _revision_snapshot(
    github_repo: str,
    issue: int,
    pr_number: int,
    run_json: Callable[[list[str]], Any],
) -> dict[str, Any]:
    parts = [
        (SPEC_REVISION_LABELS_QUERY, "labels"),
        (SPEC_REVISION_TIMELINE_QUERY, "timelineItems"),
        (SPEC_REVISION_REVIEWS_QUERY, "reviews"),
    ]
    identity: tuple[str, str] | None = None
    snapshot: dict[str, Any] = {}
    for query, key in parts:
        part_identity, nodes = _revision_connection(
            github_repo, issue, pr_number, query, key, run_json
        )
        if identity is None:
            identity = part_identity
        elif identity != part_identity:
            raise EvidenceError("spec-revision approval snapshot drifted between queries")
        snapshot[key] = nodes
    assert identity is not None
    snapshot["issue_state"], snapshot["head_sha"] = identity
    return snapshot


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{field} must be a timezone-aware timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{field} must be a timezone-aware timestamp")
    return parsed


def _terminal_lifecycle(snapshot: dict[str, Any]) -> None:
    current = {
        node.get("name")
        for node in snapshot["labels"]
        if isinstance(node.get("name"), str) and node.get("name") in SPEC_LIFECYCLE_LABELS
    }
    if current != {"spec_approved"}:
        raise EvidenceError("spec-revision issue lifecycle must be spec_approved")
    events: list[tuple[datetime, str]] = []
    for node in snapshot["timelineItems"]:
        label = node.get("label")
        name = label.get("name") if isinstance(label, dict) else None
        if name not in SPEC_LIFECYCLE_LABELS:
            continue
        events.append((_timestamp(node.get("createdAt"), "lifecycle event"), name))
    if not events or max(events, key=lambda item: item[0])[1] != "spec_approved":
        raise EvidenceError("latest trusted lifecycle label must be spec_approved")


def _maintainer_permission(
    owner: str,
    name: str,
    actor: str,
    run_json: Callable[[list[str]], Any],
) -> None:
    payload = json_object(
        run_json([
            "api", "--method", "GET",
            f"repos/{owner}/{name}/collaborators/{quote(actor, safe='')}/permission",
        ]),
        "collaborator permission response",
    )
    if payload.get("permission") not in MAINTAINER_PERMISSIONS:
        raise EvidenceError("spec-revision approval actor lacks maintainer permission")


def _exact_head_approval(
    github_repo: str,
    snapshot: dict[str, Any],
    expected_head_sha: str,
    run_json: Callable[[list[str]], Any],
) -> dict[str, str]:
    if snapshot.get("head_sha") != expected_head_sha:
        raise EvidenceError("spec-revision approval snapshot head does not match gated head")
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for review in snapshot["reviews"]:
        commit = review.get("commit")
        commit_oid = commit.get("oid") if isinstance(commit, dict) else None
        if review.get("state") != "APPROVED" or commit_oid != expected_head_sha:
            continue
        candidates.append(
            (_timestamp(review.get("submittedAt"), "approved review submittedAt"), review)
        )
    if not candidates:
        raise EvidenceError("spec-revision requires an exact-head APPROVED review")
    owner, name = github_repo.split("/", 1)
    for _submitted, review in sorted(candidates, key=lambda item: item[0], reverse=True):
        author = review.get("author")
        actor = author.get("login") if isinstance(author, dict) else None
        url = review.get("url")
        if not isinstance(actor, str) or not actor.strip():
            continue
        try:
            _maintainer_permission(owner, name, actor.strip(), run_json)
        except EvidenceError as exc:
            if "lacks maintainer permission" in str(exc):
                continue
            raise
        if not isinstance(url, str) or not url.startswith("https://"):
            raise EvidenceError("spec-revision approved review requires an HTTPS URL")
        return {
            "maintainer_actor": actor.strip(),
            "approved_at": str(review["submittedAt"]).strip(),
            "approval_url": url.strip(),
            "commit_oid": expected_head_sha,
        }
    raise EvidenceError("spec-revision APPROVED review is not from a maintainer")


def _artifact_digest(
    github_repo: str,
    head_sha: str,
    artifact_paths: tuple[str, ...],
    run_json: Callable[[list[str]], Any],
) -> str:
    owner, name = github_repo.split("/", 1)
    content_hashes: dict[str, str] = {}
    for path in sorted(artifact_paths):
        payload = json_object(
            run_json([
                "api", "--method", "GET",
                f"repos/{owner}/{name}/contents/{quote(path, safe='/')}?ref={head_sha}",
            ]),
            f"spec artifact response for {path}",
        )
        content = payload.get("content")
        if payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise EvidenceError(f"spec artifact is not a base64 file at gated head: {path}")
        if not isinstance(content, str):
            raise EvidenceError(f"spec artifact lacks content at gated head: {path}")
        try:
            raw = base64.b64decode("".join(content.split()), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise EvidenceError(f"spec artifact content is invalid base64: {path}") from exc
        content_hashes[path] = hashlib.sha256(raw).hexdigest()
    try:
        return spec_artifacts_sha256_from_hashes(content_hashes)
    except SpecRailError as exc:
        raise EvidenceError(str(exc)) from exc


def collect_spec_revision_approval(
    github_repo: str,
    issue: int,
    pr_number: int,
    head_sha: str,
    artifact_paths: tuple[str, ...],
    run_json: Callable[[list[str]], Any],
) -> dict[str, Any]:
    """Collect stable, exact-head lifecycle, review, and artifact evidence."""

    if not SHA_PATTERN.fullmatch(head_sha) or not artifact_paths:
        raise EvidenceError("spec-revision approval requires a head SHA and artifact paths")
    before = _revision_snapshot(github_repo, issue, pr_number, run_json)
    _terminal_lifecycle(before)
    approval = _exact_head_approval(github_repo, before, head_sha, run_json)
    artifacts_sha256 = _artifact_digest(
        github_repo, head_sha, artifact_paths, run_json
    )
    after = _revision_snapshot(github_repo, issue, pr_number, run_json)
    if before != after:
        raise EvidenceError("spec-revision approval snapshot drifted during collection")
    _terminal_lifecycle(after)
    if approval != _exact_head_approval(github_repo, after, head_sha, run_json):
        raise EvidenceError("spec-revision maintainer approval drifted during collection")
    return {
        "lifecycle_state": "spec_approved",
        "state_source": "label",
        "state_trusted": True,
        **approval,
        "approval_source": "github_pr_review",
        "artifact_paths": list(sorted(artifact_paths)),
        "spec_artifacts_sha256": artifacts_sha256,
    }
