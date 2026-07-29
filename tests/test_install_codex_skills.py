from __future__ import annotations

import hashlib
import json
import os
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
                "profiles": {
                    "core": [name],
                    "heavy": [name],
                    "all": [name],
                },
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
    lock["skills"].sort(key=lambda item: item["path"])
    for profile in lock["profiles"].values():
        profile.append(name)
        profile.sort()
    write_text(lock_path, json.dumps(lock))


def write_profiled_skill_repo(repo: Path) -> None:
    write_skill_repo(repo, "specrail")
    add_locked_skill(repo, "specrail-heavy")
    add_locked_skill(repo, "implx")
    lock_path = repo / "skills-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["profiles"] = {
        "core": ["specrail"],
        "heavy": ["specrail", "specrail-heavy"],
        "all": ["implx", "specrail", "specrail-heavy"],
    }
    write_text(lock_path, json.dumps(lock))


def run_installer(
    repo: Path,
    target: Path,
    *extra: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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
        env=env,
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


def test_repository_catalog_exposes_only_three_explicit_entrypoints() -> None:
    skill_dirs = {
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir()
    }
    lock = json.loads((ROOT / "skills-lock.json").read_text(encoding="utf-8"))

    assert skill_dirs == {"specrail", "specrail-heavy", "implx"}
    assert lock["profiles"] == {
        "core": ["specrail"],
        "heavy": ["specrail", "specrail-heavy"],
        "all": ["implx", "specrail", "specrail-heavy"],
    }
    for name in skill_dirs:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        description = next(
            line for line in text.splitlines() if line.startswith("description:")
        )
        assert description.startswith("description: Use only when the user explicitly")
    core = (ROOT / "skills" / "specrail" / "SKILL.md").read_text(encoding="utf-8")
    assert "Never use for SpecRail Heavy, implx, or ordinary coding tasks" in core


def test_repository_default_install_registers_only_specrail(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"

    result = run_installer(ROOT, target, "--apply")

    assert result.returncode == 0
    assert "profile: core" in result.stdout
    assert {path.name for path in target.iterdir()} == {"specrail"}


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


def test_default_core_profile_installs_only_core_skill(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)

    result = run_installer(repo, target, "--apply")

    assert result.returncode == 0
    assert "profile: core" in result.stdout
    assert (target / "specrail" / "SKILL.md").is_file()
    assert not (target / "specrail-heavy").exists()
    assert not (target / "implx").exists()


def test_heavy_profile_installs_core_and_heavy_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)

    result = run_installer(repo, target, "--profile", "heavy", "--apply")

    assert result.returncode == 0
    assert "profile: heavy" in result.stdout
    assert (target / "specrail" / "SKILL.md").is_file()
    assert (target / "specrail-heavy" / "SKILL.md").is_file()
    assert not (target / "implx").exists()


def test_all_profile_installs_every_locked_skill(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)

    result = run_installer(repo, target, "--profile", "all", "--apply")

    assert result.returncode == 0
    assert "profile: all" in result.stdout
    for name in ("specrail", "specrail-heavy", "implx"):
        assert (target / name / "SKILL.md").is_file()


def test_switching_from_all_to_core_removes_only_stale_managed_skills(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)
    assert (
        run_installer(repo, target, "--profile", "all", "--apply").returncode
        == 0
    )
    write_text(target / "user-owned" / "SKILL.md", "keep me\n")

    result = run_installer(repo, target, "--profile", "core", "--apply")

    assert result.returncode == 0
    assert "remove stale managed skill" in result.stdout
    assert "installed 1 skills" in result.stdout
    assert "removed 2 stale managed skills" in result.stdout
    assert (target / "specrail" / "SKILL.md").is_file()
    assert not (target / "specrail-heavy").exists()
    assert not (target / "implx").exists()
    assert (target / "user-owned" / "SKILL.md").read_text() == "keep me\n"


def test_apply_removes_legacy_managed_skill_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)
    write_text(target / "specrail-workflow" / "SKILL.md", "legacy router\n")
    write_text(target / "specrail-install" / "SKILL.md", "legacy installer\n")
    write_text(target / "user-owned" / "SKILL.md", "keep me\n")

    result = run_installer(repo, target, "--profile", "core", "--apply")

    assert result.returncode == 0
    assert "removed 2 stale managed skills" in result.stdout
    assert not (target / "specrail-workflow").exists()
    assert not (target / "specrail-install").exists()
    assert (target / "user-owned" / "SKILL.md").read_text() == "keep me\n"


