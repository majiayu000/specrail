#!/usr/bin/env python3
"""Produce a read-only advisory warning for suspicious closure chains."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _timestamp(value: Any, label: str, warnings: list[dict[str, str]]) -> datetime | None:
    if not isinstance(value, str):
        warnings.append({"code": "invalid_timestamp", "message": f"{label} must be a timestamp"})
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        warnings.append({"code": "invalid_timestamp", "message": f"{label} is invalid"})
        return None


def audit_closure(
    evidence: dict[str, Any],
    *,
    checked_at: str | None = None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    repository = evidence.get("repository")
    if isinstance(repository, str):
        repository = repository.lower()
    else:
        warnings.append({"code": "invalid_repository", "message": "repository must be OWNER/REPO"})
        repository = None
    pr = evidence.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
        warnings.append({"code": "invalid_pr", "message": "pr must be positive"})
    final_head = evidence.get("final_head_sha")
    if not isinstance(final_head, str) or not SHA_RE.fullmatch(final_head):
        warnings.append({"code": "invalid_head", "message": "final_head_sha must be a full SHA"})

    gate = evidence.get("gate")
    merge = evidence.get("merge")
    if not isinstance(gate, dict):
        warnings.append({"code": "closure_missing_gate_evidence", "message": "pre-merge gate evidence is missing"})
        gate = {}
    if not isinstance(merge, dict):
        warnings.append({"code": "closure_missing_merge_evidence", "message": "merge evidence is missing"})
        merge = {}
    if gate.get("decision") != "allowed":
        warnings.append({"code": "closure_gate_not_allowed", "message": "recorded gate decision is not allowed"})
    for label, value in (
        ("gate head", gate.get("head_sha")),
        ("gate query head", gate.get("gate_query_head_sha")),
        ("merge head", merge.get("merge_head_sha")),
    ):
        if final_head and value != final_head:
            warnings.append({"code": "closure_head_mismatch", "message": f"{label} does not match final head"})

    queried = _timestamp(gate.get("gate_query_completed_at"), "gate query", warnings)
    dispatched = _timestamp(merge.get("merge_dispatched_at"), "merge dispatch", warnings)
    merged = _timestamp(merge.get("merged_at"), "merge completion", warnings)
    if queried and dispatched and dispatched <= queried:
        warnings.append({"code": "closure_dispatch_not_after_gate", "message": "merge dispatch must follow gate query"})
    if dispatched and merged and merged < dispatched:
        warnings.append({"code": "closure_merge_before_dispatch", "message": "merge completion precedes dispatch"})

    unique = {
        (item["code"], item["message"]): item
        for item in warnings
    }
    ordered = [unique[key] for key in sorted(unique)]
    return {
        "status": "warning" if ordered else "clear",
        "repository": repository,
        "pr": pr,
        "final_head_sha": final_head,
        "checked_at": checked_at,
        "warnings": ordered,
        "violations": ordered,
        "advisory_only": True,
        "github_writes_performed": False,
        "required_follow_up": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory closure chain audit.")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--checked-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    path = Path(args.evidence)
    if not path.is_absolute():
        path = repo / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("closure evidence must be an object")
        result = audit_closure(value, checked_at=args.checked_at)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = audit_closure({}, checked_at=args.checked_at)
        result["warnings"].append({"code": "invalid_evidence", "message": str(exc)})
        result["violations"] = result["warnings"]
        result["status"] = "warning"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
