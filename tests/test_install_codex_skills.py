from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_skill_repo(repo: Path, name: str = "specrail-example") -> None:
    skill_text = "\n".join(
        [
            "---",
            f"name: {name}",
            "description: Example skill.",
            "---",
            "",
            "# SpecRail Example",
            "",
        ]
    )
    skill_path = repo / "skills" / name / "SKILL.md"
    write_text(skill_path, skill_text)
    digest = hashlib.sha256(skill_text.encode("utf-8")).hexdigest()
    write_text(
        repo / "skills-lock.json",
        json.dumps(
            {
                "version": 1,
                "algorithm": "sha256",
                "skills": [
                    {
                        "name": name,
                        "path": f"skills/{name}/SKILL.md",
                        "computedHash": f"sha256:{digest}",
                    }
                ],
            }
        ),
    )


def add_locked_skill(repo: Path, name: str) -> None:
    skill_text = "\n".join(
        [
            "---",
            f"name: {name}",
            "description: Another example skill.",
            "---",
            "",
            "# Another SpecRail Example",
            "",
        ]
    )
    skill_path = repo / "skills" / name / "SKILL.md"
    write_text(skill_path, skill_text)
    lock_path = repo / "skills-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(skill_text.encode("utf-8")).hexdigest()
    lock["skills"].append(
        {
            "name": name,
            "path": f"skills/{name}/SKILL.md",
            "computedHash": f"sha256:{digest}",
        }
    )
    write_text(lock_path, json.dumps(lock))


def run_installer(repo: Path, target: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "install_codex_skills.py"),
            "--repo",
            str(repo),
            "--target-dir",
            str(target),
            *extra,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_install_codex_skills_dry_run_writes_nothing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)

    result = run_installer(repo, target)

    assert result.returncode == 0
    assert "mode: dry-run" in result.stdout
    assert "no files written" in result.stdout
    assert not target.exists()


def test_install_codex_skills_apply_syncs_locked_skill(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    write_text(target / "specrail-example" / "stale.txt", "remove me")

    result = run_installer(repo, target, "--apply")

    assert result.returncode == 0
    assert "mode: apply" in result.stdout
    assert "installed 1 skills" in result.stdout
    assert (target / "specrail-example" / "SKILL.md").read_text(encoding="utf-8") == (
        repo / "skills" / "specrail-example" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert not (target / "specrail-example" / "stale.txt").exists()


def test_install_codex_skills_refuses_source_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_skill_repo(repo)

    result = run_installer(repo, repo / "skills", "--apply")

    assert result.returncode == 1
    assert "refusing to install over source skill directory" in result.stderr


def test_check_installed_returns_zero_when_all_hashes_match(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    assert run_installer(repo, target, "--apply").returncode == 0

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 0
    assert "mode: check-installed (read-only)" in result.stdout
    assert "specrail-example: match" in result.stdout
    assert "all 1 installed skills match skills-lock.json" in result.stdout


def test_check_installed_reports_all_missing_and_drift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    add_locked_skill(repo, "specrail-missing")
    write_text(target / "specrail-example" / "SKILL.md", "locally changed\n")

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 1
    assert "specrail-example: drift" in result.stdout
    assert "specrail-missing: missing" in result.stdout
    assert "rerun this installer with --apply" in result.stderr
    assert "restart Codex" in result.stderr
    assert not (target / "specrail-missing").exists()


def test_check_installed_and_apply_are_mutually_exclusive(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)

    result = run_installer(repo, target, "--apply", "--check-installed")

    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr
    assert not target.exists()
