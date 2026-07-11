from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from check_workflow import REQUIRED_FILES, validate_required_file_globs  # noqa: E402
from check_workflow import validate_auth_mode, validate_impl_branch_template  # noqa: E402
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


def _auth_workflow(**overrides: object) -> dict[str, object]:
    workflow: dict[str, object] = {
        "automation_policy": {"auth_mode": "review"},
        "required_human_gates": [
            "readiness_label",
            "spec_approval",
            "final_pr_review",
            "security_decision",
            "merge",
            "release",
        ],
        "auth_modes": {
            "auto": {
                "waived_human_gates": ["spec_approval", "final_pr_review", "merge"],
            },
            "review": {"waived_human_gates": []},
        },
    }
    workflow.update(overrides)
    return workflow


def _config(workflow: dict[str, object]) -> object:
    class Config:
        pass

    config = Config()
    config.workflow = workflow
    return config


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
