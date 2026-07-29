#!/usr/bin/env python3
"""Install repo-distributed SpecRail skills into a local Codex skill directory.

The command is dry-run by default. Use --apply only after a human explicitly
requests local Codex skill installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


INSTALL_PROFILES = ("core", "heavy", "all")
LEGACY_MANAGED_SKILLS = frozenset(
    {
        "specrail-check-impl-against-spec",
        "specrail-diagnose-ci",
        "specrail-implement",
        "specrail-implement-queue",
        "specrail-install",
        "specrail-plan-tasks",
        "specrail-release-note",
        "specrail-review-pr",
        "specrail-triage-issue",
        "specrail-workflow",
        "specrail-write-product-spec",
        "specrail-write-tech-spec",
    }
)


class InstallError(ValueError):
    """Raised when the local skill install plan is unsafe or invalid."""


@dataclass(frozen=True)
class LockedSkill:
    name: str
    source_dir: Path
    expected_hash: str


@dataclass(frozen=True)
class InstalledCheck:
    messages: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class InstallResult:
    messages: tuple[str, ...]
    installed_count: int
    removed_count: int


@dataclass(frozen=True)
class SkillCatalog:
    skills: tuple[LockedSkill, ...]
    profiles: dict[str, tuple[str, ...]]

    def selected(self, profile: str) -> tuple[LockedSkill, ...]:
        selected_names = set(self.profiles[profile])
        return tuple(skill for skill in self.skills if skill.name in selected_names)

    def managed_names(self) -> set[str]:
        return {skill.name for skill in self.skills} | set(LEGACY_MANAGED_SKILLS)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InstallError(f"cannot read {path}: {exc}") from exc


def parse_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            return None
        metadata[key.strip()] = value.strip()
    return metadata


def validate_skills_lock(repo: Path) -> list[str]:
    """Validate installer inputs without depending on the removed check layer."""
    lock_path = repo / "skills-lock.json"
    if not lock_path.is_file():
        return ["missing required file: skills-lock.json"]
    try:
        lock = json.loads(read_text(lock_path))
    except json.JSONDecodeError as exc:
        return [f"skills-lock.json: invalid JSON: {exc.msg}"]
    if not isinstance(lock, dict):
        return ["skills-lock.json: top-level value must be an object"]

    errors: list[str] = []
    if lock.get("version") != 1:
        errors.append("skills-lock.json: version must be 1")
    if lock.get("algorithm") != "sha256":
        errors.append("skills-lock.json: algorithm must be sha256")

    skills = lock.get("skills")
    if not isinstance(skills, list) or not skills:
        errors.append("skills-lock.json: skills must be a non-empty list")
        return errors

    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    ordered_paths: list[str] = []
    for index, item in enumerate(skills, start=1):
        if not isinstance(item, dict):
            errors.append(f"skills-lock.json: skill #{index} must be an object")
            continue
        name = item.get("name")
        relative = item.get("path")
        expected_hash = item.get("computedHash")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"skills-lock.json: skill #{index} missing name")
            continue
        if not isinstance(relative, str) or not relative.strip():
            errors.append(f"skills-lock.json: skill {name} missing path")
            continue
        if name in seen_names:
            errors.append(f"skills-lock.json: duplicate skill name {name}")
        if relative in seen_paths:
            errors.append(f"skills-lock.json: duplicate skill path {relative}")
        seen_names.add(name)
        seen_paths.add(relative)
        ordered_paths.append(relative)

        path = Path(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) != 3
            or path.parts[0] != "skills"
            or path.parts[1] != name
            or path.name != "SKILL.md"
        ):
            errors.append(
                f"skills-lock.json: skill {name} path must be "
                f"skills/{name}/SKILL.md"
            )
            continue

        skill_path = repo / path
        if not skill_path.is_file():
            errors.append(f"skills-lock.json: skill file does not exist: {relative}")
            continue
        metadata = parse_frontmatter(read_text(skill_path))
        if metadata is None:
            errors.append(f"{relative}: missing YAML frontmatter")
        elif set(metadata) != {"name", "description"}:
            errors.append(
                f"{relative}: frontmatter must contain only name and description"
            )
        else:
            if metadata["name"] != name:
                errors.append(f"{relative}: frontmatter name must be {name}")
            if not metadata["description"]:
                errors.append(f"{relative}: description must not be empty")

        actual_hash = hashlib.sha256(skill_path.read_bytes()).hexdigest()
        if not isinstance(expected_hash, str) or not expected_hash.startswith(
            "sha256:"
        ):
            errors.append(
                f"skills-lock.json: skill {name} computedHash must start with sha256:"
            )
        elif expected_hash[7:] != actual_hash:
            errors.append(f"skills-lock.json: skill {name} computedHash mismatch")

    if ordered_paths != sorted(ordered_paths):
        errors.append("skills-lock.json: skills must be sorted by path")

    skill_files = {
        str(path.relative_to(repo))
        for path in sorted((repo / "skills").glob("*/SKILL.md"))
    }
    for relative in sorted(skill_files - seen_paths):
        errors.append(f"skills-lock.json: missing skill file {relative}")
    for relative in sorted(seen_paths - skill_files):
        errors.append(f"skills-lock.json: locked skill file missing from repo {relative}")

    profiles = lock.get("profiles")
    if not isinstance(profiles, dict):
        errors.append("skills-lock.json: profiles must be an object")
        return errors
    if set(profiles) != set(INSTALL_PROFILES):
        errors.append(
            "skills-lock.json: profiles must contain exactly core, heavy, and all"
        )
        return errors

    normalized_profiles: dict[str, list[str]] = {}
    for profile in INSTALL_PROFILES:
        names = profiles.get(profile)
        if not isinstance(names, list) or not names:
            errors.append(
                f"skills-lock.json: profile {profile} must be a non-empty list"
            )
            continue
        if not all(isinstance(name, str) and name for name in names):
            errors.append(
                f"skills-lock.json: profile {profile} names must be non-empty strings"
            )
            continue
        if len(names) != len(set(names)):
            errors.append(
                f"skills-lock.json: profile {profile} contains duplicate names"
            )
        if names != sorted(names):
            errors.append(
                f"skills-lock.json: profile {profile} names must be sorted"
            )
        unknown = sorted(set(names) - seen_names)
        for name in unknown:
            errors.append(
                f"skills-lock.json: profile {profile} references unknown skill {name}"
            )
        normalized_profiles[profile] = names

    core = set(normalized_profiles.get("core", []))
    heavy = set(normalized_profiles.get("heavy", []))
    all_profile = set(normalized_profiles.get("all", []))
    if not core <= heavy:
        errors.append("skills-lock.json: core profile must be a subset of heavy")
    if not heavy <= all_profile:
        errors.append("skills-lock.json: heavy profile must be a subset of all")
    if all_profile != seen_names:
        errors.append(
            "skills-lock.json: all profile must contain every locked skill exactly once"
        )
    return errors


def default_codex_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "skills"


def load_skill_catalog(repo: Path) -> SkillCatalog:
    errors = validate_skills_lock(repo)
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise InstallError(f"invalid skills-lock.json:\n{details}")

    lock = json.loads(read_text(repo / "skills-lock.json"))
    skills: list[LockedSkill] = []
    for item in lock["skills"]:
        rel_path = Path(item["path"])
        skills.append(
            LockedSkill(
                name=item["name"],
                source_dir=repo / rel_path.parent,
                expected_hash=item["computedHash"],
            )
        )
    return SkillCatalog(
        skills=tuple(skills),
        profiles={
            profile: tuple(lock["profiles"][profile])
            for profile in INSTALL_PROFILES
        },
    )


def ensure_safe_destination(source_dir: Path, destination_dir: Path) -> None:
    if destination_dir.is_symlink():
        raise InstallError(
            f"refusing symbolic-link skill destination: {destination_dir}"
        )
    if destination_dir.exists() and not destination_dir.is_dir():
        raise InstallError(
            f"refusing non-directory skill destination: {destination_dir}"
        )
    source = source_dir.resolve()
    destination = destination_dir.resolve()
    if source == destination:
        raise InstallError(f"refusing to install over source skill directory: {source}")
    if source in destination.parents:
        raise InstallError(f"refusing to install inside source skill directory: {destination}")
    if destination in source.parents:
        raise InstallError(f"refusing to install into source parent directory: {destination}")


def install_skills(
    repo: Path,
    target_dir: Path,
    apply: bool,
    profile: str,
) -> InstallResult:
    repo = repo.resolve()
    target_dir = target_dir.expanduser()
    catalog = load_skill_catalog(repo)
    skills = catalog.selected(profile)
    selected_names = {skill.name for skill in skills}
    stale_destinations = [
        target_dir / name
        for name in sorted(catalog.managed_names() - selected_names)
        if (target_dir / name).exists() or (target_dir / name).is_symlink()
    ]
    messages: list[str] = []

    for skill in skills:
        destination = target_dir / skill.name
        ensure_safe_destination(skill.source_dir, destination)
        messages.append(f"{skill.name}: {skill.source_dir} -> {destination}")
    for destination in stale_destinations:
        if destination.is_symlink() or not destination.is_dir():
            raise InstallError(
                f"refusing unsafe stale managed skill destination: {destination}"
            )
        messages.append(f"remove stale managed skill: {destination}")

    if apply:
        try:
            for skill in skills:
                destination = target_dir / skill.name
                if destination.exists():
                    shutil.rmtree(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(skill.source_dir, destination)

            for skill in skills:
                installed_file = target_dir / skill.name / "SKILL.md"
                if not installed_file.is_file():
                    raise InstallError(
                        f"installed skill missing SKILL.md: {installed_file}"
                    )
                digest = (
                    "sha256:"
                    + hashlib.sha256(installed_file.read_bytes()).hexdigest()
                )
                if digest != skill.expected_hash:
                    raise InstallError(
                        f"installed skill hash mismatch for {skill.name}: "
                        f"expected {skill.expected_hash}, got {digest}"
                    )

            for destination in stale_destinations:
                shutil.rmtree(destination)
        except OSError as exc:
            raise InstallError(
                f"cannot apply profile {profile} to {target_dir}: {exc}"
            ) from exc
    return InstallResult(
        messages=tuple(messages),
        installed_count=len(skills),
        removed_count=len(stale_destinations),
    )


def check_installed_skills(
    repo: Path,
    target_dir: Path,
    profile: str,
) -> InstalledCheck:
    """Compare installed skills with the lock without following unsafe links."""
    catalog = load_skill_catalog(repo.resolve())
    skills = catalog.selected(profile)
    target_dir = target_dir.expanduser()

    if not target_dir.exists() and not target_dir.is_symlink():
        return InstalledCheck(messages=(), status="not_installed")

    messages: list[str] = []
    invalid = False
    target_is_unsafe = target_dir.is_symlink() or not target_dir.is_dir()
    target_root = target_dir.resolve()

    for skill in skills:
        skill_dir = target_dir / skill.name
        installed_file = skill_dir / "SKILL.md"
        common = (
            f"expected {skill.expected_hash}, "
            f"path {installed_file}"
        )

        if target_is_unsafe:
            invalid = True
            messages.append(
                f"{skill.name}: unsafe ({common}, actual unavailable, "
                "target root must be a real directory)"
            )
            continue
        if skill_dir.is_symlink() or installed_file.is_symlink():
            invalid = True
            messages.append(
                f"{skill.name}: unsafe ({common}, actual unavailable, "
                "symbolic links are not accepted)"
            )
            continue
        if not installed_file.is_file():
            invalid = True
            messages.append(
                f"{skill.name}: missing ({common}, actual missing)"
            )
            continue

        try:
            resolved_file = installed_file.resolve(strict=True)
            resolved_file.relative_to(target_root)
            resolved_file.relative_to(skill_dir.resolve(strict=True))
            digest = (
                "sha256:"
                + hashlib.sha256(installed_file.read_bytes()).hexdigest()
            )
        except (OSError, ValueError) as exc:
            invalid = True
            messages.append(
                f"{skill.name}: unsafe ({common}, actual unavailable, "
                f"cannot safely read installed file: {exc})"
            )
            continue

        if digest != skill.expected_hash:
            invalid = True
            messages.append(
                f"{skill.name}: drift ({common}, actual {digest})"
            )
            continue
        messages.append(
            f"{skill.name}: match ({common}, actual {digest})"
        )

    selected_names = {skill.name for skill in skills}
    for name in sorted(catalog.managed_names() - selected_names):
        installed_dir = target_dir / name
        if not installed_dir.exists() and not installed_dir.is_symlink():
            continue
        invalid = True
        messages.append(
            f"{name}: stale (path {installed_dir}, "
            f"not selected by profile {profile})"
        )

    return InstalledCheck(
        messages=tuple(messages),
        status="invalid" if invalid else "match",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install SpecRail repo-distributed skills into local Codex skills.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="SpecRail repository root. Defaults to current directory.",
    )
    parser.add_argument(
        "--target-dir",
        default=str(default_codex_skills_dir()),
        help="Codex skills directory. Defaults to $CODEX_HOME/skills or ~/.codex/skills.",
    )
    parser.add_argument(
        "--profile",
        choices=INSTALL_PROFILES,
        default="core",
        help="Install/check profile. Defaults to core.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write files. Without this flag the command is a dry-run.",
    )
    mode.add_argument(
        "--check-installed",
        action="store_true",
        help="Read only: report missing or drifted installed SKILL.md files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo = Path(args.repo).expanduser()
    target_dir = Path(args.target_dir).expanduser()

    try:
        if args.check_installed:
            installed_check = check_installed_skills(
                repo,
                target_dir,
                args.profile,
            )
        else:
            install_result = install_skills(
                repo,
                target_dir,
                args.apply,
                args.profile,
            )
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.check_installed:
        print("mode: check-installed (read-only)")
        print(f"profile: {args.profile}")
        print(f"target: {target_dir}")
        print(f"status: {installed_check.status}")
        if installed_check.status == "not_installed":
            print("target root is absent; installed-copy check skipped")
            return 0
        for message in installed_check.messages:
            print(message)
        if installed_check.status != "match":
            print(
                "repair: rerun this installer with --apply, then restart Codex "
                "to load the reinstalled skills",
                file=sys.stderr,
            )
            return 1
        print(
            f"all {len(installed_check.messages)} installed skills "
            "match skills-lock.json"
        )
        return 0

    mode = "apply" if args.apply else "dry-run"
    print(f"mode: {mode}")
    print(f"profile: {args.profile}")
    print(f"target: {target_dir}")
    for message in install_result.messages:
        print(message)
    if args.apply:
        print(f"installed {install_result.installed_count} skills")
        if install_result.removed_count:
            print(
                f"removed {install_result.removed_count} "
                "stale managed skills"
            )
    else:
        print("no files written; rerun with --apply to install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
