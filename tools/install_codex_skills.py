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


class InstallError(ValueError):
    """Raised when the local skill install plan is unsafe or invalid."""


@dataclass(frozen=True)
class LockedSkill:
    name: str
    source_dir: Path
    expected_hash: str


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
    return errors


def default_codex_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "skills"


def load_locked_skills(repo: Path) -> list[LockedSkill]:
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
    return skills


def ensure_safe_destination(source_dir: Path, destination_dir: Path) -> None:
    source = source_dir.resolve()
    destination = destination_dir.resolve()
    if source == destination:
        raise InstallError(f"refusing to install over source skill directory: {source}")
    if source in destination.parents:
        raise InstallError(f"refusing to install inside source skill directory: {destination}")
    if destination in source.parents:
        raise InstallError(f"refusing to install into source parent directory: {destination}")


def install_skills(repo: Path, target_dir: Path, apply: bool) -> list[str]:
    repo = repo.resolve()
    target_dir = target_dir.expanduser()
    skills = load_locked_skills(repo)
    messages: list[str] = []

    for skill in skills:
        destination = target_dir / skill.name
        ensure_safe_destination(skill.source_dir, destination)
        messages.append(f"{skill.name}: {skill.source_dir} -> {destination}")
        if not apply:
            continue
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.source_dir, destination)

    if apply:
        installed_repo = target_dir
        for skill in skills:
            installed_file = installed_repo / skill.name / "SKILL.md"
            if not installed_file.is_file():
                raise InstallError(f"installed skill missing SKILL.md: {installed_file}")
            digest = "sha256:" + hashlib.sha256(installed_file.read_bytes()).hexdigest()
            if digest != skill.expected_hash:
                raise InstallError(
                    f"installed skill hash mismatch for {skill.name}: "
                    f"expected {skill.expected_hash}, got {digest}"
                )
    return messages


def check_installed_skills(repo: Path, target_dir: Path) -> tuple[list[str], bool]:
    """Compare every installed SKILL.md with its locked source hash."""
    skills = load_locked_skills(repo.resolve())
    messages: list[str] = []
    matches = True

    for skill in skills:
        installed_file = target_dir.expanduser() / skill.name / "SKILL.md"
        if not installed_file.is_file():
            matches = False
            messages.append(f"{skill.name}: missing ({installed_file})")
            continue

        digest = "sha256:" + hashlib.sha256(installed_file.read_bytes()).hexdigest()
        if digest != skill.expected_hash:
            matches = False
            messages.append(
                f"{skill.name}: drift "
                f"(expected {skill.expected_hash}, got {digest})"
            )
            continue
        messages.append(f"{skill.name}: match")

    return messages, matches


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
            messages, matches = check_installed_skills(repo, target_dir)
        else:
            messages = install_skills(repo, target_dir, args.apply)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.check_installed:
        print("mode: check-installed (read-only)")
        print(f"target: {target_dir}")
        for message in messages:
            print(message)
        if not matches:
            print(
                "repair: rerun this installer with --apply, then restart Codex "
                "to load the reinstalled skills",
                file=sys.stderr,
            )
            return 1
        print(f"all {len(messages)} installed skills match skills-lock.json")
        return 0

    mode = "apply" if args.apply else "dry-run"
    print(f"mode: {mode}")
    print(f"target: {target_dir}")
    for message in messages:
        print(message)
    if args.apply:
        print(f"installed {len(messages)} skills")
    else:
        print("no files written; rerun with --apply to install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
