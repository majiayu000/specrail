#!/usr/bin/env python3
"""Evaluate a SpecRail spec packet and adoption smoke evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parent / "checks"
sys.path.insert(0, str(CHECKS_DIR))

from specrail_lib import SpecRailError, load_pack, read_text  # noqa: E402


REQUIRED_SMOKE_IDS = [
    "rclean.new_rule_spec_first",
    "rclean.security_boundary_gate",
    "rclean.doc_only_direct",
    "rclean.ci_command_mapping",
    "rclean.issue_dedupe",
]

REQUIRED_RCLEAN_COMMANDS = [
    "cargo fmt -- --check",
    "cargo clippy --all-targets --all-features -- -D warnings",
    "cargo test",
    "cargo build --release",
    "rustup run 1.95 cargo build",
    "rustup run 1.95 cargo test",
]


def check(status: str, check_id: str, path: str, message: str) -> dict[str, str]:
    return {"id": check_id, "status": status, "path": path, "message": message}


def spec_issue_number(spec_dir: Path) -> str | None:
    match = re.fullmatch(r"GH([0-9]+)", spec_dir.name)
    return match.group(1) if match else None


def issue_tokens(issue_number: str | None) -> list[str]:
    if not issue_number:
        return []
    return [f"GH-{issue_number}", f"GH{issue_number}", f"#{issue_number}"]


def evaluate_spec(repo: Path, spec_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    checks: list[dict[str, str]] = []
    errors: list[str] = []
    issue_number = spec_issue_number(spec_dir)

    for name, check_id in [
        ("product.md", "spec.product_present"),
        ("tech.md", "spec.tech_present"),
        ("tasks.md", "spec.tasks_present"),
    ]:
        path = spec_dir / name
        rel = str(path.relative_to(repo))
        if path.is_file() and read_text(path).strip():
            checks.append(check("pass", check_id, rel, f"{name} exists and is non-empty"))
        else:
            checks.append(check("fail", check_id, rel, f"{name} is missing or empty"))
            errors.append(f"{rel} is missing or empty")

    for name in ["product.md", "tech.md"]:
        path = spec_dir / name
        rel = str(path.relative_to(repo))
        if not path.is_file():
            continue
        text = read_text(path)
        if any(token in text for token in issue_tokens(issue_number)):
            checks.append(check("pass", "spec.issue_anchor_present", rel, "issue anchor present"))
        else:
            checks.append(check("fail", "spec.issue_anchor_present", rel, "issue anchor missing"))
            errors.append(f"{rel} is missing issue anchor")

    task_path = spec_dir / "tasks.md"
    if task_path.is_file():
        task_errors = validate_tasks(repo, task_path, issue_number)
        if task_errors:
            for error in task_errors:
                checks.append(check("fail", "tasks.format", str(task_path.relative_to(repo)), error))
            errors.extend(task_errors)
        else:
            rel = str(task_path.relative_to(repo))
            checks.append(check("pass", "tasks.ids_unique", rel, "task IDs are unique"))
            checks.append(check("pass", "tasks.done_when_present", rel, "all tasks include Done when"))
            checks.append(check("pass", "tasks.verification_present", rel, "all tasks include Verify"))
    return checks, errors


def validate_tasks(repo: Path, task_path: Path, issue_number: str | None) -> list[str]:
    errors: list[str] = []
    text = read_text(task_path)
    prefix = f"SP{issue_number}-T" if issue_number else "SP"
    ids: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "- [" not in line:
            continue
        match = re.search(r"`([^`]+)`", line)
        if not match:
            errors.append(f"{task_path.relative_to(repo)}:{line_number}: missing task ID")
            continue
        task_id = match.group(1)
        ids.append(task_id)
        if issue_number and not task_id.startswith(prefix):
            errors.append(f"{task_path.relative_to(repo)}:{line_number}: {task_id} must start with {prefix}")
        for token in ["Owner:", "Done when:", "Verify:"]:
            if token not in line:
                errors.append(f"{task_path.relative_to(repo)}:{line_number}: {task_id} missing {token}")
    if not ids:
        errors.append(f"{task_path.relative_to(repo)}: no tasks found")
    for task_id in sorted({task_id for task_id in ids if ids.count(task_id) > 1}):
        errors.append(f"{task_path.relative_to(repo)}: duplicate task ID {task_id}")
    return errors


def evaluate_rclean_smoke(repo: Path) -> tuple[list[dict[str, str]], list[str], list[str]]:
    smoke = repo / "examples" / "rclean-smoke.md"
    rel = "examples/rclean-smoke.md"
    checks: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []
    if not smoke.is_file() or not read_text(smoke).strip():
        checks.append(check("fail", "rclean_smoke.present", rel, "rclean smoke file missing"))
        errors.append(f"{rel} is missing")
        return checks, errors, warnings

    text = read_text(smoke)
    checks.append(check("pass", "rclean_smoke.present", rel, "rclean smoke file exists"))
    if "read-only" in text and "Do not modify" in text:
        checks.append(check("pass", "rclean_smoke.read_only", rel, "read-only boundary recorded"))
    else:
        checks.append(check("fail", "rclean_smoke.read_only", rel, "read-only boundary missing"))
        errors.append("rclean smoke is missing read-only boundary")

    missing_ids = [scenario for scenario in REQUIRED_SMOKE_IDS if scenario not in text]
    if missing_ids:
        checks.append(check("fail", "rclean_smoke.scenarios_present", rel, f"missing scenarios: {', '.join(missing_ids)}"))
        errors.append(f"rclean smoke missing scenarios: {', '.join(missing_ids)}")
    else:
        checks.append(check("pass", "rclean_smoke.scenarios_present", rel, "all required scenarios recorded"))

    missing_commands = [command for command in REQUIRED_RCLEAN_COMMANDS if command not in text]
    if missing_commands:
        checks.append(check("fail", "rclean_smoke.ci_commands_present", rel, f"missing commands: {', '.join(missing_commands)}"))
        errors.append(f"rclean smoke missing CI commands: {', '.join(missing_commands)}")
    else:
        checks.append(check("pass", "rclean_smoke.ci_commands_present", rel, "all rclean CI commands recorded"))

    if "NOT SUBMITTED YET" in text and "drafts/rclean-issues-draft-2026-05-25.md" in text:
        checks.append(check("needs_human", "rclean_smoke.issue_dedupe_present", rel, "local draft issue must be reviewed before new issue creation"))
        warnings.append("rclean adoption smoke requires human review before creating duplicate issues")
    else:
        checks.append(check("fail", "rclean_smoke.issue_dedupe_present", rel, "draft issue dedupe evidence missing"))
        errors.append("rclean smoke missing issue dedupe evidence")
    return checks, errors, warnings


def evaluate(repo: Path, spec_dir: Path) -> dict[str, object]:
    checks: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    try:
        load_pack(repo)
        checks.append(check("pass", "workflow.config_present", "workflow.yaml", "workflow config loaded"))
        checks.append(check("pass", "workflow.states_present", "states.yaml", "state config loaded"))
        checks.append(check("pass", "workflow.labels_present", "labels.yaml", "label config loaded"))
    except SpecRailError as exc:
        checks.append(check("fail", "workflow.config_present", ".", str(exc)))
        errors.append(str(exc))

    spec_checks, spec_errors = evaluate_spec(repo, spec_dir)
    checks.extend(spec_checks)
    errors.extend(spec_errors)
    smoke_checks, smoke_errors, smoke_warnings = evaluate_rclean_smoke(repo)
    checks.extend(smoke_checks)
    errors.extend(smoke_errors)
    warnings.extend(smoke_warnings)

    artifacts = {
        "product_spec": str((spec_dir / "product.md").relative_to(repo)),
        "tech_spec": str((spec_dir / "tech.md").relative_to(repo)),
        "tasks_artifact": str((spec_dir / "tasks.md").relative_to(repo)),
        "smoke_example": "examples/rclean-smoke.md",
    }
    if errors:
        status = "fail"
    elif any(item["status"] == "needs_human" for item in checks):
        status = "needs_human"
    else:
        status = "pass"
    next_actions: list[str] = []
    if status == "needs_human":
        next_actions.append("Review rclean draft issue evidence before creating new GitHub issues.")
    if status == "fail":
        next_actions.append("Fix missing or malformed SpecRail artifacts and rerun evaluate.py.")
    return {
        "status": status,
        "repo": str(repo),
        "spec_dir": str(spec_dir.relative_to(repo)),
        "checks": checks,
        "artifacts": artifacts,
        "errors": errors,
        "warnings": warnings,
        "next_actions": next_actions,
    }


def print_text(result: dict[str, object]) -> None:
    print(f"status: {result['status']}")
    print(f"spec_dir: {result['spec_dir']}")
    if result["errors"]:
        print("errors:")
        for error in result["errors"]:
            print(f"- {error}")
    if result["warnings"]:
        print("warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    if result["next_actions"]:
        print("next_actions:")
        for action in result["next_actions"]:
            print(f"- {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SpecRail artifacts.")
    parser.add_argument("--repo", default=".", help="SpecRail repository root")
    parser.add_argument("--spec-dir", required=True, help="Spec directory to evaluate")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    spec_dir = (repo / args.spec_dir).resolve()
    if not repo.is_dir():
        print(f"error: repo is not a directory: {repo}", file=sys.stderr)
        return 2
    try:
        spec_dir.relative_to(repo)
    except ValueError:
        print(f"error: spec-dir must be inside repo: {spec_dir}", file=sys.stderr)
        return 2

    result = evaluate(repo, spec_dir)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
