from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from route_gate_test_support import (
    ROOT,
    complete_issue_evidence,
    run_route_gate,
    write_custom_pack,
    write_duplicate_evidence,
    write_issue_evidence,
)

from route_gate import artifact_exists  # noqa: E402


def test_artifact_exists_rejects_empty_path() -> None:
    assert artifact_exists(ROOT, None) is False


def test_collector_evidence_reports_all_invocation_binding_errors(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "forged-issue-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "issue": 208,
                "repository": "other/repo",
                "body_sha256": "a" * 64,
                "github_state": "OPEN",
                "state": "ready_to_implement",
                "state_source": "label",
                "state_trusted": True,
                "labels": ["area_runtime", "security_private"],
                "outcomes": [],
                "url": "https://github.com/other/repo/issues/208",
                "title": "Forged reusable evidence",
                "testable_plan": {
                    "source": "issue_body_checklist",
                    "items": ["observable result"],
                    "body_sha256": "b" * 64,
                },
                "artifacts": {
                    "product_spec": "specs/GH208/product.md",
                    "tech_spec": "specs/GH208/tech.md",
                    "task_plan": "specs/GH208/tasks.md",
                },
            }
        ),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "expected/repo",
        "--profile",
        "standard",
        "--evidence",
        str(evidence_path),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    reasons = payload["reasons"]
    assert any("must match --issue 999" in reason for reason in reasons)
    assert any("must match --github-repo expected/repo" in reason for reason in reasons)
    assert "trusted label state must be present in issue evidence labels" in reasons
    assert "issue evidence outcomes must exactly match outcome labels" in reasons
    assert "testable_plan.body_sha256 must match issue evidence body_sha256" in reasons


@pytest.mark.parametrize("field", ["labels", "outcomes"])
def test_route_gate_reports_null_issue_evidence_arrays(
    tmp_path: Path,
    field: str,
) -> None:
    issue_evidence = complete_issue_evidence()
    issue_evidence[field] = None
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(json.dumps(issue_evidence), encoding="utf-8")

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--profile",
        "standard",
        "--evidence",
        str(evidence_path),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any(field in reason for reason in payload["reasons"])
    assert "Traceback" not in result.stderr


def test_route_gate_requires_trusted_state_for_readiness_gated_routes(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(
            state="ready_to_spec", state_source="body_hint",
            state_trusted=False, labels=[],
        )),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert payload["decision"] == "needs_human"
    assert "trusted_state" in payload["missing"]
    assert any("untrusted body_hint" in reason for reason in payload["reasons"])


def test_route_gate_required_mode_fails_untrusted_readiness_state(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(
            state="ready_to_spec", state_source="body_hint",
            state_trusted=False, labels=[],
        )),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence_path),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "needs_human"


def test_route_gate_allows_trusted_readiness_label_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(state="ready_to_spec")),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"


def test_route_gate_blocks_terminal_outcome_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence = complete_issue_evidence(
        state="ready_to_spec",
        labels=["ready_to_spec", "security_private"],
    )
    evidence["outcomes"] = ["security_private"]
    evidence_path.write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )

    _result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence_path),
    )

    assert payload["decision"] == "blocked"
    assert any("security_private" in reason for reason in payload["reasons"])


def test_release_note_allows_done_lifecycle_state(tmp_path: Path) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "github_state": "OPEN",
                "state": "done",
                "state_source": "label",
                "state_trusted": True,
                "labels": ["done"],
                "outcomes": [],
            }
        ),
        encoding="utf-8",
    )

    _result, payload = run_route_gate(
        "--route",
        "draft_release_note",
        "--issue",
        "999",
        "--pr",
        "123",
        "--evidence",
        str(evidence_path),
    )

    assert payload["decision"] == "allowed"


