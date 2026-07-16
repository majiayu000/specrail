from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from closure_audit import ClosureAuditError, audit_closure  # noqa: E402
from specrail_lib import validate_instance  # noqa: E402


HEAD = "a" * 40


def closure_schema() -> dict[str, object]:
    return json.loads(
        (ROOT / "schemas" / "closure_audit_result.schema.json").read_text(
            encoding="utf-8"
        )
    )


def compliant_evidence() -> dict[str, object]:
    return {
        "repository": "example/specrail",
        "pr_number": 115,
        "final_head_sha": HEAD,
        "gate": {
            "decision": "allowed",
            "head_sha": HEAD,
            "gate_query_completed_at": "2026-07-16T14:36:07Z",
            "gate_query_head_sha": HEAD,
        },
        "merge": {
            "merge_path": "gh_pr_merge",
            "remote_confirmed": True,
            "merge_dispatched_at": "2026-07-16T14:38:00Z",
            "merge_head_sha": HEAD,
            "merged_at": "2026-07-16T14:38:08Z",
            "merged_head_sha": HEAD,
        },
    }


def assert_schema_valid(result: dict[str, object]) -> None:
    validate_instance(closure_schema(), result)


def test_compliant_chain_is_schema_valid() -> None:
    result = audit_closure(
        compliant_evidence(), checked_at="2026-07-16T14:39:00Z"
    )

    assert result["status"] == "compliant"
    assert result["violations"] == []
    assert result["required_follow_up"] is None
    assert result["advisory_only"] is True
    assert result["github_writes_performed"] is False
    assert_schema_valid(result)


def test_dispatch_must_be_strictly_after_gate_query() -> None:
    evidence = compliant_evidence()
    evidence["merge"]["merge_dispatched_at"] = "2026-07-16T14:36:07Z"  # type: ignore[index]

    result = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")

    assert result["status"] == "violation"
    assert result["violations"][0]["code"] == "closure_dispatch_not_after_gate"  # type: ignore[index]
    assert result["required_follow_up"]["violation_code"] == "closure_dispatch_not_after_gate"  # type: ignore[index]
    assert_schema_valid(result)


def test_merge_must_not_precede_dispatch() -> None:
    evidence = compliant_evidence()
    evidence["merge"]["merged_at"] = "2026-07-16T14:37:59Z"  # type: ignore[index]

    result = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")

    assert result["violations"][0]["code"] == "closure_merge_before_dispatch"  # type: ignore[index]
    assert_schema_valid(result)


def test_all_heads_must_match_final_head() -> None:
    evidence = compliant_evidence()
    evidence["merge"]["merge_head_sha"] = "b" * 40  # type: ignore[index]

    result = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")

    assert result["violations"][0]["code"] == "closure_head_mismatch"  # type: ignore[index]
    assert_schema_valid(result)


def test_external_merge_missing_chain_returns_stable_follow_up() -> None:
    evidence = compliant_evidence()
    evidence["gate"] = None
    merge = evidence["merge"]
    assert isinstance(merge, dict)
    merge["merge_path"] = "merged_by_other"
    merge.pop("merge_dispatched_at")
    merge.pop("merge_head_sha")

    first = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")
    second = audit_closure(evidence, checked_at="2026-07-16T15:39:00Z")

    assert first["status"] == "violation"
    assert first["violations"][0]["code"] == "external_merge_missing_chain"  # type: ignore[index]
    assert first["required_follow_up"]["idempotency_key"] == second["required_follow_up"]["idempotency_key"]  # type: ignore[index]
    assert first["required_follow_up"]["repository"] == "example/specrail"  # type: ignore[index]
    assert first["required_follow_up"]["pr_number"] == 115  # type: ignore[index]
    assert first["required_follow_up"]["final_head_sha"] == HEAD  # type: ignore[index]
    assert_schema_valid(first)


def test_repository_identity_is_normalized_for_stable_follow_up() -> None:
    mixed_case = compliant_evidence()
    mixed_case["repository"] = "Example/SpecRail"
    mixed_case["gate"] = None
    mixed_merge = mixed_case["merge"]
    assert isinstance(mixed_merge, dict)
    mixed_merge["merge_path"] = "merged_by_other"
    mixed_merge.pop("merge_dispatched_at")
    mixed_merge.pop("merge_head_sha")
    canonical = json.loads(json.dumps(mixed_case))
    canonical["repository"] = "example/specrail"

    mixed_result = audit_closure(
        mixed_case, checked_at="2026-07-16T14:39:00Z"
    )
    canonical_result = audit_closure(
        canonical, checked_at="2026-07-16T14:39:00Z"
    )

    assert mixed_result["repository"] == "example/specrail"
    assert mixed_result["required_follow_up"]["repository"] == "example/specrail"  # type: ignore[index]
    assert mixed_result["required_follow_up"]["idempotency_key"] == canonical_result["required_follow_up"]["idempotency_key"]  # type: ignore[index]
    assert_schema_valid(mixed_result)


def test_non_external_missing_gate_is_explicit_violation() -> None:
    evidence = compliant_evidence()
    evidence["gate"] = None

    result = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")

    assert result["violations"][0]["code"] == "closure_missing_gate_evidence"  # type: ignore[index]
    assert_schema_valid(result)


