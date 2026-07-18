from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from rejection_items import (  # noqa: E402
    RejectionItemError,
    apply_prior_rejection,
    finalize_items,
    item_from_reason,
    load_prior_rejection,
    make_item,
    repeat_rejection,
)
from review_json_gate import evaluate_review_gate  # noqa: E402


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_diff() -> str:
    return (FIXTURES / "pr-diff.patch").read_text(encoding="utf-8")


def run_review_gate_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "checks/review_json_gate.py", "--repo", ".", *args, "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def assert_item_shape(item: dict[str, object]) -> None:
    for key in ["item_id", "category", "expected", "found"]:
        assert isinstance(item[key], str) and item[key].strip(), item


# --- B-002 / B-009: make_item validation -----------------------------------


def test_make_item_rejects_bad_category_and_empty_fields() -> None:
    with pytest.raises(RejectionItemError):
        make_item("not_a_category", "subject", "expected", "found")
    with pytest.raises(RejectionItemError):
        make_item("config_error", "", "expected", "found")
    with pytest.raises(RejectionItemError):
        make_item("config_error", "subject", "", "found")
    with pytest.raises(RejectionItemError):
        make_item("config_error", "subject", "expected", "   ")

    item = make_item("config_error", "a subject", "the expected", "the found")
    assert item == {
        "item_id": "config_error:a-subject",
        "category": "config_error",
        "expected": "the expected",
        "found": "the found",
    }


def test_placeholder_expected_found_rejected() -> None:
    for placeholder in ["N/A", "unknown", "none", "-", "TBD"]:
        with pytest.raises(RejectionItemError):
            make_item("config_error", "subject", placeholder, "found")
        with pytest.raises(RejectionItemError):
            make_item("config_error", "subject", "expected", placeholder)


# --- B-004: dedup and conflict resolution ----------------------------------


def test_duplicate_items_deduped_by_id() -> None:
    item = make_item("missing_artifact", "product_spec", "spec exists", "absent")
    finalized = finalize_items([item, dict(item), dict(item)])

    assert finalized == [item]


def test_conflicting_duplicate_ids_suffixed_deterministically() -> None:
    first = make_item("invalid_state", "route", "state in triaged", "new_issue")
    second = make_item("invalid_state", "route", "state in triaged", "needs_info")
    third = make_item("invalid_state", "route", "state in triaged", "new_issue")

    forward = finalize_items([first, second, third])
    backward = finalize_items([third, second, first])

    assert json.dumps(forward) == json.dumps(backward)
    assert [entry["item_id"] for entry in forward] == [
        "invalid_state:route#1",
        "invalid_state:route#2",
    ]
    assert forward[0]["found"] == "needs_info"
    assert forward[1]["found"] == "new_issue"


# --- B-003: deterministic output across runs -------------------------------


def test_rejection_items_deterministic_across_runs() -> None:
    review = {"verdict": "bogus", "comments": [{"body": ""}]}

    first = evaluate_review_gate(dict(review), load_diff())
    second = evaluate_review_gate(dict(review), load_diff())

    assert first["decision"] == "blocked"
    assert first["rejection_items"]
    assert json.dumps(first["rejection_items"]) == json.dumps(
        second["rejection_items"]
    )


# --- B-001: full enumeration ------------------------------------------------


def test_rejection_items_enumerate_all_failures() -> None:
    result = evaluate_review_gate({}, load_diff())

    assert result["decision"] == "blocked"
    items = result["rejection_items"]
    for item in items:
        assert_item_shape(item)
    item_ids = {item["item_id"] for item in items}
    for field in ["verdict", "body", "comments"]:
        assert f"missing_evidence_field:{field}" in item_ids
    # every independently reported defect has a structured item
    assert len(items) >= len(result["missing"]) + len(result["reasons"])


# --- B-005: repeat detection ------------------------------------------------


def test_repeat_rejection_lists_identical_items() -> None:
    same = make_item("missing_artifact", "tech_spec", "tech spec exists", "absent")
    changed_prior = make_item("invalid_state", "route", "state in triaged", "new_issue")
    changed_now = make_item("invalid_state", "route", "state in triaged", "needs_info")
    fresh = make_item("missing_artifact", "task_plan", "task plan exists", "absent")

    repeats = repeat_rejection([same, changed_now, fresh], [same, changed_prior])

    assert repeats == [same["item_id"]]