def test_implement_preserves_configured_required_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo)
    workflow_path = repo / "workflow.yaml"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "    implement:\n"
            "      allowed_from:\n"
            "        - ready_to_implement\n"
            "      required_artifacts:\n"
            "        - linked_issue\n",
            "    implement:\n"
            "      allowed_from:\n"
            "        - ready_to_implement\n"
            "      required_artifacts:\n"
            "        - linked_issue\n"
            "        - verification\n",
        ),
        encoding="utf-8",
    )

    _result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(
            tmp_path,
            testable_plan={
                "source": "issue_body_checklist",
                "items": ["verify the configured requirement"],
            },
        )),
        repo=repo,
    )

    assert payload["decision"] == "warn"
    assert "verification" in payload["missing"]


@pytest.mark.parametrize(
    "task_plan",
    [
        "",
        "# Tasks\n\n- [ ] missing stable contract fields\n",
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: complete\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: TBD | Verify: `true`\n"
        ),
        (
            '# Tasks\n\n- [ ] `SP999-T1` Owner: test | '
            'Done when: "TBD" | Verify: `true`\n'
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: 'TODO' | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: “TBD” | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: 「TBD」 | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: «TBD» | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: „TBD“ | Verify: `true`\n"
        ),
        (
            '# Tasks\n\n- [ ] `SP999-T1` Owner: test | '
            'Done when: “TBD" | Verify: `true`\n'
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: **「`TBD/TODO`」** | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: TBD\u200bTODO | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: TBD\u0301TODO | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: TBDTODO | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: pendingTBD | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: TODOunknownnull | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: comingsoon | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: test | "
            "Done when: tobedeterminedTODO | Verify: `true`\n"
        ),
        (
            "# Tasks\n\n- [ ] `SP999-T1` Owner: | "
            "Done when: complete | Verify: `true`\n"
        ),
    ],
)
def test_standard_implement_rejects_invalid_task_plan(
    tmp_path: Path,
    task_plan: str,
) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo)
    packet = repo / "docs" / "specs" / "GH999"
    packet.mkdir(parents=True)
    (packet / "tasks.md").write_text(task_plan, encoding="utf-8")

    _result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--profile",
        "standard",
        "--evidence",
        str(write_issue_evidence(tmp_path)),
        repo=repo,
    )

    assert payload["decision"] != "allowed"
    assert "testable_plan" in payload["missing"]


def test_standard_implement_accepts_valid_task_plan(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo)
    packet = repo / "docs" / "specs" / "GH999"
    packet.mkdir(parents=True)
    (packet / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] `SP999-T1` Owner: test | "
        "Done when: “TODO fix parser” | Verify: `true`\n",
        encoding="utf-8",
    )

    _result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--profile",
        "standard",
        "--evidence",
        str(write_issue_evidence(tmp_path)),
        repo=repo,
    )

    assert payload["decision"] == "allowed", payload["reasons"]
    assert "standard testable plan evidence validated" in payload["satisfied"]


def test_route_gate_uses_configured_spec_packet_in_verification_command(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo)

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, state="ready_to_spec")),
        repo=repo,
    )

    assert result.returncode == 0
    assert (
        "python3 checks/check_workflow.py --repo . --spec-dir=docs/specs/GH999"
        in payload["verification_commands"]
    )