def test_gate_must_have_allowed_decision() -> None:
    evidence = compliant_evidence()
    evidence["gate"]["decision"] = "blocked"  # type: ignore[index]

    result = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")

    assert result["violations"][0]["code"] == "closure_gate_not_allowed"  # type: ignore[index]
    assert_schema_valid(result)


def test_invalid_timestamp_is_schema_valid_violation() -> None:
    evidence = compliant_evidence()
    evidence["merge"]["merged_at"] = "not-a-time"  # type: ignore[index]

    result = audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")

    assert result["violations"][0]["code"] == "closure_invalid_timestamp"  # type: ignore[index]
    assert_schema_valid(result)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda evidence: evidence.update({"unexpected": True}),
        lambda evidence: evidence["gate"].update({"gate_completed_at": "forged"}),  # type: ignore[union-attr]
        lambda evidence: evidence["merge"].update({"write_issue": True}),  # type: ignore[union-attr]
    ],
)
def test_unknown_input_fields_fail_explicitly(mutation: object) -> None:
    evidence = compliant_evidence()
    assert callable(mutation)
    mutation(evidence)

    with pytest.raises(ClosureAuditError, match="unsupported fields"):
        audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")


@pytest.mark.parametrize("merge_path", [[], {}])
def test_non_string_merge_path_fails_explicitly(merge_path: object) -> None:
    evidence = compliant_evidence()
    evidence["merge"]["merge_path"] = merge_path  # type: ignore[index]

    with pytest.raises(ClosureAuditError, match="merge.merge_path"):
        audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "not-a-repository"),
        ("pr_number", 0),
        ("final_head_sha", "short"),
    ],
)
def test_invalid_follow_up_identity_fails_explicitly(field: str, value: object) -> None:
    evidence = compliant_evidence()
    evidence[field] = value

    with pytest.raises(ClosureAuditError, match=field):
        audit_closure(evidence, checked_at="2026-07-16T14:39:00Z")


def make_cli_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    schema_dir = repo / "schemas"
    schema_dir.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "schemas" / "closure_audit_result.schema.json",
        schema_dir / "closure_audit_result.schema.json",
    )
    return repo


def write_evidence(repo: Path, evidence: dict[str, object]) -> Path:
    path = repo / "closure.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def test_cli_compliant_smoke(tmp_path: Path) -> None:
    repo = make_cli_repo(tmp_path)
    evidence = write_evidence(repo, compliant_evidence())

    completed = subprocess.run(
        [
            sys.executable,
            "checks/closure_audit.py",
            "--repo",
            str(repo),
            "--evidence",
            evidence.name,
            "--checked-at",
            "2026-07-16T14:39:00Z",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "compliant"
    assert_schema_valid(result)


def test_cli_violation_smoke(tmp_path: Path) -> None:
    repo = make_cli_repo(tmp_path)
    evidence_payload = compliant_evidence()
    evidence_payload["gate"] = None
    merge = evidence_payload["merge"]
    assert isinstance(merge, dict)
    merge["merge_path"] = "merged_by_other"
    merge.pop("merge_dispatched_at")
    merge.pop("merge_head_sha")
    evidence = write_evidence(repo, evidence_payload)

    completed = subprocess.run(
        [
            sys.executable,
            "checks/closure_audit.py",
            "--repo",
            str(repo),
            "--evidence",
            evidence.name,
            "--checked-at",
            "2026-07-16T14:39:00Z",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["required_follow_up"]["violation_code"] == "external_merge_missing_chain"
    assert_schema_valid(result)


def test_cli_invalid_json_is_error(tmp_path: Path) -> None:
    repo = make_cli_repo(tmp_path)
    evidence = repo / "invalid.json"
    evidence.write_text("{", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "checks/closure_audit.py",
            "--repo",
            str(repo),
            "--evidence",
            evidence.name,
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "invalid closure evidence JSON" in completed.stderr
    assert completed.stdout == ""


@pytest.mark.parametrize("merge_path", [[], {}])
def test_cli_non_string_merge_path_is_malformed_input(
    tmp_path: Path, merge_path: object
) -> None:
    repo = make_cli_repo(tmp_path)
    payload = compliant_evidence()
    payload["merge"]["merge_path"] = merge_path  # type: ignore[index]
    evidence = write_evidence(repo, payload)

    completed = subprocess.run(
        [
            sys.executable,
            "checks/closure_audit.py",
            "--repo",
            str(repo),
            "--evidence",
            evidence.name,
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "merge.merge_path" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert completed.stdout == ""


@pytest.mark.parametrize("evidence_arg", ["absolute", "parent", "symlink"])
def test_cli_rejects_evidence_outside_repository(
    tmp_path: Path, evidence_arg: str
) -> None:
    repo = make_cli_repo(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(compliant_evidence()), encoding="utf-8")
    if evidence_arg == "absolute":
        argument = str(outside)
    elif evidence_arg == "parent":
        argument = "../outside.json"
    else:
        link = repo / "escape.json"
        link.symlink_to(outside)
        argument = link.name

    completed = subprocess.run(
        [
            sys.executable,
            "checks/closure_audit.py",
            "--repo",
            str(repo),
            "--evidence",
            argument,
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "closure evidence" in completed.stderr
    assert "repository" in completed.stderr
    assert completed.stdout == ""
