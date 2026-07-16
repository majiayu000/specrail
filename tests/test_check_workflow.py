from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from check_workflow_test_support import ROOT, _auth_workflow, _config

import check_workflow  # noqa: E402

from check_workflow import REQUIRED_FILES, main as check_workflow_main  # noqa: E402
from check_workflow import validate_required_file_globs  # noqa: E402
from check_workflow import (  # noqa: E402
    validate_auth_mode,
    validate_impl_branch_template,
    validate_pack_assets,
)
from specrail_lib import load_pack  # noqa: E402


def test_required_files_do_not_enumerate_fixtures_or_non_runtime_schemas() -> None:
    assert not any(path.startswith("examples/fixtures/") for path in REQUIRED_FILES)
    schema_paths = [path for path in REQUIRED_FILES if path.startswith("schemas/")]
    assert schema_paths == ["schemas/duplicate_work_evidence.schema.json"]


def test_required_file_globs_discover_existing_fixture_and_schema_files() -> None:
    assert validate_required_file_globs(ROOT) == []


def test_required_file_globs_require_at_least_one_match(tmp_path: Path) -> None:
    errors = validate_required_file_globs(tmp_path)

    assert "missing required files matching: examples/fixtures/*" in errors
    assert "missing required files matching: schemas/*.schema.json" in errors


def test_required_files_include_duplicate_work_checks() -> None:
    assert "checks/duplicate_work_gate.py" in REQUIRED_FILES
    assert "checks/github_duplicate_evidence.py" in REQUIRED_FILES
    assert "schemas/duplicate_work_evidence.schema.json" in REQUIRED_FILES


def test_required_files_include_pr_issue_reference_module() -> None:
    assert "checks/github_evidence_common.py" in REQUIRED_FILES
    assert "checks/github_issue_reference.py" in REQUIRED_FILES


def test_required_files_include_schema_validation_runtime_dependency() -> None:
    assert "checks/schema_validation.py" in REQUIRED_FILES


def test_required_files_include_closure_audit() -> None:
    assert "checks/closure_audit.py" in REQUIRED_FILES


def test_trusted_pack_asset_validation_ignores_target_helper(tmp_path: Path) -> None:
    target = tmp_path / "target"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    target_helper = target / "checks" / "pack_asset_validation.py"
    target_helper.write_text(
        "from pathlib import Path\n"
        "Path(__file__).with_name('target-helper-executed').write_text('yes')\n"
        "def validate_json_schemas(repo):\n"
        "    return []\n"
        "def validate_template_parity(repo):\n"
        "    return []\n",
        encoding="utf-8",
    )
    (target / "schemas" / "workflow_run.schema.json").unlink()

    errors = validate_pack_assets(target)

    assert "schemas: missing SpecRail schema workflow_run.schema.json" in errors
    assert not target_helper.with_name("target-helper-executed").exists()


def test_trusted_pack_asset_validation_requires_source_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = tmp_path / "runner" / "checks" / "check_workflow.py"
    runner.parent.mkdir(parents=True)
    monkeypatch.setattr(check_workflow, "__file__", str(runner))

    errors = validate_pack_assets(ROOT)

    assert errors == [
        "cannot load trusted pack asset validation: "
        "checks/pack_asset_validation.py is missing"
    ]


def test_tech_templates_have_one_fail_closed_planned_changes_manifest() -> None:
    assert validate_pack_assets(ROOT) == []


@pytest.mark.parametrize("failure", ["missing", "duplicate", "invalid"])
def test_pack_assets_reject_invalid_tech_template_manifest(
    tmp_path: Path,
    failure: str,
) -> None:
    target = tmp_path / "target"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    path = target / "templates" / "tech_spec.md"
    marker = (
        '<!-- specrail-planned-changes\n'
        '{"version":1,"issue":0,"complete":false,"paths":[],"spec_refs":[]}\n'
        '-->'
    )
    text = path.read_text(encoding="utf-8")
    if failure == "missing":
        text = text.replace(marker, "")
    elif failure == "duplicate":
        text = text.replace(marker, marker + "\n" + marker)
    else:
        text = text.replace(marker, "<!-- specrail-planned-changes\n{invalid}\n-->")
    path.write_text(text, encoding="utf-8")

    errors = validate_pack_assets(target)

    assert any("templates/tech_spec.md" in error for error in errors)


