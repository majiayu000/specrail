#!/usr/bin/env python3
"""Validate the optional SpecRail milestone resume cursor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from schema_validation import load_json_schema
from specrail_lib import SpecRailError, validate_instance


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "runtime_checkpoint.schema.json"
WORK_LISTS = ("completed", "pending", "blocked")


def _load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read checkpoint: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"checkpoint is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("checkpoint top-level value must be an object")
    return payload


def evaluate_checkpoint(data: dict[str, Any], **_: Any) -> dict[str, Any]:
    errors: list[str] = []
    try:
        validate_instance(load_json_schema(SCHEMA_PATH), data)
    except SpecRailError as exc:
        errors.append(str(exc))
        return {"decision": "blocked", "errors": errors, "warnings": []}

    seen: dict[tuple[str, int], str] = {}
    for list_name in WORK_LISTS:
        for item in data[list_name]:
            key = (item["kind"], item["number"])
            prior = seen.get(key)
            if prior is not None:
                errors.append(
                    f"{item['kind']} #{item['number']} appears in both "
                    f"{prior} and {list_name}"
                )
            else:
                seen[key] = list_name

    status = data["status"]
    if status == "complete" and (data["pending"] or data["blocked"]):
        errors.append("complete checkpoint cannot contain pending or blocked work")
    milestone = data["milestone"]
    milestone_state = milestone["state"]
    completed_at = milestone.get("completed_at")
    if status == "running" and milestone_state != "active":
        errors.append("running checkpoint requires an active milestone")
    if status in {"handoff", "blocked"} and milestone_state not in {
        "paused",
        "complete",
    }:
        errors.append(f"{status} checkpoint requires a paused or complete milestone")
    if status == "complete" and milestone_state != "complete":
        errors.append(f"{status} checkpoint requires a complete milestone")
    if milestone_state == "complete" and not (
        isinstance(completed_at, str) and completed_at.strip()
    ):
        errors.append("complete milestone requires completed_at")
    if milestone_state != "complete" and completed_at is not None:
        errors.append(f"{milestone_state} milestone requires completed_at null")

    return {
        "decision": "blocked" if errors else "allowed",
        "errors": errors,
        "warnings": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a SpecRail milestone checkpoint."
    )
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = evaluate_checkpoint(_load_checkpoint(Path(args.checkpoint)))
    except ValueError as exc:
        result = {"decision": "blocked", "errors": [str(exc)], "warnings": []}

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["decision"] == "allowed":
        print("SpecRail milestone checkpoint allowed")
    else:
        print("SpecRail milestone checkpoint blocked")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["decision"] == "allowed" else 1


if __name__ == "__main__":
    sys.exit(main())
