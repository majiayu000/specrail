from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

from check_workflow_test_support import ROOT, _config, _spec_config

from check_workflow import (  # noqa: E402
    discover_spec_packet_dirs,
    select_spec_packet_dirs,
    spec_packet_sort_key,
    validate_spec_packet,
)
from specrail_lib import (  # noqa: E402
    SpecRailError,
    resolve_path,
    spec_packet_artifact_paths,
    spec_packet_root,
)


def test_spec_packet_root_accepts_configured_repo_relative_path() -> None:
    config = _config(
        {"artifacts": {"spec_packet": "docs/specs/GH{issue_number}/"}}
    )

    assert spec_packet_root(config) == PurePosixPath("docs/specs")


def test_spec_packet_root_requires_template() -> None:
    config = _config({"artifacts": {}})

    with pytest.raises(SpecRailError, match="artifacts.spec_packet is required"):
        spec_packet_root(config)


def test_resolve_path_rejects_missing_filesystem_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_path(_path: Path) -> None:
        raise FileNotFoundError("unavailable filesystem root")

    monkeypatch.setattr(Path, "lstat", missing_path)

    with pytest.raises(SpecRailError, match="could not be resolved"):
        resolve_path(Path("/"), label="repository")


def test_resolve_path_wraps_unavailable_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_cwd(_path: Path) -> Path:
        raise FileNotFoundError("working directory was removed")

    monkeypatch.setattr(Path, "absolute", unavailable_cwd)

    with pytest.raises(SpecRailError, match="could not be resolved"):
        resolve_path(Path("."), label="repository")


@pytest.mark.parametrize(
    "template",
    [
        "docs/specs/GH1/",
        "docs/specs/{issue_number}/",
        "/tmp/specs/GH{issue_number}/",
        "../specs/GH{issue_number}/",
        "docs\\specs\\GH{issue_number}\\",
        "docs/{unsupported}/GH{issue_number}/",
        "docs/{issue_number}/GH{issue_number}/",
        "C:/outside/GH{issue_number}/",
        "docs/C:/outside/GH{issue_number}/",
    ],
)
def test_spec_packet_root_rejects_invalid_templates(template: str) -> None:
    config = _config({"artifacts": {"spec_packet": template}})

    with pytest.raises(SpecRailError):
        spec_packet_root(config)


def test_spec_packet_artifacts_accept_work_id_templates() -> None:
    config = _spec_config(
        spec_packet="docs/specs/{work_id}/",
        product_spec="docs/specs/{work_id}/product.md",
        tech_spec="docs/specs/{work_id}/tech.md",
        task_plan="docs/specs/{work_id}/tasks.md",
    )

    assert spec_packet_artifact_paths(config, 16) == {
        "spec_packet": "docs/specs/GH16",
        "product_spec": "docs/specs/GH16/product.md",
        "tech_spec": "docs/specs/GH16/tech.md",
        "task_plan": "docs/specs/GH16/tasks.md",
    }


@pytest.mark.parametrize(
    ("artifact", "template"),
    [
        ("product_spec", "/tmp/specs/GH{issue_number}/product.md"),
        ("product_spec", "../specs/GH{issue_number}/product.md"),
        ("tech_spec", "C:/outside/GH{issue_number}/tech.md"),
        ("task_plan", "docs/specs/GH{issue_number}/plan.md"),
        ("product_spec", "docs/{unsupported}/GH{issue_number}/product.md"),
        ("product_spec", "docs/specs/GH1/product.md"),
    ],
)
def test_spec_packet_artifacts_reject_invalid_paths(
    artifact: str,
    template: str,
) -> None:
    config = _spec_config(**{artifact: template})

    with pytest.raises(SpecRailError):
        spec_packet_artifact_paths(config, 1)


