"""Regression tests for the PR #210 fastlane self-review scope findings.

Each test pins one reported bypass:

* protected filename stems (`auth_service.py`) must not qualify for fastlane;
* workflow/policy contract paths (`workflow.yaml`, `skills/**`) must not either;
* the coordinator exception is limited to a genuinely single-file PR;
* a recorded pr_gate decision must not stand in for raw re-evaluated evidence;
* an independently reviewed PR must receive adapter-derived tier evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pr_gate_test_support import CHECKS  # noqa: F401  (adds checks/ to sys.path)
from github_tier_evidence import (
    TierEvidenceError,
    adapter_tier_evidence,
    trusted_tier_attestation,
)
from runtime_pr_gate_evidence import validate_pr_gate_artifact
from runtime_tier_authorization import (
    _fastlane_protected_path,
    fastlane_tier_evidence_errors,
)

HEAD = "a" * 40
BASE = "b" * 40


def _tier_evidence(paths: list[str], *, changed_files: int) -> dict[str, object]:
    normalized = sorted(paths)
    return {
        "changed_lines": 10,
        "changed_lines_countable": True,
        "changed_files": changed_files,
        "touched_paths": normalized,
        "source": "github_changed_files",
        "head_sha": HEAD,
        "base_ref": "main",
        "base_sha": BASE,
        "paths_sha256": hashlib.sha256(
            json.dumps(normalized, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _errors(evidence: dict[str, object]) -> list[str]:
    return fastlane_tier_evidence_errors(
        evidence,
        expected_head_sha=HEAD,
        expected_base_ref="main",
        expected_base_sha=BASE,
    )


@pytest.mark.parametrize(
    "path",
    [
        "src/auth_service.py",
        "src/security_utils.py",
        "src/api_client.py",
        "src/auth.test.ts",
        "src/securityUtils.ts",
    ],
)
def test_protected_tokens_in_filename_stems_are_not_fastlane(path: str) -> None:
    assert _fastlane_protected_path(path) is True
    assert _errors(_tier_evidence([path], changed_files=1)) != []


@pytest.mark.parametrize(
    "path",
    [
        "workflow.yaml",
        "states.yaml",
        "AGENTS.md",
        "skills-lock.json",
        "skills/implx/SKILL.md",
        "integrations/threads.md",
        "review/agent_first_review.md",
        "templates/tranche_checkpoint.md",
        ".github/dependabot.yml",
    ],
)
def test_workflow_contract_paths_are_not_fastlane(path: str) -> None:
    assert _fastlane_protected_path(path) is True
    assert _errors(_tier_evidence([path], changed_files=1)) != []


@pytest.mark.parametrize("path", ["docs/notes.md", "README.md", "src/widget.tsx"])
def test_ordinary_paths_stay_fastlane_eligible(path: str) -> None:
    assert _fastlane_protected_path(path) is False
    assert _errors(_tier_evidence([path], changed_files=1)) == []


def test_multi_file_diff_is_rejected_even_under_the_line_limit() -> None:
    evidence = _tier_evidence(["src/alpha.py", "src/beta.py"], changed_files=2)

    errors = _errors(evidence)

    assert any("changed_files must be exactly 1" in error for error in errors)


def test_rename_keeps_two_paths_but_one_changed_file() -> None:
    # GitHub reports one changed file for a rename while the path snapshot
    # carries both the previous and current name.
    evidence = _tier_evidence(["docs/new.md", "docs/old.md"], changed_files=1)

    assert _errors(evidence) == []


def test_missing_changed_files_fails_closed() -> None:
    evidence = _tier_evidence(["docs/notes.md"], changed_files=1)
    evidence.pop("changed_files")

    assert any(
        "changed_files is invalid" in error for error in _errors(evidence)
    )


def test_recorded_decision_is_rejected_for_tier_authorized_items(
    tmp_path: Path,
) -> None:
    gate_path = tmp_path / "pr-gate.json"
    gate_path.write_text(
        json.dumps(
            {
                "decision": "allowed",
                "pr": 718,
                "head_sha": HEAD,
                "pr_tier": "standard",
                "enforcement_sensitive": False,
            }
        ),
        encoding="utf-8",
    )
    raw_item = {
        "pr": 718,
        "head_sha": HEAD,
        "authorization_tier": "standard_auto",
        "enforcement_sensitive": False,
    }
    errors: list[str] = []

    result = validate_pr_gate_artifact(
        raw_item, str(gate_path), "item #1", errors, None, None
    )

    assert result is None
    assert any("requires raw pr_gate evidence" in error for error in errors)


def test_recorded_decision_still_accepted_for_untiered_items(
    tmp_path: Path,
) -> None:
    gate_path = tmp_path / "pr-gate.json"
    gate_path.write_text(
        json.dumps({"decision": "allowed", "pr": 718, "head_sha": HEAD}),
        encoding="utf-8",
    )
    errors: list[str] = []

    result = validate_pr_gate_artifact(
        {"pr": 718, "head_sha": HEAD}, str(gate_path), "item #1", errors, None, None
    )

    assert errors == []
    assert result is not None and result["decision"] == "allowed"


def _artifact(**overrides: object) -> dict[str, object]:
    artifact = {
        "artifact_path": "artifacts/review-1.json",
        "head_sha": HEAD,
        "review_source": "independent_lane",
        "tier_attestation": {
            "pr_tier": "standard",
            "attested": True,
            "basis": "reviewer lane measured the diff",
        },
    }
    artifact.update(overrides)
    return artifact


def test_independent_lane_attestation_yields_tier_evidence() -> None:
    manifest = {"review_source": "independent_lane", "artifacts": [_artifact()]}

    attestation = trusted_tier_attestation(manifest, HEAD)

    assert attestation == {
        "pr_tier": "standard",
        "artifact_path": "artifacts/review-1.json",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"review_source": "self_review"},
        {"tier_dispute": True},
        {"tier_attestation": {"pr_tier": "standard", "attested": False, "basis": "x"}},
        {"tier_attestation": {"pr_tier": "standard", "attested": True, "basis": " "}},
    ],
)
def test_untrusted_attestation_fails_closed(overrides: dict[str, object]) -> None:
    manifest = {
        "review_source": "independent_lane",
        "artifacts": [_artifact(**overrides)],
    }

    with pytest.raises(TierEvidenceError):
        trusted_tier_attestation(manifest, HEAD)


def test_dispute_without_own_attestation_still_fails_closed() -> None:
    # A reviewer who raises a dispute without writing their own attestation is
    # the ordinary case. Skipping that artifact would let a second lane's
    # attestation through.
    manifest = {
        "review_source": "independent_lane",
        "artifacts": [
            {
                "artifact_path": "artifacts/review-1.json",
                "head_sha": HEAD,
                "review_source": "independent_lane",
                "tier_dispute": True,
            },
            _artifact(artifact_path="artifacts/review-2.json"),
        ],
    }

    with pytest.raises(TierEvidenceError, match="tier_dispute"):
        trusted_tier_attestation(manifest, HEAD)


@pytest.mark.parametrize(
    "path", ["src/enforcement_policy.py", "src/contract_loader.py"]
)
def test_contract_and_enforcement_tokens_are_protected(path: str) -> None:
    # skills/implx/SKILL.md:72-74 names enforcement and contracts as
    # enforcement-sensitive surfaces.
    assert _fastlane_protected_path(path) is True


@pytest.mark.parametrize("path", ["AGENT_USAGE.md", "labels.yaml", "SPEC.md"])
def test_bootstrap_contracts_are_protected(path: str) -> None:
    # These root files define the agent operating contract and workflow
    # labels; an empty consumer registry must not leave them fastlane-eligible.
    assert _fastlane_protected_path(path) is True


def test_uncountable_diff_is_rejected() -> None:
    # A binary change reports zero additions and deletions, so an arbitrarily
    # large one would otherwise satisfy the 50-line bound unmeasured.
    evidence = _tier_evidence(["assets/logo.png"], changed_files=1)
    evidence["changed_lines"] = 0
    evidence["changed_lines_countable"] = False

    assert any("countable textual diff" in error for error in _errors(evidence))


def test_missing_countability_flag_fails_closed() -> None:
    evidence = _tier_evidence(["docs/notes.md"], changed_files=1)
    evidence.pop("changed_lines_countable")

    assert any("countable textual diff" in error for error in _errors(evidence))


def test_disagreeing_lanes_fail_closed() -> None:
    manifest = {
        "review_source": "independent_lane",
        "artifacts": [
            _artifact(),
            _artifact(
                artifact_path="artifacts/review-2.json",
                tier_attestation={
                    "pr_tier": "heavy",
                    "attested": True,
                    "basis": "second lane disagrees",
                },
            ),
        ],
    }

    with pytest.raises(TierEvidenceError, match="disagreeing pr_tier"):
        trusted_tier_attestation(manifest, HEAD)


def test_stale_head_attestation_is_ignored() -> None:
    manifest = {
        "review_source": "independent_lane",
        "artifacts": [_artifact(head_sha="c" * 40)],
    }

    assert trusted_tier_attestation(manifest, HEAD) is None


def test_adapter_tier_evidence_uses_github_file_count_not_path_count() -> None:
    snapshot = {
        "head_sha": HEAD,
        "base_ref": "main",
        "base_sha": BASE,
        "changed_lines": 10,
        "changed_lines_countable": True,
        "file_count": 1,
        "paths": ["docs/new.md", "docs/old.md"],
        "paths_sha256": "0" * 64,
    }

    evidence = adapter_tier_evidence(snapshot)

    assert evidence["changed_files"] == 1
    assert evidence["touched_paths"] == ["docs/new.md", "docs/old.md"]