# --- B-006: fail-closed prior payload --------------------------------------


def test_bad_prior_rejection_file_becomes_config_error_item(tmp_path: Path) -> None:
    missing_items, missing_error = load_prior_rejection(tmp_path / "absent.json")
    assert missing_items is None
    assert missing_error is not None
    assert missing_error["category"] == "config_error"
    assert missing_error["item_id"] == "config_error:prior_rejection"

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    _, bad_error = load_prior_rejection(bad_json)
    assert bad_error is not None and bad_error["category"] == "config_error"

    no_items = tmp_path / "no-items.json"
    no_items.write_text(json.dumps({"decision": "blocked"}), encoding="utf-8")
    _, shape_error = load_prior_rejection(no_items)
    assert shape_error is not None and shape_error["category"] == "config_error"

    # CLI: an unusable prior payload blocks even an otherwise passing review.
    result = run_review_gate_cli(
        "--review",
        "examples/fixtures/review-valid.json",
        "--diff",
        "examples/fixtures/pr-diff.patch",
        "--prior-rejection",
        str(tmp_path / "absent.json"),
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "blocked"
    assert any(
        item["item_id"] == "config_error:prior_rejection"
        for item in payload["rejection_items"]
    )


# --- B-008: allowed decision ------------------------------------------------


def test_allowed_result_has_empty_rejection_items() -> None:
    result = run_review_gate_cli(
        "--review",
        "examples/fixtures/review-valid.json",
        "--diff",
        "examples/fixtures/pr-diff.patch",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allowed"
    assert payload["rejection_items"] == []
    assert "repeat_rejection" not in payload


# --- B-010: early-exit paths -----------------------------------------------


def test_early_exit_paths_emit_structured_items(tmp_path: Path) -> None:
    evidence_path = tmp_path / "issue-evidence.json"
    evidence_path.write_text(json.dumps({"github_state": "CLOSED"}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "checks/route_gate.py",
            "--repo",
            ".",
            "--route",
            "implement",
            "--issue",
            "999",
            "--evidence",
            str(evidence_path),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "blocked"
    items = payload["rejection_items"]
    assert len(items) == 1
    assert_item_shape(items[0])
    assert items[0]["category"] == "invalid_state"


# --- B-011: read-only gates -------------------------------------------------


def test_gate_read_only_with_rejection_items(tmp_path: Path) -> None:
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps({"rejection_items": []}), encoding="utf-8")
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    result = run_review_gate_cli(
        "--review",
        "examples/fixtures/review-invalid-body.json",
        "--diff",
        "examples/fixtures/pr-diff.patch",
        "--prior-rejection",
        str(prior),
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["rejection_items"]

    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert before == after


# --- B-012: idempotent rerun ------------------------------------------------


def test_rerun_after_interrupt_matches_full_run() -> None:
    args = (
        "--review",
        "examples/fixtures/review-invalid-body.json",
        "--diff",
        "examples/fixtures/pr-diff.patch",
    )
    interrupted_then_rerun = run_review_gate_cli(*args)
    full_run = run_review_gate_cli(*args)

    assert interrupted_then_rerun.returncode == full_run.returncode == 1
    assert interrupted_then_rerun.stdout == full_run.stdout


# --- SP141-T5: end-to-end two-round flows -----------------------------------


def test_two_round_full_list_single_fix_then_pass(tmp_path: Path) -> None:
    review = load_fixture("review-valid.json")
    broken = dict(review)
    del broken["body"]
    del broken["comments"]
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(broken), encoding="utf-8")

    first = run_review_gate_cli(
        "--review", str(review_path), "--diff", "examples/fixtures/pr-diff.patch"
    )
    assert first.returncode == 1
    first_payload = json.loads(first.stdout)
    item_ids = {item["item_id"] for item in first_payload["rejection_items"]}
    assert "missing_evidence_field:body" in item_ids
    assert "missing_evidence_field:comments" in item_ids

    rejection_path = tmp_path / "rejection.json"
    rejection_path.write_text(first.stdout, encoding="utf-8")

    # Single fix round: repair every listed defect at once.
    review_path.write_text(json.dumps(review), encoding="utf-8")
    second = run_review_gate_cli(
        "--review",
        str(review_path),
        "--diff",
        "examples/fixtures/pr-diff.patch",
        "--prior-rejection",
        str(rejection_path),
    )
    assert second.returncode == 0
    second_payload = json.loads(second.stdout)
    assert second_payload["decision"] == "allowed"
    assert second_payload["rejection_items"] == []
    assert "repeat_rejection" not in second_payload


# --- PR147 review round: placeholder observations ---------------------------


def test_item_from_reason_normalizes_placeholder_observation() -> None:
    for placeholder in ["None", "null", "unknown", "N/A", "-"]:
        item = item_from_reason(f"verdict must be approve; got {placeholder}")
        assert item["found"] == f"placeholder value {placeholder!r} reported"

    concrete = item_from_reason("verdict must be approve; got bogus")
    assert concrete["found"] == "bogus"


def test_review_gate_null_verdict_keeps_full_enumeration() -> None:
    result = evaluate_review_gate({"verdict": None}, load_diff())

    assert result["decision"] == "blocked"
    items = result["rejection_items"]
    for item in items:
        assert_item_shape(item)
    assert not any(item["category"] == "config_error" for item in items)
    assert any(
        item["found"] == "placeholder value 'None' reported" for item in items
    )
    assert len(items) >= len(result["missing"]) + len(result["reasons"])


# --- PR147 review round: malformed prior entries fail closed -----------------


def test_prior_rejection_non_object_entry_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "prior.json"
    bad.write_text(json.dumps({"rejection_items": [None]}), encoding="utf-8")

    items, error = load_prior_rejection(bad)

    assert items is None
    assert error is not None
    assert error["category"] == "config_error"
    assert "non-object entry" in error["found"]

    # CLI: the corrupted prior blocks an otherwise passing review.
    result = run_review_gate_cli(
        "--review",
        "examples/fixtures/review-valid.json",
        "--diff",
        "examples/fixtures/pr-diff.patch",
        "--prior-rejection",
        str(bad),
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "blocked"
    assert any(
        item["item_id"] == "config_error:prior_rejection"
        for item in payload["rejection_items"]
    )


# --- PR147 review round: suffix-stable repeat detection ----------------------


def test_repeat_rejection_matches_across_conflict_suffix_changes() -> None:
    prior_suffixed = [
        {
            "item_id": "invalid_state:route#1",
            "category": "invalid_state",
            "expected": "state in triaged",
            "found": "needs_info",
        },
        {
            "item_id": "invalid_state:route#2",
            "category": "invalid_state",
            "expected": "state in triaged",
            "found": "new_issue",
        },
    ]
    survivor = [make_item("invalid_state", "route", "state in triaged", "new_issue")]

    # Round 1 suffixed both conflicts; round 2 fixed one, survivor unsuffixed.
    assert repeat_rejection(survivor, prior_suffixed) == ["invalid_state:route"]
    # Reverse direction: prior unsuffixed, current suffixed still matches.
    assert repeat_rejection(prior_suffixed, survivor) == ["invalid_state:route#2"]


# --- PR147 review round: unusable prior carries blocked actions --------------


def test_unusable_prior_blocks_declared_actions(tmp_path: Path) -> None:
    result = {
        "decision": "allowed",
        "reasons": [],
        "rejection_items": [],
        "blocked_actions": [],
    }

    updated = apply_prior_rejection(
        result,
        str(tmp_path / "absent.json"),
        blocked_actions=["merge", "final_approval"],
    )

    assert updated["decision"] == "blocked"
    assert updated["blocked_actions"] == ["final_approval", "merge"]


def test_repeat_rejection_cli_flags_identical_second_round(tmp_path: Path) -> None:
    review = load_fixture("review-valid.json")
    broken = dict(review)
    del broken["body"]
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(broken), encoding="utf-8")

    first = run_review_gate_cli(
        "--review", str(review_path), "--diff", "examples/fixtures/pr-diff.patch"
    )
    assert first.returncode == 1
    first_payload = json.loads(first.stdout)
    rejection_path = tmp_path / "rejection.json"
    rejection_path.write_text(first.stdout, encoding="utf-8")

    second = run_review_gate_cli(
        "--review",
        str(review_path),
        "--diff",
        "examples/fixtures/pr-diff.patch",
        "--prior-rejection",
        str(rejection_path),
    )
    assert second.returncode == 1
    second_payload = json.loads(second.stdout)
    assert second_payload["repeat_rejection"]["item_ids"] == [
        item["item_id"] for item in first_payload["rejection_items"]
    ]
