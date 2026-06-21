#!/usr/bin/env python3
"""Validate a SpecRail workflow pack without network or GitHub writes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_FILES = [
    "README.md",
    "SPEC.md",
    "workflow.yaml",
    "states.yaml",
    "labels.yaml",
    "templates/issue_bug.md",
    "templates/issue_feature.md",
    "templates/product_spec.md",
    "templates/tech_spec.md",
    "templates/pull_request.md",
    "review/agent_first_review.md",
    "review/human_final_review.md",
    "policies/security_disclosure.md",
    "policies/maintainer_escalation.md",
    "schemas/flow_manifest.schema.json",
    "schemas/issue_triage.schema.json",
    "schemas/spec_packet.schema.json",
    "schemas/pr_review_gate.schema.json",
    "schemas/workflow_run.schema.json",
]

REQUIRED_TOKENS = {
    "workflow.yaml": [
        "default_mode: dry_run",
        "forbidden_agent_actions:",
        "required_human_gates:",
    ],
    "states.yaml": [
        "ready_to_spec",
        "ready_to_implement",
        "agent_review",
        "human_review",
        "merge_ready",
    ],
    "labels.yaml": [
        "readiness:",
        "ready_to_spec",
        "ready_to_implement",
        "security_private",
    ],
    "templates/product_spec.md": [
        "## Goals",
        "## Non-Goals",
        "## Acceptance Criteria",
    ],
    "templates/tech_spec.md": [
        "## Proposed Design",
        "## Test Plan",
        "## Rollback Plan",
    ],
    "templates/pull_request.md": [
        "## Linked Work",
        "## Readiness Gate",
        "## Review Gate",
        "## Verification",
    ],
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def validate_required_files(repo: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        path = repo / rel
        if not path.is_file():
            errors.append(f"missing required file: {rel}")
    return errors


def validate_tokens(repo: Path) -> list[str]:
    errors: list[str] = []
    for rel, tokens in REQUIRED_TOKENS.items():
        path = repo / rel
        if not path.is_file():
            continue
        text = read_text(path)
        for token in tokens:
            if token not in text:
                errors.append(f"{rel}: missing token {token!r}")
    return errors


def validate_json_schemas(repo: Path) -> list[str]:
    errors: list[str] = []
    schema_dir = repo / "schemas"
    if not schema_dir.is_dir():
        return ["missing schemas/ directory"]

    for path in sorted(schema_dir.glob("*.schema.json")):
        try:
            data = json.loads(read_text(path))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.relative_to(repo)}: invalid JSON: {exc.msg}")
            continue
        if "$schema" not in data:
            errors.append(f"{path.relative_to(repo)}: missing $schema")
        if "title" not in data:
            errors.append(f"{path.relative_to(repo)}: missing title")
        if data.get("type") != "object":
            errors.append(f"{path.relative_to(repo)}: top-level type must be object")
    return errors


def validate_spec_packet(spec_dir: Path) -> list[str]:
    errors: list[str] = []
    if not spec_dir.exists():
        return [f"spec packet does not exist: {spec_dir}"]
    if not spec_dir.is_dir():
        return [f"spec packet is not a directory: {spec_dir}"]
    for name in ["product.md", "tech.md"]:
        path = spec_dir / name
        if not path.is_file():
            errors.append(f"{spec_dir}: missing {name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a SpecRail workflow pack."
    )
    parser.add_argument("--repo", default=".", help="Workflow pack root")
    parser.add_argument(
        "--spec-dir",
        action="append",
        default=[],
        help="Optional specs/GH<number> directory to validate",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    errors: list[str] = []
    errors.extend(validate_required_files(repo))
    errors.extend(validate_tokens(repo))
    errors.extend(validate_json_schemas(repo))
    for raw_spec_dir in args.spec_dir:
        errors.extend(validate_spec_packet((repo / raw_spec_dir).resolve()))

    if errors:
        print("SpecRail check failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print("SpecRail check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