def test_profile_switch_dry_run_does_not_remove_stale_skills(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)
    assert (
        run_installer(repo, target, "--profile", "all", "--apply").returncode
        == 0
    )

    result = run_installer(repo, target, "--profile", "core")

    assert result.returncode == 0
    assert "remove stale managed skill" in result.stdout
    assert (target / "specrail-heavy" / "SKILL.md").is_file()
    assert (target / "implx" / "SKILL.md").is_file()


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
    assert "status: match" in result.stdout
    assert "specrail-example: match" in result.stdout
    assert "expected sha256:" in result.stdout
    assert "actual sha256:" in result.stdout
    assert f"path {target / 'specrail-example' / 'SKILL.md'}" in result.stdout
    assert "all 1 installed skills match skills-lock.json" in result.stdout


def test_check_installed_skips_absent_target_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "not-installed"
    write_skill_repo(repo)

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 0
    assert "status: not_installed" in result.stdout
    assert "target root is absent; installed-copy check skipped" in result.stdout
    assert not target.exists()


def test_check_installed_reports_all_missing_and_drift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    add_locked_skill(repo, "specrail-missing")
    write_text(target / "specrail-example" / "SKILL.md", "locally changed\n")

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 1
    assert "status: invalid" in result.stdout
    assert "specrail-example: drift" in result.stdout
    assert "expected sha256:" in result.stdout
    assert "actual sha256:" in result.stdout
    assert "specrail-missing: missing" in result.stdout
    assert "actual missing" in result.stdout
    assert "rerun this installer with --apply" in result.stderr
    assert "restart Codex" in result.stderr
    assert not (target / "specrail-missing").exists()


def test_check_installed_reports_unselected_managed_skill_as_stale(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_profiled_skill_repo(repo)
    assert (
        run_installer(repo, target, "--profile", "all", "--apply").returncode
        == 0
    )

    result = run_installer(repo, target, "--profile", "core", "--check-installed")

    assert result.returncode == 1
    assert "specrail: match" in result.stdout
    assert "specrail-heavy: stale" in result.stdout
    assert "implx: stale" in result.stdout


def test_check_installed_rejects_symlink_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    outside = tmp_path / "outside" / "specrail-example"
    write_skill_repo(repo)
    write_text(outside / "SKILL.md", "outside\n")
    target.mkdir()
    (target / "specrail-example").symlink_to(outside, target_is_directory=True)

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 1
    assert "specrail-example: unsafe" in result.stdout
    assert "symbolic links are not accepted" in result.stdout
    assert "outside" not in result.stdout


def test_check_installed_rejects_broken_target_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    target.symlink_to(tmp_path / "missing-target", target_is_directory=True)

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 1
    assert "status: invalid" in result.stdout
    assert "specrail-example: unsafe" in result.stdout
    assert "target root must be a real directory" in result.stdout


def test_check_installed_reports_multiple_drift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    add_locked_skill(repo, "specrail-second")
    write_text(target / "specrail-example" / "SKILL.md", "first drift\n")
    write_text(target / "specrail-second" / "SKILL.md", "second drift\n")

    result = run_installer(repo, target, "--check-installed")

    assert result.returncode == 1
    assert result.stdout.count(": drift") == 2
    assert result.stdout.count("actual sha256:") == 2


def test_check_installed_uses_codex_home_when_target_is_not_explicit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home"
    target = codex_home / "skills"
    write_skill_repo(repo)
    assert run_installer(repo, target, "--apply").returncode == 0
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(codex_home)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "install_codex_skills.py"),
            "--repo",
            str(repo),
            "--check-installed",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0
    assert f"target: {target}" in result.stdout
    assert "specrail-example: match" in result.stdout


def test_check_installed_uses_home_fallback_when_codex_home_is_unset(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    user_home = tmp_path / "user-home"
    target = user_home / ".codex" / "skills"
    write_skill_repo(repo)
    assert run_installer(repo, target, "--apply").returncode == 0
    environment = dict(os.environ)
    environment.pop("CODEX_HOME", None)
    environment["HOME"] = str(user_home)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "install_codex_skills.py"),
            "--repo",
            str(repo),
            "--check-installed",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0
    assert f"target: {target}" in result.stdout
    assert "specrail-example: match" in result.stdout


def test_check_installed_does_not_modify_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)
    assert run_installer(repo, target, "--apply").returncode == 0
    installed_file = target / "specrail-example" / "SKILL.md"
    before_bytes = installed_file.read_bytes()
    before_stat = installed_file.stat()

    result = run_installer(repo, target, "--check-installed")

    after_stat = installed_file.stat()
    assert result.returncode == 0
    assert installed_file.read_bytes() == before_bytes
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    assert after_stat.st_ctime_ns == before_stat.st_ctime_ns


def test_check_installed_and_apply_are_mutually_exclusive(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    write_skill_repo(repo)

    result = run_installer(repo, target, "--apply", "--check-installed")

    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr
    assert not target.exists()
