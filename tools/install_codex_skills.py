#!/usr/bin/env python3
"""Install repo-distributed SpecRail skills into a local Codex skill directory.

The command is dry-run by default. Use --apply only after a human explicitly
requests local Codex skill installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


INSTALL_PROFILES = ("core", "heavy", "all")
LEGACY_MANAGED_SKILLS = frozenset(
    {
        "implement-specrail-issues",
        "specrail-check-impl-against-spec",
        "specrail-diagnose-ci",
        "specrail-implement",
        "specrail-implement-queue",
        "specrail-install",
        "specrail-plan-tasks",
        "specrail-pr-gate",
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
class LockedFile:
    relative_path: Path
    expected_hash: str


@dataclass(frozen=True)
class LockedSkill:
    name: str
    source_dir: Path
    files: tuple[LockedFile, ...]


@dataclass(frozen=True)
class InstalledCheck:
    messages: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class InstallResult:
    messages: tuple[str, ...]
    installed_count: int
    removed_count: int
    archived_count: int


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
    if lock.get("version") != 2:
        errors.append("skills-lock.json: version must be 2")
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
        metadata_relative = item.get("agentMetadataPath")
        metadata_expected_hash = item.get("agentMetadataHash")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"skills-lock.json: skill #{index} missing name")
            continue
        if not isinstance(relative, str) or not relative.strip():
            errors.append(f"skills-lock.json: skill {name} missing path")
            continue
        if not isinstance(metadata_relative, str) or not metadata_relative.strip():
            errors.append(
                f"skills-lock.json: skill {name} missing agentMetadataPath"
            )
            continue
        if name in seen_names:
            errors.append(f"skills-lock.json: duplicate skill name {name}")
        for declared_path in (relative, metadata_relative):
            if declared_path in seen_paths:
                errors.append(
                    f"skills-lock.json: duplicate skill path {declared_path}"
                )
            seen_paths.add(declared_path)
        seen_names.add(name)
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

        metadata_path = Path(metadata_relative)
        if (
            metadata_path.is_absolute()
            or ".." in metadata_path.parts
            or metadata_path.parts
            != ("skills", name, "agents", "openai.yaml")
        ):
            errors.append(
                f"skills-lock.json: skill {name} agentMetadataPath must be "
                f"skills/{name}/agents/openai.yaml"
            )
            continue

        metadata_file = repo / metadata_path
        if not metadata_file.is_file():
            errors.append(
                "skills-lock.json: agent metadata file does not exist: "
                f"{metadata_relative}"
            )
            continue
        metadata_text = read_text(metadata_file)
        if "interface:\n" not in metadata_text:
            errors.append(f"{metadata_relative}: interface mapping is required")
        if "  display_name:" not in metadata_text:
            errors.append(f"{metadata_relative}: interface.display_name is required")
        if "  short_description:" not in metadata_text:
            errors.append(
                f"{metadata_relative}: interface.short_description is required"
            )
        if "policy:\n  allow_implicit_invocation: false\n" not in metadata_text:
            errors.append(
                f"{metadata_relative}: implicit invocation must be disabled"
            )
        metadata_actual_hash = hashlib.sha256(metadata_file.read_bytes()).hexdigest()
        if not isinstance(
            metadata_expected_hash, str
        ) or not metadata_expected_hash.startswith("sha256:"):
            errors.append(
                f"skills-lock.json: skill {name} agentMetadataHash must start "
                "with sha256:"
            )
        elif metadata_expected_hash[7:] != metadata_actual_hash:
            errors.append(
                f"skills-lock.json: skill {name} agentMetadataHash mismatch"
            )

    if ordered_paths != sorted(ordered_paths):
        errors.append("skills-lock.json: skills must be sorted by path")

    source_files = {
        str(path.relative_to(repo))
        for path in sorted((repo / "skills").glob("*/SKILL.md"))
    }
    source_files.update(
        str(path.relative_to(repo))
        for path in sorted((repo / "skills").glob("*/agents/openai.yaml"))
    )
    for relative in sorted(source_files - seen_paths):
        errors.append(f"skills-lock.json: missing locked file {relative}")
    for relative in sorted(seen_paths - source_files):
        errors.append(f"skills-lock.json: locked file missing from repo {relative}")

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


def default_user_skills_dir() -> Path:
    return Path.home() / ".agents" / "skills"


def load_skill_catalog(repo: Path) -> SkillCatalog:
    errors = validate_skills_lock(repo)
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise InstallError(f"invalid skills-lock.json:\n{details}")

    lock = json.loads(read_text(repo / "skills-lock.json"))
    skills: list[LockedSkill] = []
    for item in lock["skills"]:
        rel_path = Path(item["path"])
        metadata_path = Path(item["agentMetadataPath"])
        skill_root = Path("skills") / item["name"]
        skills.append(
            LockedSkill(
                name=item["name"],
                source_dir=repo / skill_root,
                files=(
                    LockedFile(
                        relative_path=rel_path.relative_to(skill_root),
                        expected_hash=item["computedHash"],
                    ),
                    LockedFile(
                        relative_path=metadata_path.relative_to(skill_root),
                        expected_hash=item["agentMetadataHash"],
                    ),
                ),
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
    legacy_target_dirs: tuple[Path, ...] = (),
    legacy_archive_dir: Path | None = None,
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
    legacy_destinations: list[Path] = []
    target_root = target_dir.resolve()
    for legacy_target_dir in legacy_target_dirs:
        legacy_target_dir = legacy_target_dir.expanduser()
        if legacy_target_dir.resolve() == target_root:
            raise InstallError(
                "legacy target directory must differ from install target: "
                f"{legacy_target_dir}"
            )
        if legacy_target_dir.is_symlink():
            raise InstallError(
                f"refusing symbolic-link legacy target: {legacy_target_dir}"
            )
        legacy_destinations.extend(
            legacy_target_dir / name
            for name in sorted(catalog.managed_names())
            if (legacy_target_dir / name).exists()
            or (legacy_target_dir / name).is_symlink()
        )
    archive_destinations: dict[Path, Path] = {}
    if legacy_archive_dir is not None:
        legacy_archive_dir = legacy_archive_dir.expanduser()
        if legacy_archive_dir.is_symlink():
            raise InstallError(
                f"refusing symbolic-link legacy archive: {legacy_archive_dir}"
            )
        for destination in legacy_destinations:
            archive_destination = legacy_archive_dir / destination.name
            if archive_destination.exists() or archive_destination.is_symlink():
                raise InstallError(
                    f"refusing to overwrite legacy archive: {archive_destination}"
                )
            archive_destinations[destination] = archive_destination
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
    for destination in legacy_destinations:
        if destination.is_symlink() or not destination.is_dir():
            raise InstallError(
                f"refusing unsafe legacy managed skill destination: {destination}"
            )
        archive_destination = archive_destinations.get(destination)
        if archive_destination is None:
            messages.append(f"remove legacy managed skill: {destination}")
        else:
            messages.append(
                f"archive legacy managed skill: {destination} -> "
                f"{archive_destination}"
            )

    if apply:
        try:
            for skill in skills:
                destination = target_dir / skill.name
                if destination.exists():
                    shutil.rmtree(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(skill.source_dir, destination)

            for skill in skills:
                for locked_file in skill.files:
                    installed_file = (
                        target_dir / skill.name / locked_file.relative_path
                    )
                    if not installed_file.is_file():
                        raise InstallError(
                            f"installed skill file missing: {installed_file}"
                        )
                    digest = (
                        "sha256:"
                        + hashlib.sha256(installed_file.read_bytes()).hexdigest()
                    )
                    if digest != locked_file.expected_hash:
                        raise InstallError(
                            f"installed file hash mismatch for {skill.name}/"
                            f"{locked_file.relative_path}: expected "
                            f"{locked_file.expected_hash}, got {digest}"
                        )

            for destination in stale_destinations:
                shutil.rmtree(destination)
            for destination in legacy_destinations:
                archive_destination = archive_destinations.get(destination)
                if archive_destination is None:
                    shutil.rmtree(destination)
                else:
                    archive_destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(destination, archive_destination)
        except OSError as exc:
            raise InstallError(
                f"cannot apply profile {profile} to {target_dir}: {exc}"
            ) from exc
    return InstallResult(
        messages=tuple(messages),
        installed_count=len(skills),
        removed_count=(
            len(stale_destinations)
            + len(legacy_destinations)
            - len(archive_destinations)
        ),
        archived_count=len(archive_destinations),
    )


def check_installed_skills(
    repo: Path,
    target_dir: Path,
    profile: str,
    legacy_target_dirs: tuple[Path, ...] = (),
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
        primary = skill.files[0]
        primary_file = skill_dir / primary.relative_path
        common = f"expected {primary.expected_hash}, path {primary_file}"

        if target_is_unsafe:
            invalid = True
            messages.append(
                f"{skill.name}: unsafe ({common}, actual unavailable, "
                "target root must be a real directory)"
            )
            continue
        if skill_dir.is_symlink():
            invalid = True
            messages.append(
                f"{skill.name}: unsafe ({common}, actual unavailable, "
                "symbolic links are not accepted)"
            )
            continue

        skill_invalid = False
        matched: list[str] = []
        for locked_file in skill.files:
            installed_file = skill_dir / locked_file.relative_path
            file_common = (
                f"file {locked_file.relative_path}, "
                f"expected {locked_file.expected_hash}, path {installed_file}"
            )
            if installed_file.is_symlink() or installed_file.parent.is_symlink():
                invalid = True
                skill_invalid = True
                messages.append(
                    f"{skill.name}: unsafe ({file_common}, actual unavailable, "
                    "symbolic links are not accepted)"
                )
                continue
            if not installed_file.is_file():
                invalid = True
                skill_invalid = True
                messages.append(
                    f"{skill.name}: missing ({file_common}, actual missing)"
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
                skill_invalid = True
                messages.append(
                    f"{skill.name}: unsafe ({file_common}, actual unavailable, "
                    f"cannot safely read installed file: {exc})"
                )
                continue

            if digest != locked_file.expected_hash:
                invalid = True
                skill_invalid = True
                messages.append(
                    f"{skill.name}: drift ({file_common}, actual {digest})"
                )
                continue
            matched.append(
                f"{locked_file.relative_path}: expected "
                f"{locked_file.expected_hash}, actual {digest}, "
                f"path {installed_file}"
            )

        if not skill_invalid:
            messages.append(
                f"{skill.name}: match ({'; '.join(matched)})"
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
    for legacy_target_dir in legacy_target_dirs:
        legacy_target_dir = legacy_target_dir.expanduser()
        for name in sorted(catalog.managed_names()):
            installed_dir = legacy_target_dir / name
            if not installed_dir.exists() and not installed_dir.is_symlink():
                continue
            invalid = True
            messages.append(
                f"{name}: legacy stale (path {installed_dir}, "
                f"migrate to {target_dir})"
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
        default=str(default_user_skills_dir()),
        help="Codex skills directory. Defaults to ~/.agents/skills.",
    )
    parser.add_argument(
        "--legacy-target-dir",
        action="append",
        default=[],
        help=(
            "Old skill directory to inspect or clean while migrating. "
            "Repeat for multiple directories."
        ),
    )
    parser.add_argument(
        "--legacy-archive-dir",
        help=(
            "Move managed skills from legacy targets into this archive "
            "instead of deleting them."
        ),
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
    legacy_target_dirs = tuple(
        Path(path).expanduser() for path in args.legacy_target_dir
    )
    legacy_archive_dir = (
        Path(args.legacy_archive_dir).expanduser()
        if args.legacy_archive_dir
        else None
    )

    try:
        if args.check_installed:
            installed_check = check_installed_skills(
                repo,
                target_dir,
                args.profile,
                legacy_target_dirs,
            )
        else:
            install_result = install_skills(
                repo,
                target_dir,
                args.apply,
                args.profile,
                legacy_target_dirs,
                legacy_archive_dir,
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
        if install_result.archived_count:
            print(
                f"archived {install_result.archived_count} "
                "legacy managed skills"
            )
    else:
        print("no files written; rerun with --apply to install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