def test_check_workflow_rejects_invalid_sensitive_registry_provider_config(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    workflow = target / "workflow.yaml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("    paths: []", "    paths: invalid"),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "checks/check_workflow.py", "--repo", "."],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "sensitive_registry.paths must be a list" in result.stdout


@pytest.mark.parametrize(
    ("replacement", "expected"),
    [
        ("enforcement: null", "enforcement must be a mapping"),
        (
            "enforcement:\n  sensitive_registry: null",
            "enforcement.sensitive_registry must be a mapping",
        ),
        (
            "enforcement:\n  sensitive_regsitry:\n    paths: []\n    specs: []",
            "enforcement contains unsupported fields: sensitive_regsitry",
        ),
    ],
)
def test_check_workflow_rejects_malformed_enforcement_config(
    tmp_path: Path,
    replacement: str,
    expected: str,
) -> None:
    target = tmp_path / "target"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    workflow = target / "workflow.yaml"
    block = (
        "enforcement:\n"
        "  sensitive_registry:\n"
        "    paths: []\n"
        "    specs: []"
    )
    text = workflow.read_text(encoding="utf-8")
    assert text.count(block) == 1
    workflow.write_text(text.replace(block, replacement), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "checks/check_workflow.py", "--repo", "."],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert expected in result.stdout


def test_impl_branch_template_requires_issue_number_placeholder() -> None:
    class Config:
        workflow = {"artifacts": {"impl_branch": "{agent}/branch-{slug}"}}

    assert validate_impl_branch_template(Config()) == [
        "workflow.yaml: artifacts.impl_branch must contain {issue_number}"
    ]


def test_impl_branch_template_accepts_current_workflow() -> None:
    class Config:
        workflow = {"artifacts": {"impl_branch": "{agent}/gh{issue_number}-{slug}"}}

    assert validate_impl_branch_template(Config()) == []


def test_cli_all_specs_uses_configured_root(tmp_path: Path) -> None:
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
    shutil.copytree(repo / "specs" / "GH91", repo / "docs" / "specs" / "GH91")
    (repo / "specs" / "GH1" / "tasks.md").unlink()

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

    assert result.returncode == 0, result.stdout + result.stderr


def test_main_validates_configured_spec_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_workflow.py", "--repo", str(ROOT), "--all-specs"],
    )

    assert check_workflow_main() == 0
    assert "SpecRail check passed" in capsys.readouterr().out


def test_auth_mode_accepts_repo_workflow() -> None:
    assert validate_auth_mode(load_pack(ROOT)) == []


def test_auth_mode_accepts_valid_two_mode_config() -> None:
    assert validate_auth_mode(_config(_auth_workflow())) == []


def test_auth_mode_rejects_unknown_mode_value() -> None:
    workflow = _auth_workflow()
    workflow["automation_policy"] = {"auth_mode": "yolo"}

    errors = validate_auth_mode(_config(workflow))

    assert (
        "workflow.yaml: automation_policy.auth_mode must be one of: auto, review"
        in errors
    )


def test_auth_mode_rejects_persisted_auto_mode() -> None:
    workflow = _auth_workflow()
    workflow["automation_policy"] = {"auth_mode": "auto"}

    errors = validate_auth_mode(_config(workflow))

    assert errors == [
        "workflow.yaml: automation_policy.auth_mode must be review; "
        "auto requires an explicit current implx auto invocation"
    ]


def test_auth_mode_requires_auth_modes_mapping() -> None:
    workflow = _auth_workflow()
    del workflow["auth_modes"]

    assert validate_auth_mode(_config(workflow)) == [
        "workflow.yaml: auth_modes must be a mapping"
    ]


def test_auth_mode_requires_both_mode_definitions() -> None:
    workflow = _auth_workflow()
    workflow["auth_modes"] = {"auto": {"waived_human_gates": []}}

    assert validate_auth_mode(_config(workflow)) == [
        "workflow.yaml: auth_modes.review must be a mapping"
    ]


def test_auth_mode_rejects_waiving_unknown_gate() -> None:
    workflow = _auth_workflow()
    workflow["auth_modes"]["auto"]["waived_human_gates"] = ["not_a_gate"]

    assert validate_auth_mode(_config(workflow)) == [
        "workflow.yaml: auth_modes.auto waives unknown human gate not_a_gate"
    ]


def test_auth_mode_rejects_unknown_mode_key() -> None:
    workflow = _auth_workflow()
    workflow["auth_modes"]["turbo"] = {"waived_human_gates": []}

    assert validate_auth_mode(_config(workflow)) == [
        "workflow.yaml: auth_modes defines unknown mode turbo"
    ]
