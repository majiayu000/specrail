#!/usr/bin/env python3
"""Report duplicate work as advisory evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from schema_validation import validate_instance
from specrail_lib import PackConfig, SpecRailError, load_pack, resolve_path


def _positive_issue(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _load_schema(repo: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            (repo / "schemas" / "duplicate_work_evidence.schema.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecRailError(f"cannot load duplicate work schema: {exc}") from exc
    if not isinstance(value, dict):
        raise SpecRailError("duplicate work schema must be an object")
    return value


def _load_evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecRailError(f"cannot load duplicate work evidence: {exc}") from exc
    if not isinstance(value, dict):
        raise SpecRailError("duplicate work evidence must be an object")
    return value


def _impl_branch_token(config: PackConfig, issue: int) -> str | None:
    artifacts = config.workflow.get("artifacts", {})
    template = artifacts.get("impl_branch") if isinstance(artifacts, dict) else None
    if not isinstance(template, str) or "{issue_number}" not in template:
        return None
    return f"gh{issue}"


def _result(
    issue: int | None,
    warnings: list[str],
    satisfied: list[str],
) -> dict[str, Any]:
    return {
        "decision": "warn" if warnings else "allowed",
        "issue": issue,
        "advisory_only": True,
        "warnings": sorted(set(warnings)),
        "reasons": sorted(set(warnings)),
        "satisfied": sorted(set(satisfied)),
        "missing": [],
        "blocked_actions": [],
        "verification_commands": [
            "python3 checks/github_duplicate_evidence.py --github-repo OWNER/REPO --issue <issue> --json"
        ],
    }


def evaluate_duplicate_work_gate(
    config: PackConfig,
    issue: int | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    satisfied: list[str] = []
    if not _positive_issue(issue):
        return _result(issue, ["duplicate check requires a positive issue number"], [])
    if evidence is None:
        return _result(
            issue,
            ["duplicate work evidence is missing; search GitHub before implementation"],
            [],
        )
    try:
        validate_instance(_load_schema(config.repo), evidence, "duplicate evidence")
    except SpecRailError as exc:
        return _result(issue, [f"duplicate evidence is invalid: {exc}"], [])
    if evidence.get("issue") != issue:
        warnings.append(
            f"duplicate evidence issue mismatch: expected {issue}, got {evidence.get('issue')}"
        )
    duplicate_prs = sorted(
        item["number"]
        for item in evidence.get("open_prs", [])
        if isinstance(item, dict) and item.get("references_issue") is True
    )
    if duplicate_prs:
        warnings.append(
            "open PRs already reference GH-"
            f"{issue}: {', '.join(f'#{number}' for number in duplicate_prs)}"
        )
    else:
        satisfied.append(f"no open PR references GH-{issue}")
    if evidence.get("open_prs_complete") is not True:
        warnings.append("open PR evidence may be incomplete")
    token = _impl_branch_token(config, issue)
    if token is None:
        warnings.append("workflow artifacts.impl_branch is missing its issue token")
    else:
        branches = sorted(
            branch
            for branch in evidence.get("remote_branches", [])
            if isinstance(branch, str) and token in branch.lower()
        )
        if branches:
            warnings.append(
                "remote branches may already own this issue: " + ", ".join(branches)
            )
        else:
            satisfied.append(f"no remote branch matches implementation token {token}")
    return _result(issue, warnings, satisfied)


def evaluate_duplicate_work_gate_path(
    repo: Path,
    issue: int | None,
    evidence_path: Path | None,
) -> dict[str, Any]:
    config = load_pack(repo)
    try:
        evidence = _load_evidence(evidence_path)
    except SpecRailError as exc:
        return _result(issue, [str(exc)], [])
    return evaluate_duplicate_work_gate(config, issue, evidence)


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory duplicate-work check.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument("--evidence")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repo = resolve_path(Path(args.repo), label="repository")
    evidence = Path(args.evidence) if args.evidence else None
    if evidence is not None and not evidence.is_absolute():
        evidence = repo / evidence
    result = evaluate_duplicate_work_gate_path(repo, args.issue, evidence)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"decision: {result['decision']}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
