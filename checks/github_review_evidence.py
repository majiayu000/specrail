"""Review-thread, authorization, and reviewer-lane evidence helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from github_evidence_common import EvidenceError


LANE_FAILURE_KINDS = {"usage_limit", "crash", "zero_output", "closed", "other"}
THREAD_ROLE_PREFIX = "thread:"
ROUND_CAP_DECISION = "continue_once"
ROUND_CAP_FIELDS = {
    "authorization_id",
    "pr",
    "prior_head_sha",
    "target_head_sha",
    "review_round",
    "decision",
    "actor",
    "source",
    "authorized_at",
}
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
AUTHORIZATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _read_json_file(path: str, field: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise EvidenceError(f"cannot read {field} file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{field} file is not valid JSON: {exc.msg}") from exc


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{field} must be a list")
    return value


def _first_comment_url(thread: dict[str, Any]) -> str | None:
    comments = thread.get("comments")
    if not isinstance(comments, dict) or not isinstance(comments.get("nodes"), list):
        return None
    for node in comments["nodes"]:
        if isinstance(node, dict) and isinstance(node.get("url"), str) and node["url"].strip():
            return node["url"].strip()
    return None


def _first_comment_identity(thread: dict[str, Any], index: int) -> tuple[str, str]:
    comments = thread.get("comments")
    if not isinstance(comments, dict) or not isinstance(comments.get("nodes"), list):
        raise EvidenceError(f"review thread item #{index} requires root comment evidence")
    nodes = comments["nodes"]
    if not nodes or not isinstance(nodes[0], dict):
        raise EvidenceError(f"review thread item #{index} requires a root comment")
    root = nodes[0]
    comment_id = root.get("id")
    author = root.get("author")
    if not isinstance(comment_id, str) or not comment_id.strip():
        raise EvidenceError(f"review thread item #{index} root comment requires id")
    if (
        not isinstance(author, dict)
        or not isinstance(author.get("login"), str)
        or not author["login"].strip()
    ):
        raise EvidenceError(f"review thread item #{index} root comment requires author.login")
    return comment_id.strip(), author["login"].strip()


def _resolver_login(thread: dict[str, Any]) -> str | None:
    for key in ["resolvedBy", "resolved_by"]:
        value = thread.get(key)
        if isinstance(value, dict) and isinstance(value.get("login"), str) and value["login"].strip():
            return value["login"].strip()
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolver_role(thread: dict[str, Any]) -> str | None:
    for key in ["resolverRole", "resolver_role"]:
        value = thread.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_resolver_entry(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, str) and value.strip():
        return {"resolver_role": value.strip()}
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a role string or object")
    role = value.get("resolver_role") or value.get("role")
    if not isinstance(role, str) or not role.strip():
        raise EvidenceError(f"{label}.resolver_role must be a non-empty string")
    normalized: dict[str, Any] = {"resolver_role": role.strip()}
    for key in ["lane_id", "successor_of", "re_review_artifact_id"]:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            normalized[key] = item.strip()
    if "authorized_human_maintainer" in value:
        if not isinstance(value["authorized_human_maintainer"], bool):
            raise EvidenceError(f"{label}.authorized_human_maintainer must be a boolean")
        normalized["authorized_human_maintainer"] = value["authorized_human_maintainer"]
    return normalized


def _resolver_role_map(payload: Any) -> dict[str, dict[str, Any]]:
    source = payload
    if isinstance(payload, dict):
        if isinstance(payload.get("resolver_roles"), dict):
            source = payload["resolver_roles"]
        elif isinstance(payload.get("lane_roster"), list):
            source = payload["lane_roster"]
        elif isinstance(payload.get("lanes"), list):
            source = payload["lanes"]

    roles: dict[str, dict[str, Any]] = {}
    seen_global_logins: dict[str, str] = {}
    if isinstance(source, dict):
        for login, value in source.items():
            if not isinstance(login, str) or not login.strip():
                raise EvidenceError("resolver role map login must be a non-empty string")
            normalized_login = login.strip()
            folded_login = normalized_login.casefold()
            if folded_login in seen_global_logins:
                raise EvidenceError(
                    "duplicate global resolver login: "
                    f"{seen_global_logins[folded_login]} and {normalized_login}; "
                    "use thread_resolver_roles to disambiguate"
                )
            seen_global_logins[folded_login] = normalized_login
            roles[normalized_login] = _normalize_resolver_entry(
                value, f"resolver role map {normalized_login}"
            )
        _add_thread_resolver_roles(payload, roles)
        return roles

    if isinstance(source, list):
        for index, lane in enumerate(source, start=1):
            if not isinstance(lane, dict):
                raise EvidenceError(f"resolver role lane_roster item #{index} must be an object")
            login = lane.get("login") or lane.get("github_login") or lane.get("actor") or lane.get("resolved_by")
            if not isinstance(login, str) or not login.strip():
                raise EvidenceError(f"resolver role lane_roster item #{index} requires login")
            normalized_login = login.strip()
            folded_login = normalized_login.casefold()
            if folded_login in seen_global_logins:
                raise EvidenceError(
                    "duplicate global resolver login: "
                    f"{seen_global_logins[folded_login]} and {normalized_login}; "
                    "use thread_resolver_roles to disambiguate"
                )
            seen_global_logins[folded_login] = normalized_login
            roles[normalized_login] = _normalize_resolver_entry(
                lane, f"resolver role lane_roster item #{index}"
            )
        _add_thread_resolver_roles(payload, roles)
        return roles
    raise EvidenceError("resolver role map must be an object or lane roster list")


def _add_thread_resolver_roles(
    payload: Any,
    roles: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(payload, dict) or "thread_resolver_roles" not in payload:
        return
    thread_roles = payload["thread_resolver_roles"]
    if not isinstance(thread_roles, dict):
        raise EvidenceError("thread_resolver_roles must be an object")
    for thread_id, value in thread_roles.items():
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise EvidenceError(
                "thread_resolver_roles thread id must be a non-empty string"
            )
        normalized_id = thread_id.strip()
        if not isinstance(value, dict):
            raise EvidenceError(
                f"thread_resolver_roles {normalized_id} must be an object"
            )
        resolver_login = value.get("resolver_login")
        if not isinstance(resolver_login, str) or not resolver_login.strip():
            raise EvidenceError(
                f"thread_resolver_roles {normalized_id}.resolver_login "
                "must be a non-empty string"
            )
        normalized = _normalize_resolver_entry(
            value,
            f"thread_resolver_roles {normalized_id}",
        )
        normalized["resolver_login"] = resolver_login.strip()
        roles[f"{THREAD_ROLE_PREFIX}{normalized_id}"] = normalized


def load_resolver_role_map(path: str | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    return _resolver_role_map(_read_json_file(path, "resolver role map"))


def load_maintainer_role_map(path: str | None) -> dict[str, dict[str, Any]]:
    """Load the explicit human-maintainer map used only for round-cap decisions."""

    if path is None:
        return {}
    payload = _require_mapping(
        _read_json_file(path, "maintainer role map"),
        "maintainer role map",
    )
    if set(payload) != {"maintainer_roles"}:
        raise EvidenceError(
            "maintainer role map must contain only maintainer_roles"
        )
    raw_roles = _require_mapping(
        payload.get("maintainer_roles"),
        "maintainer role map.maintainer_roles",
    )
    roles: dict[str, dict[str, Any]] = {}
    for actor, raw_entry in raw_roles.items():
        if not isinstance(actor, str) or not actor.strip():
            raise EvidenceError("maintainer role map actor must be a non-empty string")
        entry = _require_mapping(
            raw_entry,
            f"maintainer role map.maintainer_roles.{actor}",
        )
        if set(entry) != {"role", "authorized_human_maintainer"}:
            raise EvidenceError(
                f"maintainer role map.maintainer_roles.{actor} must contain only "
                "role and authorized_human_maintainer"
            )
        if entry.get("role") != "maintainer":
            raise EvidenceError(
                f"maintainer role map.maintainer_roles.{actor}.role must be maintainer"
            )
        if entry.get("authorized_human_maintainer") is not True:
            raise EvidenceError(
                f"maintainer role map.maintainer_roles.{actor}."
                "authorized_human_maintainer must be true"
            )
        normalized_actor = actor.strip()
        if normalized_actor in roles:
            raise EvidenceError("maintainer role map actors must be unique")
        roles[normalized_actor] = {
            "role": "maintainer",
            "authorized_human_maintainer": True,
        }
    return roles


def _round_cap_string(payload: dict[str, Any], field: str, index: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(
            f"round cap authorization #{index}.{field} must be a non-empty string"
        )
    return value.strip()


def _normalize_round_cap_authorization(
    payload: Any,
    index: int,
    maintainer_roles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    item = _require_mapping(payload, f"round cap authorization #{index}")
    unknown = sorted(set(item) - ROUND_CAP_FIELDS)
    missing = sorted(ROUND_CAP_FIELDS - set(item))
    if unknown:
        raise EvidenceError(
            f"round cap authorization #{index} contains unsupported fields: "
            + ", ".join(unknown)
        )
    if missing:
        raise EvidenceError(
            f"round cap authorization #{index} is missing fields: "
            + ", ".join(missing)
        )

    authorization_id = _round_cap_string(item, "authorization_id", index)
    if AUTHORIZATION_ID_PATTERN.fullmatch(authorization_id) is None:
        raise EvidenceError(
            f"round cap authorization #{index}.authorization_id has invalid format"
        )
    pr = item.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
        raise EvidenceError(
            f"round cap authorization #{index}.pr must be a positive integer"
        )
    review_round = item.get("review_round")
    if (
        not isinstance(review_round, int)
        or isinstance(review_round, bool)
        or review_round <= 3
    ):
        raise EvidenceError(
            f"round cap authorization #{index}.review_round must be greater than 3"
        )
    prior_head_sha = _round_cap_string(item, "prior_head_sha", index)
    target_head_sha = _round_cap_string(item, "target_head_sha", index)
    for field, value in [
        ("prior_head_sha", prior_head_sha),
        ("target_head_sha", target_head_sha),
    ]:
        if SHA_PATTERN.fullmatch(value) is None:
            raise EvidenceError(
                f"round cap authorization #{index}.{field} must be a 40-character Git SHA"
            )
    if prior_head_sha.lower() == target_head_sha.lower():
        raise EvidenceError(
            f"round cap authorization #{index} must bind distinct prior and target heads"
        )
    if item.get("decision") != ROUND_CAP_DECISION:
        raise EvidenceError(
            f"round cap authorization #{index}.decision must be {ROUND_CAP_DECISION}"
        )
    actor = _round_cap_string(item, "actor", index)
    source = _round_cap_string(item, "source", index)
    authorized_at = _round_cap_string(item, "authorized_at", index)
    try:
        parsed_at = datetime.fromisoformat(authorized_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(
            f"round cap authorization #{index}.authorized_at must be ISO-8601"
        ) from exc
    if parsed_at.tzinfo is None:
        raise EvidenceError(
            f"round cap authorization #{index}.authorized_at must include a timezone"
        )
    role = maintainer_roles.get(actor)
    if not isinstance(role, dict) or (
        role.get("role") != "maintainer"
        or role.get("authorized_human_maintainer") is not True
    ):
        raise EvidenceError(
            f"round cap authorization #{index}.actor is not an explicitly authorized maintainer"
        )
    return {
        "authorization_id": authorization_id,
        "pr": pr,
        "prior_head_sha": prior_head_sha.lower(),
        "target_head_sha": target_head_sha.lower(),
        "review_round": review_round,
        "decision": ROUND_CAP_DECISION,
        "actor": actor,
        "source": source,
        "authorized_at": authorized_at,
        "authorized_human_maintainer": True,
    }


def load_round_cap_authorizations(
    paths: list[str] | None,
    maintainer_roles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, path in enumerate(paths or [], start=1):
        item = _normalize_round_cap_authorization(
            _read_json_file(path, f"round cap authorization #{index}"),
            index,
            maintainer_roles,
        )
        authorization_id = item["authorization_id"]
        if authorization_id in seen_ids:
            raise EvidenceError(
                f"round cap authorization id is duplicated: {authorization_id}"
            )
        seen_ids.add(authorization_id)
        normalized.append(item)
    return normalized


def normalize_review_threads(
    graphql_payload: dict[str, Any],
    resolver_roles: dict[str, dict[str, Any]] | dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    data = _require_mapping(graphql_payload.get("data"), "data")
    repository = _require_mapping(data.get("repository"), "data.repository")
    pull_request = _require_mapping(repository.get("pullRequest"), "data.repository.pullRequest")
    review_threads = _require_mapping(
        pull_request.get("reviewThreads"), "data.repository.pullRequest.reviewThreads"
    )
    nodes = _require_list(
        review_threads.get("nodes"), "data.repository.pullRequest.reviewThreads.nodes"
    )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(nodes, start=1):
        if not isinstance(item, dict):
            raise EvidenceError(f"review thread item #{index} must be an object")
        thread: dict[str, Any] = {
            "is_resolved": item.get("isResolved") is True,
            "is_outdated": item.get("isOutdated") is True,
            "actionable": item.get("actionable") is not False,
        }
        thread_id = item.get("id")
        if isinstance(thread_id, str) and thread_id.strip():
            thread["id"] = thread_id.strip()
        url = _first_comment_url(item)
        if url:
            thread["url"] = url
        original_comment_id, original_author = _first_comment_identity(item, index)
        thread["original_comment_id"] = original_comment_id
        thread["original_author"] = original_author
        resolver = _resolver_login(item)
        if resolver:
            thread["resolved_by"] = resolver
        role = _resolver_role(item)
        role_source = "github_payload" if role else None
        metadata: dict[str, Any] = {}
        if resolver and resolver_roles:
            raw_metadata = None
            if isinstance(thread_id, str) and thread_id.strip():
                thread_metadata = resolver_roles.get(
                    f"{THREAD_ROLE_PREFIX}{thread_id.strip()}"
                )
                if (
                    isinstance(thread_metadata, dict)
                    and thread_metadata.get("resolver_login") == resolver
                ):
                    raw_metadata = thread_metadata
            if raw_metadata is None:
                raw_metadata = resolver_roles.get(resolver)
        else:
            raw_metadata = None
        if raw_metadata is not None:
            metadata = (
                {"resolver_role": raw_metadata}
                if isinstance(raw_metadata, str)
                else dict(raw_metadata)
            )
            if not role:
                role = metadata.get("resolver_role")
                role_source = "explicit_map"
            elif metadata.get("resolver_role") == role:
                role_source = "explicit_map"
        if role:
            thread["resolver_role"] = role
        if role_source:
            thread["resolver_role_source"] = role_source
        for key in [
            "lane_id",
            "successor_of",
            "re_review_artifact_id",
            "authorized_human_maintainer",
        ]:
            if key in metadata:
                thread[key] = metadata[key]
        normalized.append(thread)
    return normalized


def build_human_authorization(
    actor: str | None,
    source: str | None,
    summary: str | None,
) -> dict[str, str] | None:
    provided = [value for value in [actor, source, summary] if value is not None and value.strip()]
    if not provided:
        return None
    if not actor or not actor.strip() or not source or not source.strip():
        raise EvidenceError(
            "--authorization-actor and --authorization-source must be provided together"
        )
    authorization = {"actor": actor.strip(), "source": source.strip()}
    if summary and summary.strip():
        authorization["summary"] = summary.strip()
    return authorization


def build_self_review_authorization(
    actor: str | None,
    source: str | None,
    scope: str | None,
    summary: str | None,
) -> dict[str, str] | None:
    provided = [
        value for value in [actor, source, scope, summary]
        if value is not None and value.strip()
    ]
    if not provided:
        return None
    if not actor or not actor.strip() or not source or not source.strip() or not scope or not scope.strip():
        raise EvidenceError(
            "--self-review-authorization-actor, --self-review-authorization-source, "
            "and --self-review-authorization-scope must be provided together"
        )
    authorization = {"actor": actor.strip(), "source": source.strip(), "scope": scope.strip()}
    if summary and summary.strip():
        authorization["summary"] = summary.strip()
    return authorization


def _normalize_lane_failure(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise EvidenceError(f"lane_failures item #{index} must be an object")
    normalized: dict[str, Any] = {}
    for key in ["lane_id", "failure_kind", "observed_marker"]:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise EvidenceError(f"lane_failures[{index}].{key} must be a non-empty string")
        normalized[key] = value.strip()
    if normalized["failure_kind"] not in LANE_FAILURE_KINDS:
        raise EvidenceError(
            f"lane_failures[{index}].failure_kind is unsupported: {normalized['failure_kind']}"
        )
    detail = item.get("detail")
    if isinstance(detail, str) and detail.strip():
        normalized["detail"] = detail.strip()
    pr = item.get("pr")
    if pr is not None:
        if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
            raise EvidenceError(f"lane_failures[{index}].pr must be a positive integer")
        normalized["pr"] = pr
    head_sha = item.get("head_sha")
    if head_sha is not None:
        if not isinstance(head_sha, str) or not head_sha.strip():
            raise EvidenceError(f"lane_failures[{index}].head_sha must be a non-empty string")
        normalized["head_sha"] = head_sha.strip()
    return normalized


def load_lane_failures(path: str | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = _read_json_file(path, "lane failures")
    if isinstance(payload, dict):
        payload = payload.get("lane_failures")
    if not isinstance(payload, list):
        raise EvidenceError("lane failures file must contain a list or lane_failures list")
    return [_normalize_lane_failure(item, index) for index, item in enumerate(payload, start=1)]
