from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CHECKS))

from check_workflow import validate_spec_packet, validate_task_plan  # noqa: E402
from evaluate import evaluate_rclean_smoke  # noqa: E402


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_task_plan_rejects_duplicate_ids(tmp_path: Path) -> None:
    task_path = tmp_path / "specs" / "GH5" / "tasks.md"
    write_text(
        task_path,
        "\n".join(
            [
                "- [ ] `SP5-T001` Owner: `docs` | Done when: done | Verify: review",
                "- [ ] `SP5-T001` Owner: `tests` | Done when: done | Verify: pytest",
            ]
        ),
    )

    errors = validate_task_plan(task_path, "5")

    assert any("duplicate task ID SP5-T001" in error for error in errors)


def test_task_plan_requires_done_when_and_verify(tmp_path: Path) -> None:
    task_path = tmp_path / "specs" / "GH5" / "tasks.md"
    write_text(
        task_path,
        "- [ ] `SP5-T001` Owner: `tests` | Details: malformed task",
    )

    errors = validate_task_plan(task_path, "5")

    assert any("missing Done when:" in error for error in errors)
    assert any("missing Verify:" in error for error in errors)


def test_spec_packet_requires_tasks_md(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs" / "GH5"
    write_text(spec_dir / "product.md", "GitHub issue: `#5`\n")
    write_text(spec_dir / "tech.md", "GitHub issue: `#5`\n")

    errors = validate_spec_packet(spec_dir)

    assert any("missing tasks.md" in error for error in errors)


def test_rclean_smoke_requires_all_scenarios(tmp_path: Path) -> None:
    smoke = tmp_path / "examples" / "rclean-smoke.md"
    write_text(
        smoke,
        "\n".join(
            [
                "Scope: read-only. Do not modify `/Users/lifcc/Desktop/code/AI/tool/rclean`.",
                "cargo fmt -- --check",
                "cargo clippy --all-targets --all-features -- -D warnings",
                "cargo test",
                "cargo build --release",
                "rustup run 1.95 cargo build",
                "rustup run 1.95 cargo test",
                "rclean.new_rule_spec_first",
                "rclean.security_boundary_gate",
                "rclean.doc_only_direct",
                "rclean.ci_command_mapping",
                "drafts/rclean-issues-draft-2026-05-25.md",
                "NOT SUBMITTED YET",
            ]
        ),
    )

    checks, errors, warnings = evaluate_rclean_smoke(tmp_path)

    assert any(check["id"] == "rclean_smoke.scenarios_present" for check in checks)
    assert any("rclean.issue_dedupe" in error for error in errors)
    assert any("human review" in warning for warning in warnings)


def test_evaluate_json_contract_for_gh5() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "evaluate.py",
            "--repo",
            ".",
            "--spec-dir",
            "specs/GH5",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert {
        "status",
        "repo",
        "spec_dir",
        "checks",
        "artifacts",
        "errors",
        "warnings",
        "next_actions",
    } <= set(payload)
    assert payload["status"] == "needs_human"
    assert payload["errors"] == []
