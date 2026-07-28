from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from duplicate_work_gate import evaluate_duplicate_work_gate  # noqa: E402
from specrail_lib import load_pack  # noqa: E402


def evidence(
    *,
    open_prs: list[dict[str, object]] | None = None,
    branches: list[str] | None = None,
    complete: bool = True,
) -> dict[str, object]:
    return {
        "issue": 208,
        "collected_at": "2026-07-28T00:00:00Z",
        "open_prs_complete": complete,
        "open_pr_limit": 100,
        "open_prs": open_prs or [],
        "remote_branches": branches or [],
    }


def test_no_duplicate_evidence_is_clear() -> None:
    result = evaluate_duplicate_work_gate(load_pack(ROOT), 208, evidence())

    assert result["decision"] == "allowed"
    assert result["warnings"] == []
    assert result["advisory_only"] is True


def test_open_pr_and_branch_are_advisory_warnings() -> None:
    result = evaluate_duplicate_work_gate(
        load_pack(ROOT),
        208,
        evidence(
            open_prs=[
                {
                    "number": 99,
                    "head_ref": "codex/gh208-existing",
                    "references_issue": True,
                }
            ],
            branches=["origin/codex/gh208-existing"],
        ),
    )

    assert result["decision"] == "warn"
    assert any("open PRs already reference" in item for item in result["warnings"])
    assert any("remote branches may already own" in item for item in result["warnings"])
    assert result["blocked_actions"] == []


def test_missing_or_incomplete_evidence_never_blocks() -> None:
    missing = evaluate_duplicate_work_gate(load_pack(ROOT), 208, None)
    incomplete = evaluate_duplicate_work_gate(
        load_pack(ROOT),
        208,
        evidence(complete=False),
    )

    assert missing["decision"] == "warn"
    assert incomplete["decision"] == "warn"
    assert missing["blocked_actions"] == incomplete["blocked_actions"] == []


def test_invalid_evidence_is_reported_once_as_advisory() -> None:
    invalid = evidence()
    invalid["unexpected"] = True

    result = evaluate_duplicate_work_gate(load_pack(ROOT), 208, invalid)

    assert result["decision"] == "warn"
    assert len(result["warnings"]) == 1
    assert "invalid" in result["warnings"][0]


def test_branch_ownership_uses_configured_template() -> None:
    pack = load_pack(ROOT)
    pack.workflow["artifacts"]["impl_branch"] = (
        "{agent}/issue-{issue_number}-{slug}"
    )

    result = evaluate_duplicate_work_gate(
        pack,
        208,
        evidence(branches=["origin/codex/issue-208-existing"]),
    )

    assert result["decision"] == "warn"
    assert any("issue-208-existing" in item for item in result["warnings"])
