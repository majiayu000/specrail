"""Collect maintainer-controlled approved-spec label evidence from GitHub."""

from __future__ import annotations

from typing import Any, Callable

from github_evidence_common import EvidenceError


APPROVAL_QUERY = """
query SpecRailApproval($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      state
      labels(first: 100) { nodes { name } }
      timelineItems(last: 100, itemTypes: [LABELED_EVENT]) {
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


def collect_approval_metadata(
    github_repo: str,
    issue: int,
    run_json: Callable[[list[str]], dict[str, Any]],
) -> dict[str, str]:
    owner, name = github_repo.split("/", 1)
    payload = run_json(
        [
            "api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
            "-F", f"number={issue}", "-f", f"query={APPROVAL_QUERY}",
        ]
    )
    try:
        issue_data = payload["data"]["repository"]["issue"]
        labels = issue_data["labels"]["nodes"]
        events = issue_data["timelineItems"]["nodes"]
    except (KeyError, TypeError) as exc:
        raise EvidenceError("approved-spec query returned malformed issue evidence") from exc
    if issue_data.get("state") != "OPEN":
        raise EvidenceError("approved-spec issue must remain OPEN")
    current_labels = {
        item.get("name") for item in labels if isinstance(item, dict)
    }
    if "ready_to_implement" not in current_labels:
        raise EvidenceError(
            "approved spec requires current ready_to_implement maintainer label"
        )
    candidates: list[tuple[str, str]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        label = event.get("label")
        actor = event.get("actor")
        if not isinstance(label, dict) or label.get("name") != "ready_to_implement":
            continue
        created_at = event.get("createdAt")
        login = actor.get("login") if isinstance(actor, dict) else None
        if isinstance(created_at, str) and created_at.strip() and isinstance(login, str) and login.strip():
            candidates.append((created_at.strip(), login.strip()))
    if not candidates:
        raise EvidenceError(
            "ready_to_implement label lacks maintainer actor/timestamp evidence"
        )
    approved_at, maintainer_actor = max(candidates)
    return {
        "approved_at": approved_at,
        "maintainer_actor": maintainer_actor,
        "state_source": "label",
        "state_trusted": True,
    }
