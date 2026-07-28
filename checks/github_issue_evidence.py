#!/usr/bin/env python3
"""Collect read-only GitHub issue evidence for the offline SpecRail route gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from _lib.issue_labels import validate_issue_labels
from github_evidence_common import EvidenceError, json_object
from github_pr_evidence import (
    _require_positive_int,
    _require_string,
    parse_github_repo,
    run_gh_json,
)
from rejection_items import is_substantive_text
from sensitive_enforcement import (
    classification_from_tech_spec,
    sensitive_registry,
)
from specrail_lib import (
    ISSUE_STATES,
    PackConfig,
    SpecRailError,
    load_pack,
    resolve_path,
    resolve_repo_path,
    spec_packet_artifact_paths,
    state_map,
)


ISSUE_VIEW_FIELDS = [
    "number",
    "title",
    "state",
    "labels",
    "url",
    "body",
]

STATE_HINT_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?state\s*:\s*[`\"']?([A-Za-z0-9_]+)[`\"']?\s*$",
    re.IGNORECASE,
)
KNOWN_STATES = set(ISSUE_STATES)
PLAN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PLAN_ITEM_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.+?)\s*$")
PLAN_HEADINGS = ("done-when", "done when", "acceptance criteria", "完成标准", "验收标准")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`+|~+)[ \t]*$")


def parse_issue_number(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("issue number must be a positive integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("issue number must be a positive integer")
    return value


def collect_issue_view(github_repo: str, issue_number: int) -> dict[str, Any]:
    return json_object(run_gh_json(
        [
            "issue",
            "view",
            str(issue_number),
            "--repo",
            github_repo,
            "--json",
            ",".join(ISSUE_VIEW_FIELDS),
        ]
    ), "gh issue view response")


def _optional_body(payload: dict[str, Any]) -> str:
    value = payload.get("body")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EvidenceError("body must be a string or null")
    return value


def normalize_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise EvidenceError("labels must be a list")
    labels: list[str] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            label = item.strip()
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            label = item["name"].strip()
        else:
            raise EvidenceError(f"label item #{index} must be a string or object with name")
        if label:
            labels.append(label)
    return labels


def infer_state_from_labels(
    labels: list[str],
    config: PackConfig | None = None,
) -> str | None:
    try:
        state, _outcomes = validate_issue_labels(config, labels)
    except SpecRailError as exc:
        raise EvidenceError(str(exc)) from exc
    return state


def infer_state_from_body(
    body: str,
    config: PackConfig | None = None,
) -> str | None:
    known_states = set(state_map(config)) if config is not None else KNOWN_STATES
    matches: list[str] = []
    for line in body.splitlines():
        match = STATE_HINT_PATTERN.fullmatch(line)
        if match is None:
            continue
        state = match.group(1)
        if state in known_states:
            matches.append(state)
    unique_matches = sorted(set(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    if len(unique_matches) > 1:
        raise EvidenceError(f"conflicting state hints: {', '.join(unique_matches)}")
    return None


def infer_state_with_source(
    labels: list[str],
    body: str,
    config: PackConfig | None = None,
) -> tuple[str | None, str, bool]:
    state = infer_state_from_labels(labels, config)
    if state is not None:
        return state, "label", True

    state = infer_state_from_body(body, config)
    if state is not None:
        return state, "body_hint", False

    return None, "none", False


def _visible_issue_body(body: str) -> str:
    visible_lines: list[str] = []
    in_comment = False
    fence: str | None = None
    for raw_line in body.splitlines():
        if fence is not None:
            fence_match = FENCE_CLOSE_RE.fullmatch(raw_line)
            if (
                fence_match is not None
                and fence_match.group(1)[0] == fence[0]
                and len(fence_match.group(1)) >= len(fence)
            ):
                fence = None
            continue
        line = raw_line
        while line:
            if in_comment:
                end = line.find("-->")
                if end < 0:
                    line = ""
                    break
                line, in_comment = line[end + 3:], False
            start = line.find("<!--")
            if start < 0:
                break
            end = line.find("-->", start + 4)
            if end < 0:
                line, in_comment = line[:start], True
                break
            line = line[:start] + line[end + 3:]
        match = FENCE_OPEN_RE.match(line)
        if match is not None and (
            match.group(1)[0] == "~" or "`" not in match.group(2)
        ):
            fence = match.group(1)
            continue
        visible_lines.append(line)
    return "\n".join(visible_lines)


def extract_testable_plan_from_body(body: str) -> dict[str, object] | None:
    section_level: int | None = None
    items: list[str] = []
    invalid_item = False
    for line in _visible_issue_body(body).splitlines():
        heading = PLAN_HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group(1))
            title = heading.group(2).strip().lower()
            if section_level is not None and level <= section_level:
                section_level = None
            if any(title.startswith(name) for name in PLAN_HEADINGS):
                section_level = level
            continue
        item = PLAN_ITEM_RE.match(line)
        if section_level is not None and item is not None:
            value = item.group(1).strip()
            invalid_item = invalid_item or not is_substantive_text(value)
            items.append(value)
    if invalid_item or not items:
        return None
    return {
        "source": "issue_body_checklist",
        "items": items,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def default_artifacts(issue_number: int) -> dict[str, str]:
    return {
        "product_spec": f"specs/GH{issue_number}/product.md",
        "tech_spec": f"specs/GH{issue_number}/tech.md",
        "task_plan": f"specs/GH{issue_number}/tasks.md",
    }


def configured_artifacts(repo: Path, issue_number: int) -> dict[str, str]:
    config = load_pack(repo)
    paths = spec_packet_artifact_paths(config, issue_number, repo=repo)
    return {
        name: paths[name]
        for name in ["product_spec", "tech_spec", "task_plan"]
    }


def build_issue_evidence(
    issue_payload: dict[str, Any],
    artifacts: dict[str, str] | None = None,
    config: PackConfig | None = None,
) -> dict[str, Any]:
    issue_number = _require_positive_int(issue_payload, "number")
    title = _require_string(issue_payload, "title")
    github_state = _require_string(issue_payload, "state").upper()
    url = _require_string(issue_payload, "url")
    labels = normalize_labels(issue_payload.get("labels"))
    body = _optional_body(issue_payload)
    state, state_source, state_trusted = infer_state_with_source(labels, body, config)
    try:
        _label_state, outcomes = validate_issue_labels(config, labels)
    except SpecRailError as exc:
        raise EvidenceError(str(exc)) from exc

    evidence: dict[str, Any] = {
        "issue": issue_number,
        "github_state": github_state,
        "state": state,
        "state_source": state_source,
        "state_trusted": state_trusted,
        "labels": labels,
        "outcomes": outcomes,
        "url": url,
        "title": title,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "artifacts": default_artifacts(issue_number) if artifacts is None else artifacts,
    }
    plan = extract_testable_plan_from_body(body)
    if plan is not None:
        evidence["testable_plan"] = plan
    return evidence


def collect_issue_evidence(
    github_repo: str,
    issue_number: int,
    repo: Path,
) -> dict[str, Any]:
    parse_github_repo(github_repo)
    config = load_pack(repo)
    paths = spec_packet_artifact_paths(config, issue_number, repo=repo)
    artifacts = {
        name: paths[name]
        for name in ["product_spec", "tech_spec", "task_plan"]
    }
    issue_payload = collect_issue_view(github_repo, issue_number)
    payload_issue_number = _require_positive_int(issue_payload, "number")
    if payload_issue_number != issue_number:
        raise EvidenceError(
            f"issue number mismatch: expected {issue_number}, got {payload_issue_number}"
        )
    evidence = build_issue_evidence(
        issue_payload,
        artifacts,
        config,
    )
    evidence["repository"] = github_repo
    tech_spec = resolve_repo_path(
        repo,
        artifacts["tech_spec"],
        label="configured tech spec",
    )
    if (
        evidence["state"] == "ready_to_implement"
        and evidence["state_source"] == "label"
        and evidence["state_trusted"] is True
        and any(sensitive_registry(config).values())
        and tech_spec.is_file()
    ):
        evidence.update(
            collect_sensitive_route_evidence(
                github_repo, issue_number, repo, config
            )
        )
    return evidence


def collect_sensitive_route_evidence(
    github_repo: str,
    issue_number: int,
    repo: Path,
    config: PackConfig,
) -> dict[str, Any]:
    classification = classification_from_tech_spec(
        config,
        repo,
        issue=issue_number,
    )
    return {
        "enforcement_sensitive": classification["enforcement_sensitive"],
        "sensitive_classification": classification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect read-only GitHub issue evidence for SpecRail route_gate.py."
    )
    parser.add_argument("--repo", default=".", help="SpecRail pack or adopted repo root")
    parser.add_argument("--github-repo", required=True, help="GitHub repository as OWNER/REPO")
    parser.add_argument("--issue", required=True, type=parse_issue_number, help="Issue number")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    try:
        evidence = collect_issue_evidence(
            args.github_repo,
            args.issue,
            resolve_path(Path(args.repo), label="repository"),
        )
    except (EvidenceError, SpecRailError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
