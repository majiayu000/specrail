from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from check_workflow_test_support import ROOT, _auth_workflow, _config

import check_workflow  # noqa: E402

from check_workflow import REQUIRED_FILES, main as check_workflow_main  # noqa: E402
from check_workflow import (  # noqa: E402
    validate_required_file_globs,
    validate_required_files,
)
from check_workflow import (  # noqa: E402
    validate_auth_mode,
    validate_impl_branch_template,
    validate_issue_triage_contract,
    validate_pack_assets,
)
from specrail_lib import load_pack  # noqa: E402


def run_check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "checks" / "check_workflow.py"), "--repo", str(repo)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_unadopted_repository_is_explicitly_skipped(tmp_path: Path) -> None:
    result = run_check(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "SpecRail check skipped: repository is not adopted\n"


@pytest.mark.parametrize(
    ("relative_path", "content"),
    [
        (
            "checks/route_gate.py",
            '"""Evaluate whether a SpecRail action may proceed."""\n',
        ),
        ("skills/specrail-workflow/SKILL.md", "# SpecRail\n"),
        ("skills/implx/SKILL.md", "# implx\n"),
        (
            "AGENTS.md",
            "Treat SpecRail as an agent-facing workflow contract.\n",
        ),
    ],
)
def test_missing_workflow_fails_when_adoption_sentinel_exists(
    tmp_path: Path,
    relative_path: str,
    content: str,
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "missing workflow.yaml in adopted repository" in result.stdout
    assert relative_path.split(":", 1)[0] in result.stdout


@pytest.mark.parametrize(
    ("relative_path", "content"),
    [
        ("states.yaml", "states: {}\n"),
        ("labels.yaml", "labels: []\n"),
        ("skills-lock.json", "{}\n"),
        (
            "skills-lock.json",
            '{"version":1,"algorithm":"sha256","skills":[]}\n',
        ),
        ("AGENTS.md", "Use the repository's native workflow.\n"),
        ("AGENTS.md", "This repository does not use SpecRail.\n"),
    ],
)
def test_unrelated_assets_do_not_imply_adoption(
    tmp_path: Path,
    relative_path: str,
    content: str,
) -> None:
    (tmp_path / relative_path).write_text(content, encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "SpecRail check skipped: repository is not adopted\n"


@pytest.mark.parametrize(
    "skill",
    [
        {"name": "specrail-workflow", "path": "skills/other/SKILL.md"},
        {"name": "other", "path": "skills/specrail-workflow/SKILL.md"},
        {"name": "implx", "path": "skills/other/SKILL.md"},
        {"name": "other", "path": "skills/implx/SKILL.md"},
    ],
)
def test_specrail_lock_alone_implies_adoption(
    tmp_path: Path,
    skill: dict[str, str],
) -> None:
    (tmp_path / "skills-lock.json").write_text(
        json.dumps({"skills": [skill]}) + "\n",
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "missing workflow.yaml in adopted repository" in result.stdout
    assert "skills-lock.json" in result.stdout


def test_generic_lock_alone_does_not_imply_adoption(tmp_path: Path) -> None:
    (tmp_path / "skills-lock.json").write_text(
        '{"skills":[{"name":"lint","path":"skills/lint/SKILL.md"}]}\n',
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "SpecRail check skipped: repository is not adopted\n"


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        ("{", "invalid JSON"),
        ("[]", "top-level value must be an object"),
        ('{"skills":{}}', "skills must be a list"),
        ('{"skills":[1]}', "skill #1 must be an object"),
        ('{"skills":[{"name":"lint"}]}', "must have string name and path"),
    ],
)
def test_malformed_lock_alone_fails_closed(
    tmp_path: Path,
    content: str,
    detail: str,
) -> None:
    (tmp_path / "skills-lock.json").write_text(content, encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "malformed SpecRail adoption manifest" in result.stdout
    assert detail in result.stdout


def test_adopted_repository_with_missing_assets_fails_closed(tmp_path: Path) -> None:
    shutil.copy(ROOT / "workflow.yaml", tmp_path / "workflow.yaml")

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "SpecRail check failed" in result.stdout
    assert "missing required file: states.yaml" in result.stdout


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


def test_issue_triage_schema_matches_readiness_labels(tmp_path: Path) -> None:
    assert validate_issue_triage_contract(ROOT, load_pack(ROOT)) == []
    for name in ("workflow.yaml", "states.yaml", "labels.yaml"):
        shutil.copy(ROOT / name, tmp_path / name)
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema = (ROOT / "schemas" / "issue_triage.schema.json").read_text(
        encoding="utf-8"
    ).replace('"parked"', '"reserved_internal"')
    (schema_dir / "issue_triage.schema.json").write_text(schema, encoding="utf-8")

    errors = validate_issue_triage_contract(tmp_path, load_pack(tmp_path))

    assert errors == [
        "schemas/issue_triage.schema.json: recommended_state must match "
        "labels.yaml readiness states"
    ]


def test_required_file_cap_ignores_consumer_owned_schema(tmp_path: Path) -> None:
    shutil.copytree(ROOT, tmp_path / "repo", ignore=shutil.ignore_patterns(".git"))
    repo = tmp_path / "repo"
    (repo / "schemas" / "consumer.schema.json").write_text(
        '{"type":"object"}\n',
        encoding="utf-8",
    )

    assert not any(
        "schemas:" in error and "hard limit" in error
        for error in validate_required_files(repo)
    )


def test_checker_count_rejects_extra_top_level_python_file(tmp_path: Path) -> None:
    shutil.copytree(ROOT, tmp_path / "repo", ignore=shutil.ignore_patterns(".git"))
    repo = tmp_path / "repo"
    (repo / "checks" / "consumer_checker.py").write_text(
        "raise SystemExit('consumer-owned')\n",
        encoding="utf-8",
    )

    assert "checks: expected exactly 18 Python files; found 19" in (
        validate_required_files(repo)
    )


def test_checker_count_is_recursive(
    tmp_path: Path,
) -> None:
    shutil.copytree(ROOT, tmp_path / "repo", ignore=shutil.ignore_patterns(".git"))
    repo = tmp_path / "repo"
    nested = repo / "checks" / "_lib" / "nested_checker.py"
    nested.parent.mkdir(exist_ok=True)
    nested.write_text("# nested\n", encoding="utf-8")

    assert "checks: expected exactly 18 Python files; found 19" in (
        validate_required_files(repo)
    )


def test_required_files_exclude_removed_runtime_dependencies() -> None:
    assert not any("runtime" in path for path in REQUIRED_FILES)
    assert "checks/review_json_gate.py" in REQUIRED_FILES
    assert "checks/pr_gate.py" in REQUIRED_FILES


def test_required_files_reject_missing_compact_review_gate(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".coverage*"),
    )
    helper = target / "checks" / "review_json_gate.py"
    helper.unlink()

    assert (
        "missing required file: checks/review_json_gate.py"
        in validate_required_files(target)
    )


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
    (target / "schemas" / "task_plan.schema.json").unlink()

    errors = validate_pack_assets(target)

    assert "schemas: missing SpecRail schema task_plan.schema.json" in errors
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