def test_route_gate_accepts_normalized_configured_artifact_evidence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo, "./specs")
    schema_dir = repo / "schemas"
    schema_dir.mkdir(exist_ok=True)
    duplicate_schema = schema_dir / "duplicate_work_evidence.schema.json"
    duplicate_schema.write_text(
        (ROOT / "schemas" / duplicate_schema.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (schema_dir / "issue_evidence.schema.json").write_text(
        (ROOT / "schemas/issue_evidence.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    packet = repo / "specs" / "GH999"
    packet.mkdir(parents=True)
    for name in ["product.md", "tech.md"]:
        (packet / name).write_text("GitHub issue: `#999`\n", encoding="utf-8")
    (packet / "tasks.md").write_text(
        "# Task Plan\n\n## Linked Issue\n\nGH-999\n\n"
        "- [ ] `SP999-T1` Covers: B-001 | Owner: test | "
        "Done when: fixture exists | Verify: `true`\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid", "commit", "-qm", "approved",
        ],
        check=True,
    )
    approved_revision = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    duplicate_evidence = write_duplicate_evidence(tmp_path)
    issue_evidence = tmp_path / "issue-evidence.json"
    issue_evidence.write_text(
        json.dumps(complete_issue_evidence()),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--profile",
        "heavy",
        "--github-repo",
        "example/consumer",
        "--approved-spec-revision",
        approved_revision,
        "--evidence",
        str(issue_evidence),
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--artifact",
        "product_spec=specs/GH999/product.md",
        "--artifact",
        "tech_spec=specs/GH999/tech.md",
        "--mode",
        "required",
        repo=repo,
    )

    assert result.returncode == 0, payload
    assert payload["decision"] == "allowed"
    assert "security_evidence" not in payload["missing"]
    assert "product_spec: specs/GH999/product.md" in payload["satisfied"]

    dotted_result, dotted_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--profile",
        "heavy",
        "--github-repo",
        "example/consumer",
        "--approved-spec-revision",
        approved_revision,
        "--evidence",
        str(issue_evidence),
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--artifact",
        "product_spec=./specs/GH999/product.md",
        "--artifact",
        "tech_spec=./specs/GH999/tech.md",
        "--mode",
        "required",
        repo=repo,
    )

    assert dotted_result.returncode == 0, dotted_payload
    assert dotted_payload["decision"] == "allowed"
    assert "security_evidence" not in dotted_payload["missing"]
    assert "product_spec: specs/GH999/product.md" in dotted_payload["satisfied"]

    wrong_result, wrong_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--profile",
        "heavy",
        "--evidence",
        str(issue_evidence),
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--artifact",
        "product_spec=specs/GH998/product.md",
        "--artifact",
        "tech_spec=specs/GH999/tech.md",
        "--mode",
        "required",
        repo=repo,
    )

    assert wrong_result.returncode == 1
    assert wrong_payload["decision"] == "blocked"


def test_route_gate_shell_quotes_configured_spec_packet_command(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo, "docs/spec packets;printf PWN")

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, state="ready_to_spec")),
        repo=repo,
    )

    assert result.returncode == 0
    assert (
        "python3 checks/check_workflow.py --repo . --spec-dir="
        "'docs/spec packets;printf PWN/GH999'"
        in payload["verification_commands"]
    )


def test_route_gate_uses_equals_for_leading_dash_spec_packet(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo, "-specs")

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, state="ready_to_spec")),
        repo=repo,
    )

    assert result.returncode == 0
    assert (
        "python3 checks/check_workflow.py --repo . --spec-dir=-specs/GH999"
        in payload["verification_commands"]
    )


def test_route_gate_blocks_root_symlink_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    write_custom_pack(repo)
    (repo / "docs").mkdir()
    outside.mkdir()
    try:
        (repo / "docs" / "specs").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, state="ready_to_spec")),
        repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any(
        "resolves outside the repository" in reason
        for reason in payload["reasons"]
    )


def test_route_gate_reports_root_symlink_loop_as_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo)
    (repo / "docs").mkdir()
    try:
        (repo / "docs" / "specs").symlink_to("specs", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, state="ready_to_spec")),
        repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("could not be resolved" in reason for reason in payload["reasons"])
    assert "Traceback" not in result.stderr

def test_route_gate_blocks_invalid_spec_packet_template(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo)
    workflow_path = repo / "workflow.yaml"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "docs/specs/GH{issue_number}/",
            "../specs/GH{issue_number}/",
            1,
        ),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, state="ready_to_spec")),
        repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert (
        "workflow.yaml: artifacts.spec_packet must stay within the repository"
        in payload["reasons"]
    )


