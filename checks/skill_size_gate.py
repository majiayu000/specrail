#!/usr/bin/env python3
"""Skill contract size gate (GH-208).

Enforces the anti-flywheel hard caps: per-skill line ceilings and tiered
read-set byte budgets. Adding contract text past a cap requires deleting an
equal amount first (one-in-one-out; see AGENTS.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LINE_CAPS = {
    "skills/specrail-implement-queue/SKILL.md": 400,
    "skills/implx/SKILL.md": 150,
}
DEFAULT_SKILL_LINE_CAP = 200

# Files read before any work starts on the single-issue short circuit.
FASTLANE_READ_SET = (
    "skills/implx/SKILL.md",
    "skills/specrail-implement/SKILL.md",
    "skills/specrail-pr-gate/SKILL.md",
)
FASTLANE_BYTE_BUDGET = 30 * 1024

# Files read at startup for a full queue drain. Phase-loaded files
# (review-pr, pr-gate, implement, threads, workflow router) are excluded:
# they load lazily per skills/implx/SKILL.md Tiered Read Set.
FULL_DRAIN_STARTUP_READ_SET = (
    "AGENTS.md",
    "AGENT_USAGE.md",
    "workflow.yaml",
    "states.yaml",
    "labels.yaml",
    "skills/implx/SKILL.md",
    "skills/specrail-implement-queue/SKILL.md",
    "templates/queue_plan.yaml",
)
FULL_DRAIN_STARTUP_BYTE_BUDGET = 60 * 1024


def evaluate(repo: Path) -> dict:
    errors: list[str] = []
    line_counts: dict[str, int] = {}

    for skill_path in sorted(repo.glob("skills/*/SKILL.md")):
        rel = skill_path.relative_to(repo).as_posix()
        cap = LINE_CAPS.get(rel, DEFAULT_SKILL_LINE_CAP)
        lines = len(skill_path.read_text(encoding="utf-8").splitlines())
        line_counts[rel] = lines
        if lines > cap:
            errors.append(f"{rel}: {lines} lines exceeds hard cap {cap}")

    read_sets = {}
    for name, files, budget in (
        ("fastlane", FASTLANE_READ_SET, FASTLANE_BYTE_BUDGET),
        (
            "full_drain_startup",
            FULL_DRAIN_STARTUP_READ_SET,
            FULL_DRAIN_STARTUP_BYTE_BUDGET,
        ),
    ):
        total = 0
        for rel in files:
            path = repo / rel
            if not path.is_file():
                errors.append(f"{name} read set: missing file {rel}")
                continue
            total += path.stat().st_size
        read_sets[name] = {"bytes": total, "budget": budget, "files": list(files)}
        if total > budget:
            errors.append(
                f"{name} read set: {total} bytes exceeds budget {budget}"
            )

    return {
        "decision": "blocked" if errors else "allowed",
        "errors": errors,
        "line_counts": line_counts,
        "read_sets": read_sets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--json", action="store_true", help="emit JSON result")
    args = parser.parse_args()

    result = evaluate(Path(args.repo).resolve())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for error in result["errors"]:
            print(f"skill-size-gate: {error}", file=sys.stderr)
        print(f"skill-size-gate: {result['decision']}")
    return 0 if result["decision"] == "allowed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