def test_spec_packet_artifacts_reject_file_symlink_outside_packet(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    packet = repo / "docs" / "specs" / "GH16"
    outside_product = repo / "shared" / "product.md"
    packet.mkdir(parents=True)
    outside_product.parent.mkdir()
    outside_product.write_text("GitHub issue: `#16`\n", encoding="utf-8")
    try:
        (packet / "product.md").symlink_to(outside_product)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(
        SpecRailError,
        match="artifacts.product_spec resolves outside the configured spec packet",
    ):
        spec_packet_artifact_paths(_spec_config(), 16, repo=repo)


def test_spec_packet_artifacts_reject_packet_symlink_outside_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    configured_root = repo / "docs" / "specs"
    outside_packet = repo / "internal" / "GH16"
    configured_root.mkdir(parents=True)
    outside_packet.mkdir(parents=True)
    try:
        (configured_root / "GH16").symlink_to(
            outside_packet,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(
        SpecRailError,
        match="artifacts.spec_packet resolves outside the configured spec packet root",
    ):
        spec_packet_artifact_paths(_spec_config(), 16, repo=repo)


def test_spec_packet_artifacts_reject_packet_identity_redirect(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    configured_root = repo / "docs" / "specs"
    redirected_packet = configured_root / "GH17"
    redirected_packet.mkdir(parents=True)
    try:
        (configured_root / "GH16").symlink_to(
            redirected_packet,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(
        SpecRailError,
        match="does not preserve its configured packet identity",
    ):
        spec_packet_artifact_paths(_spec_config(), 16, repo=repo)


def test_spec_packet_artifacts_reject_file_identity_redirect(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    packet = repo / "docs" / "specs" / "GH16"
    packet.mkdir(parents=True)
    (packet / "tech.md").write_text("GitHub issue: `#16`\n", encoding="utf-8")
    try:
        (packet / "product.md").symlink_to(packet / "tech.md")
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(
        SpecRailError,
        match="artifacts.product_spec does not preserve its configured artifact identity",
    ):
        spec_packet_artifact_paths(_spec_config(), 16, repo=repo)


def test_discovery_rejects_configured_root_symlink_outside_repo(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    (repo / "docs").mkdir(parents=True)
    outside.mkdir()
    try:
        (repo / "docs" / "specs").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(SpecRailError, match="resolves outside the repository"):
        discover_spec_packet_dirs(repo, PurePosixPath("docs/specs"))


@pytest.mark.parametrize("root_kind", ["missing", "regular_file"])
def test_cli_all_specs_rejects_configured_root_is_unusable(
    tmp_path: Path,
    root_kind: str,
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    shutil.rmtree(repo / "specs")
    if root_kind == "regular_file":
        (repo / "specs").write_text("not a directory\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "checks/check_workflow.py",
            "--repo",
            ".",
            "--all-specs",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "configured spec packet root" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


def test_main_rejects_configured_root_symlink_without_all_specs(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    workflow_path = repo / "workflow.yaml"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "specs/GH{issue_number}",
            "docs/specs/GH{issue_number}",
        ),
        encoding="utf-8",
    )
    (repo / "docs").mkdir(exist_ok=True)
    outside.mkdir()
    try:
        (repo / "docs" / "specs").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result = subprocess.run(
        [sys.executable, "checks/check_workflow.py", "--repo", "."],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "resolves outside the repository" in result.stdout


def test_main_reports_configured_root_symlink_loop(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    workflow_path = repo / "workflow.yaml"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "specs/GH{issue_number}",
            "docs/specs/GH{issue_number}",
        ),
        encoding="utf-8",
    )
    try:
        (repo / "docs" / "specs").symlink_to("specs", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result = subprocess.run(
        [sys.executable, "checks/check_workflow.py", "--repo", "."],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "could not be resolved" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


def test_discovery_rejects_packet_symlink_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside_packet = tmp_path / "outside" / "GH1"
    (repo / "docs" / "specs").mkdir(parents=True)
    outside_packet.mkdir(parents=True)
    try:
        (repo / "docs" / "specs" / "GH1").symlink_to(
            outside_packet,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(SpecRailError, match="resolves outside the repository"):
        discover_spec_packet_dirs(repo, PurePosixPath("docs/specs"))


def test_discovery_rejects_packet_symlink_that_changes_name(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    packet_target = repo / "internal" / "GH2"
    (repo / "docs" / "specs").mkdir(parents=True)
    packet_target.mkdir(parents=True)
    try:
        (repo / "docs" / "specs" / "GH1").symlink_to(
            packet_target,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(SpecRailError, match="resolves to a different name"):
        discover_spec_packet_dirs(repo, PurePosixPath("docs/specs"))


def test_explicit_spec_dir_rejects_parent_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (tmp_path / "outside" / "GH1").mkdir(parents=True)
    repo.mkdir()

    with pytest.raises(SpecRailError, match="must stay within the repository"):
        select_spec_packet_dirs(
            repo,
            ["../outside/GH1"],
            all_specs=False,
        )


def test_explicit_spec_dir_rejects_packet_identity_redirect(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    redirected_packet = repo / "docs" / "specs" / "GH2"
    redirected_packet.mkdir(parents=True)
    try:
        (repo / "docs" / "specs" / "GH1").symlink_to(
            redirected_packet,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(SpecRailError, match="different packet identity"):
        select_spec_packet_dirs(
            repo,
            ["docs/specs/GH1"],
            all_specs=False,
        )


def test_spec_packet_rejects_file_symlink_outside_packet(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    outside_product = tmp_path / "outside-product.md"
    spec_dir.mkdir(parents=True)
    outside_product.write_text("GitHub issue: `#1`\n", encoding="utf-8")
    (spec_dir / "tech.md").write_text("GitHub issue: `#1`\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "- [ ] `SP1-T001` Owner: test | Done when: done | Verify: test\n",
        encoding="utf-8",
    )
    try:
        (spec_dir / "product.md").symlink_to(outside_product)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = validate_spec_packet(spec_dir)

    assert f"{spec_dir / 'product.md'}: must stay within the spec packet" in errors


def test_spec_packet_rejects_file_identity_redirect(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tech.md").write_text("GitHub issue: `#1`\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "- [ ] `SP1-T001` Owner: test | Done when: done | Verify: test\n",
        encoding="utf-8",
    )
    try:
        (spec_dir / "product.md").symlink_to(spec_dir / "tech.md")
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = validate_spec_packet(spec_dir)

    assert (
        f"{spec_dir / 'product.md'}: must preserve its declared artifact identity"
        in errors
    )


def test_spec_packet_rejects_packet_identity_redirect(tmp_path: Path) -> None:
    packet_root = tmp_path / "repo" / "specs"
    redirected_packet = packet_root / "GH2"
    redirected_packet.mkdir(parents=True)
    try:
        (packet_root / "GH1").symlink_to(
            redirected_packet,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = validate_spec_packet(packet_root / "GH1")

    assert f"{packet_root / 'GH1'}: must preserve its GH<number> packet identity" in errors


def test_spec_packet_reports_missing_doc_and_issue_token(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "product.md").write_text("No linked issue\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "- [ ] `SP1-T001` Owner: test | Done when: done | Verify: test\n",
        encoding="utf-8",
    )

    errors = validate_spec_packet(spec_dir)

    assert f"{spec_dir}: missing tech.md" in errors
    assert any("product.md: missing linked issue token" in error for error in errors)


def test_spec_packet_rejects_unrendered_tech_manifest_template(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "product.md").write_text("GitHub issue: `#1`\n", encoding="utf-8")
    (spec_dir / "tech.md").write_text(
        "GitHub issue: `#1`\n"
        + (ROOT / "templates" / "tech_spec.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (spec_dir / "tasks.md").write_text(
        "- [ ] `SP1-T001` Owner: test | Done when: done | Verify: test\n",
        encoding="utf-8",
    )

    errors = validate_spec_packet(spec_dir)

    assert f"{spec_dir / 'tech.md'}: manifest issue must match GH1" in errors
    assert f"{spec_dir / 'tech.md'}: manifest must declare complete=true" in errors
    assert f"{spec_dir / 'tech.md'}: manifest paths must not be empty" in errors


def test_spec_packet_requires_planned_changes_manifest(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "product.md").write_text("GitHub issue: `#1`\n", encoding="utf-8")
    (spec_dir / "tech.md").write_text(
        "GitHub issue: `#1`\n"
        "<!-- specrail-requires-planned-changes-v1 -->\n",
        encoding="utf-8",
    )
    (spec_dir / "tasks.md").write_text(
        "- [ ] `SP1-T001` Owner: test | Done when: done | Verify: test\n",
        encoding="utf-8",
    )

    errors = validate_spec_packet(spec_dir)

    assert (
        f"{spec_dir / 'tech.md'} must contain exactly one "
        "specrail-planned-changes manifest"
    ) in errors


def test_cli_explicit_spec_requires_planned_changes_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    tech_path = repo / "specs" / "GH97" / "tech.md"
    text = tech_path.read_text(encoding="utf-8")
    text = re.sub(
        r"<!-- specrail-planned-changes\n.*?\n-->",
        "",
        text,
        count=1,
        flags=re.DOTALL,
    )
    tech_path.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "checks/check_workflow.py",
            "--repo",
            ".",
            "--spec-dir",
            "specs/GH97",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert (
        "tech.md must contain exactly one specrail-planned-changes manifest"
        in result.stdout
    )


def test_spec_packet_rejects_task_identity_redirect(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    spec_dir.mkdir(parents=True)
    for name in ["product.md", "tech.md"]:
        (spec_dir / name).write_text("GitHub issue: `#1`\n", encoding="utf-8")
    try:
        (spec_dir / "tasks.md").symlink_to(spec_dir / "product.md")
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = validate_spec_packet(spec_dir)

    assert (
        f"{spec_dir / 'tasks.md'}: must preserve its declared artifact identity"
        in errors
    )


def test_spec_packet_rejects_task_symlink_outside_packet(tmp_path: Path) -> None:
    spec_dir = tmp_path / "repo" / "specs" / "GH1"
    outside_tasks = tmp_path / "outside-tasks.md"
    spec_dir.mkdir(parents=True)
    outside_tasks.write_text(
        "- [ ] `SP1-T001` Owner: test | Done when: done | Verify: test\n",
        encoding="utf-8",
    )
    for name in ["product.md", "tech.md"]:
        (spec_dir / name).write_text("GitHub issue: `#1`\n", encoding="utf-8")
    try:
        (spec_dir / "tasks.md").symlink_to(outside_tasks)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = validate_spec_packet(spec_dir)

    assert f"{spec_dir / 'tasks.md'}: must stay within the spec packet" in errors


def test_spec_packet_sort_key_places_non_packet_paths_last() -> None:
    assert spec_packet_sort_key(Path("not-a-packet")) == (1, 0, "not-a-packet")