def test_route_gate_dry_run_warns_for_missing_artifacts_but_required_blocks(
    tmp_path: Path,
) -> None:
    duplicate_evidence = write_duplicate_evidence(tmp_path)
    issue_evidence = write_issue_evidence(tmp_path)
    dry_run, dry_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(issue_evidence),
        "--profile",
        "heavy",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "dry_run",
    )
    required, required_payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(issue_evidence),
        "--profile",
        "heavy",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "required",
    )

    assert dry_run.returncode == 0
    assert dry_payload["decision"] == "warn"
    assert any("product_spec" in item for item in dry_payload["missing"])

    assert required.returncode == 1
    assert required_payload["decision"] == "blocked"
    assert any("tech_spec" in item for item in required_payload["missing"])


def test_route_gate_duplicate_success_reason_not_itemized(tmp_path: Path) -> None:
    duplicate_evidence = write_duplicate_evidence(tmp_path)
    issue_evidence = write_issue_evidence(tmp_path)
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(issue_evidence),
        "--profile",
        "heavy",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "required",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    # Duplicate-work evidence is carried as advisory context...
    assert any(
        "no open PR references" in item for item in payload["satisfied"]
    )
    # ...but never becomes a rejection item for unrelated blockers.
    assert not any(
        "duplicate_work" in item["expected"]
        or "duplicate_work" in item["found"]
        for item in payload["rejection_items"]
    )


def test_route_gate_missing_duplicate_evidence_is_advisory(tmp_path: Path) -> None:
    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "142",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, issue=142)),
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"
    assert any("duplicate work evidence is missing" in item for item in payload["warnings"])


def test_route_gate_warns_for_duplicate_open_pr(tmp_path: Path) -> None:
    duplicate_evidence = write_duplicate_evidence(
        tmp_path,
        issue=142,
        open_prs=[
            {
                "number": 123,
                "head_ref": "codex/gh142-existing",
                "references_issue": True,
            }
        ],
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "142",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, issue=142)),
        "--duplicate-evidence",
        str(duplicate_evidence),
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"
    assert any("#123" in warning for warning in payload["warnings"])


def test_route_gate_duplicate_branch_is_advisory(tmp_path: Path) -> None:
    duplicate_evidence = write_duplicate_evidence(
        tmp_path,
        issue=142,
        remote_branches=["codex/gh142-existing"],
    )

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "142",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path, issue=142)),
        "--duplicate-evidence",
        str(duplicate_evidence),
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"
    assert any("remote branches may already own" in item for item in payload["warnings"])


