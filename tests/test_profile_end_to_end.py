from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from pr_gate import evaluate_pr_gate  # noqa: E402
from review_json_gate import evaluate_review_gate  # noqa: E402
from route_gate_test_support import run_route_gate, write_duplicate_evidence  # noqa: E402
from test_pr_gate import evidence  # noqa: E402
from test_pr_gate_sensitive_routes import authorization  # noqa: E402
from test_review_json_gate import load_diff, valid_review  # noqa: E402


@pytest.mark.parametrize("profile", ["fastlane", "standard", "heavy"])
def test_profile_route_review_and_pr_gate_end_to_end(
    tmp_path: Path,
    profile: str,
) -> None:
    route_process, route = run_route_gate(
        "--route",
        "implement",
        "--issue",
        "208",
        "--state",
        "ready_to_implement",
        "--profile",
        profile,
        "--duplicate-evidence",
        str(write_duplicate_evidence(tmp_path, issue=208)),
        "--mode",
        "required",
    )
    assert route_process.returncode == 0, route
    assert route["decision"] == "allowed"
    assert route["profile"] == profile

    review = copy.deepcopy(valid_review())
    review["profile"] = profile
    review["review_source"] = (
        "self_review" if profile == "fastlane" else "independent_lane"
    )
    review_result = evaluate_review_gate(review, load_diff())
    assert review_result["decision"] == "allowed", review_result["reasons"]

    pr_payload, pack = evidence(profile=profile)
    pr_payload["review"] = {
        **pr_payload["review"],
        "review_source": review["review_source"],
    }
    if profile == "heavy":
        pr_payload["human_merge_authorization"] = authorization(pr_payload)
    pr_result = evaluate_pr_gate(pr_payload, ROOT, pack)

    assert pr_result["decision"] == "allowed", pr_result["reasons"]
    assert pr_result["advisory_only"] is True