def test_route_gate_blocks_unknown_current_state() -> None:
    result, payload = run_route_gate(
        "--route",
        "triage_issue",
        "--issue",
        "999",
        "--state",
        "ready_to_merge",
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert payload["reasons"] == ["unknown current state: ready_to_merge"]


def test_route_gate_rejection_items_enumerate_missing_evidence(
    tmp_path: Path,
) -> None:
    _, payload = run_route_gate("--route", "implement", "--issue", "999")

    assert payload["decision"] != "allowed"
    items = payload["rejection_items"]
    assert items
    item_ids = {item["item_id"] for item in items}
    assert "missing_evidence_field:current_state" in item_ids
    for item in items:
        for key in ["item_id", "category", "expected", "found"]:
            assert isinstance(item[key], str) and item[key].strip()


def _write_implement_pack(tmp_path: Path, product_text: str) -> Path:
    repo = tmp_path / "repo"
    write_custom_pack(repo, "./specs")
    schema_dir = repo / "schemas"
    schema_dir.mkdir(exist_ok=True)
    duplicate_schema = schema_dir / "duplicate_work_evidence.schema.json"
    duplicate_schema.write_text(
        (ROOT / "schemas" / duplicate_schema.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    packet = repo / "specs" / "GH999"
    packet.mkdir(parents=True)
    (packet / "product.md").write_text(product_text, encoding="utf-8")
    (packet / "tech.md").write_text("GitHub issue: `#999`\n", encoding="utf-8")
    return repo


def test_implement_blocked_on_legacy_spec_with_non_legacy_spec_missing(
    tmp_path: Path,
) -> None:
    repo = _write_implement_pack(
        tmp_path,
        "# Product Spec\n\n## Linked Issue\n\nGH-999\n\nstatus: legacy\n",
    )
    duplicate_evidence = write_duplicate_evidence(tmp_path)

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
        "--duplicate-evidence",
        str(duplicate_evidence),
        repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert "non_legacy_spec" in payload["missing"]
    assert any(
        "status: legacy" in reason and "write_spec (needs_spec)" in reason
        for reason in payload["reasons"]
    )
    assert any(
        item["item_id"] == "contract_violation:non_legacy_spec"
        for item in payload["rejection_items"]
    )


def test_implement_blocked_json_on_undecodable_product_spec(
    tmp_path: Path,
) -> None:
    # GH142 follow-up: product.md exists but is invalid UTF-8. The legacy read
    # must fail closed as a blocked JSON result, not a UnicodeDecodeError
    # traceback.
    repo = _write_implement_pack(
        tmp_path,
        "# Product Spec\n\n## Linked Issue\n\nGH-999\n",
    )
    (repo / "specs" / "GH999" / "product.md").write_bytes(
        b"# Product Spec\n\xff\xfe\x81invalid\n"
    )
    duplicate_evidence = write_duplicate_evidence(tmp_path)

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
        "--duplicate-evidence",
        str(duplicate_evidence),
        repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("cannot decode" in reason for reason in payload["reasons"])


def test_implement_allows_non_legacy_spec_unchanged(tmp_path: Path) -> None:
    repo = _write_implement_pack(
        tmp_path,
        "# Product Spec\n\n## Linked Issue\n\nGH-999\n",
    )
    duplicate_evidence = write_duplicate_evidence(tmp_path)

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path)),
        "--profile",
        "fastlane",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "required",
        repo=repo,
    )

    assert result.returncode == 0, payload
    assert payload["decision"] == "allowed"
    assert "non_legacy_spec" not in payload["missing"]


def test_legacy_marker_outside_linked_issue_does_not_block_implement(
    tmp_path: Path,
) -> None:
    repo = _write_implement_pack(
        tmp_path,
        "# Product Spec\n\n## Linked Issue\n\nGH-999\n\n"
        "## Non-Goals\n\nstatus: legacy\n",
    )
    duplicate_evidence = write_duplicate_evidence(tmp_path)

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(write_issue_evidence(tmp_path)),
        "--profile",
        "fastlane",
        "--duplicate-evidence",
        str(duplicate_evidence),
        "--mode",
        "required",
        repo=repo,
    )

    assert result.returncode == 0, payload
    assert payload["decision"] == "allowed"


def test_implement_blocked_when_product_md_unreadable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_custom_pack(repo, "./specs")
    packet = repo / "specs" / "GH999"
    packet.mkdir(parents=True)
    # product.md exists but is unreadable as a file: fail closed (B-007).
    (packet / "product.md").mkdir()
    (packet / "tech.md").write_text("GitHub issue: `#999`\n", encoding="utf-8")

    result, payload = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "999",
        "--state",
        "ready_to_implement",
        repo=repo,
    )

    assert result.returncode == 1
    assert payload["decision"] == "blocked"
    assert any("cannot read" in reason for reason in payload["reasons"])


def test_route_gate_allowed_result_has_empty_rejection_items(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(
        json.dumps(complete_issue_evidence(state="ready_to_spec")),
        encoding="utf-8",
    )

    result, payload = run_route_gate(
        "--route",
        "write_spec",
        "--issue",
        "999",
        "--github-repo",
        "example/consumer",
        "--evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert payload["decision"] == "allowed"
    assert payload["rejection_items"] == []
    assert "repeat_rejection" not in payload
