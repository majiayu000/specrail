from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from github_pr_evidence_test_support import (
    ROOT,
    base_sha,
    clean_review_evidence,
    file_snapshot,
    pr_payload,
    reviewer_resolver_roles,
    threads_payload,
)
from github_pr_evidence import (  # noqa: E402
    EvidenceError,
    REVIEW_THREADS_QUERY,
    build_evidence,
    build_human_authorization,
    collect_evidence,
    load_maintainer_role_map,
    load_round_cap_authorizations,
    load_resolver_role_map,
    normalize_issue_reference,
    normalize_review_threads,
    parse_github_repo,
    references_partial_issue,
)
from pr_gate import evaluate_pr_gate  # noqa: E402
from schema_validation import SpecRailError, validate_instance  # noqa: E402
from specrail_lib import PackConfig, load_pack  # noqa: E402


def test_parse_github_repo_requires_owner_repo() -> None:
    assert parse_github_repo("majiayu000/specrail") == ("majiayu000", "specrail")

    with pytest.raises(EvidenceError):
        parse_github_repo("majiayu000/specrail/extra")

    with pytest.raises(EvidenceError):
        parse_github_repo("../specrail")


def test_review_threads_query_requests_resolver_identity() -> None:
    assert "resolvedBy" in REVIEW_THREADS_QUERY
    assert "login" in REVIEW_THREADS_QUERY


def test_build_evidence_matches_pr_gate_contract() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        {
            "actor": "user",
            "source": "chat",
            "summary": "merge approved",
        },
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
    )

    assert evidence["pr"] == 10
    assert evidence["review_source"] == "independent_lane"
    assert evidence["review_execution"] == "local"
    assert evidence["lane_failures"] == []
    assert evidence["gate_query_head_sha"] == "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"
    assert evidence["gate_query_completed_at"].endswith("Z")
    assert evidence["linked_issue"] == 9
    assert evidence["issue_reference"] == {
        "number": 9,
        "kind": "closing",
        "source": "closingIssuesReferences",
        "verified": True,
        "closing_issue_numbers": [9],
    }
    assert evidence["checks"] == [
        {
            "name": "workflow-check",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "url": "https://github.com/example/specrail/actions/runs/1",
        },
        {
            "name": "lint",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "url": "https://ci.example.invalid/lint",
        },
    ]
    assert evidence["reviews"] == [
        {"author": "reviewer", "state": "APPROVED"},
        {"author": "bot", "state": "COMMENTED"},
    ]
    assert evidence["review_threads"] == [
        {
            "id": "PRRT_kwDOExample",
            "url": "https://github.com/example/specrail/pull/10#discussion_r1",
            "is_resolved": True,
            "is_outdated": False,
            "actionable": True,
            "original_comment_id": "PRRC_kwDOExampleRoot",
            "original_author": "reviewer",
            "resolved_by": "reviewer",
            "resolver_role": "reviewer_lane",
            "lane_id": "reviewer-1",
        }
    ]
    assert evaluate_pr_gate(evidence)["decision"] == "allowed"


def test_build_evidence_rejects_hosted_review_as_primary() -> None:
    review_evidence = clean_review_evidence()
    review_evidence["review_execution"] = "hosted"
    review_evidence["artifacts"][0]["review_execution"] = "hosted"

    with pytest.raises(EvidenceError, match="supplemental only"):
        build_evidence(
            pr_payload(),
            threads_payload(),
            review_source="independent_lane",
            review_evidence=review_evidence,
            resolver_roles=reviewer_resolver_roles(),
        )


def test_build_evidence_derives_sensitive_classification_and_approved_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_payload()
    head = base_sha()
    checkout_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    payload.update(
        {
            "headRefOid": checkout_head,
            "body": "Closes #97\nenforcement_sensitive: true",
            "closingIssuesReferences": [{"number": 97}],
        }
    )
    base = load_pack(ROOT)
    workflow = deepcopy(base.workflow)
    workflow["enforcement"]["sensitive_registry"]["paths"] = ["checks/**"]
    config = PackConfig(ROOT, workflow, base.states, base.labels)
    monkeypatch.setattr(
        "github_pr_evidence.build_approved_spec_evidence",
        lambda *_args, **_kwargs: {"issue": 97},
    )

    evidence = build_evidence(
        payload,
        threads_payload(),
        {"actor": "user", "source": "chat"},
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
        repo=ROOT,
        config=config,
        repository="majiayu000/specrail",
        approval_metadata={
            "approved_at": "2030-07-14T00:00:00Z",
            "spec_revisions": {},
            "maintainer_actor": "maintainer",
            "state_source": "label",
            "state_trusted": True,
            "default_base_ref": "main",
            "default_base_sha": head,
        },
        pr_snapshot=file_snapshot(
            ["checks/pr_gate.py"], head_sha=checkout_head
        ),
    )

    assert evidence["sensitive_classification"]["matched_paths"] == [
        "checks/pr_gate.py"
    ]
    assert evidence["approved_spec"]["issue"] == 97
    assert evidence["approved_spec"] == {"issue": 97}
    assert evidence["default_base_ref"] == "main"
    assert evidence["default_base_sha"] == head


def test_build_evidence_rejects_body_hint_approval_metadata() -> None:
    payload = pr_payload()
    head = base_sha()
    payload.update(
        {
            "body": "Closes #97\nenforcement_sensitive: true",
            "closingIssuesReferences": [{"number": 97}],
        }
    )
    base = load_pack(ROOT)
    workflow = deepcopy(base.workflow)
    workflow["enforcement"]["sensitive_registry"]["paths"] = ["checks/**"]
    config = PackConfig(ROOT, workflow, base.states, base.labels)

    with pytest.raises(EvidenceError, match="trusted maintainer label"):
        build_evidence(
            payload, threads_payload(), review_source="independent_lane",
            review_evidence=clean_review_evidence(),
            repo=ROOT, config=config, repository="majiayu000/specrail",
            approval_metadata={
                "approved_at": "2026-07-14T00:00:00Z",
                "spec_revisions": {},
                "maintainer_actor": "requester",
                "state_source": "body_hint",
                "state_trusted": False,
            },
            pr_snapshot=file_snapshot(["checks/pr_gate.py"]),
        )


@pytest.mark.parametrize(
    ("body", "issue", "expected"),
    [
        ("Refs #671", 671, True),
        ("- Refs #671\n", 671, True),
        ("* refs #671", 671, True),
        ("Refs GH-671", 671, False),
        ("Refs #6710", 671, False),
        ("Refs #67", 671, False),
        ("Discussion mentions #671", 671, False),
        ("Fixes #671", 671, False),
        ("This line says Refs #671 in prose", 671, False),
        ("```text\nRefs #671\n```", 671, False),
        ("~~~\n- Refs #671\n~~~", 671, False),
        ("<!--\nRefs #671\n-->", 671, False),
        ("<!-- Refs #671 -->", 671, False),
        ("    Refs #671", 671, False),
        ("\tRefs #671", 671, False),
        ("<!-- note -->\nRefs #671", 671, True),
        ("Refs #671 <!-- verified relation -->", 671, True),
        ("```text\n<!-- literal\n```\nRefs #671", 671, True),
        ("~~~text\n<!-- literal\n~~~\n- Refs #671", 671, True),
        ("`<!-- literal`\nRefs #671", 671, True),
        ("    <!-- literal\nRefs #671", 671, True),
        ("\t<!-- literal\nRefs #671", 671, True),
        ("<!--\n    -->\nRefs #671", 671, True),
        ("`code\nRefs #671\nend`", 671, False),
        ("``code\n- Refs #671\nend``", 671, False),
        ("`code\n<!-- literal\nend`\nRefs #671", 671, True),
        ("``code\n<!-- literal\nend``\n- Refs #671", 671, True),
        ("`code\n``\nRefs #671\n`", 671, False),
    ],
)
def test_partial_reference_text_is_an_exact_standalone_directive(
    body: str,
    issue: int,
    expected: bool,
) -> None:
    assert references_partial_issue(body, issue) is expected


@pytest.mark.parametrize("invalid_issue", [True, False])
def test_partial_reference_direct_calls_reject_boolean_issue_numbers(
    invalid_issue: bool,
) -> None:
    with pytest.raises(EvidenceError, match="positive integer"):
        references_partial_issue("Refs #1", invalid_issue)

    payload = pr_payload()
    payload["closingIssuesReferences"] = [{"number": 1}]
    with pytest.raises(EvidenceError, match="positive integer"):
        normalize_issue_reference(payload, expected_issue=invalid_issue)

    with pytest.raises(EvidenceError, match="positive integer"):
        collect_evidence("majiayu000/specrail", 10, None, expected_issue=invalid_issue)


def test_build_evidence_records_other_closing_issues_without_reclassifying_expected_partial() -> None:
    payload = pr_payload()
    payload["body"] = "## Issue Links\n\n- Closes #806\n- Refs #671\n"
    payload["closingIssuesReferences"] = [{"number": 806}]

    evidence = build_evidence(
        payload,
        threads_payload(),
        {"actor": "user", "source": "chat"},
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
        expected_issue=671,
        issue_payload={
            "number": 671,
            "state": "OPEN",
            "url": "https://github.com/majiayu000/remem/issues/671",
        },
    )

    assert evidence["linked_issue"] == 671
    assert evidence["issue_reference"] == {
        "number": 671,
        "kind": "partial",
        "source": "pr_body",
        "verified": True,
        "state": "OPEN",
        "url": "https://github.com/majiayu000/remem/issues/671",
        "closing_issue_numbers": [806],
    }


def test_expected_issue_uses_closing_relation_when_target_itself_is_closing() -> None:
    payload = pr_payload()
    payload["body"] = "Closes #9\nRefs #671"
    payload["closingIssuesReferences"] = [{"number": 9}, {"number": 671}]

    linked_issue, relation = normalize_issue_reference(payload, expected_issue=671)

    assert linked_issue == 671
    assert relation == {
        "number": 671,
        "kind": "closing",
        "source": "closingIssuesReferences",
        "verified": True,
        "closing_issue_numbers": [9, 671],
    }


@pytest.mark.parametrize(
    "closing_references",
    [
        [True],
        [{"number": True}],
        [{"number": 9}, {"number": 9}],
    ],
)
def test_closing_issue_reference_payload_must_be_well_formed(
    closing_references: list[object],
) -> None:
    payload = pr_payload()
    payload["closingIssuesReferences"] = closing_references

    with pytest.raises(EvidenceError, match="closingIssuesReferences"):
        normalize_issue_reference(payload)


@pytest.mark.parametrize(
    ("body", "issue_payload", "error"),
    [
        ("Mentions #671", {"number": 671, "state": "OPEN", "url": "https://example/671"}, "Refs"),
        ("Refs #670", {"number": 671, "state": "OPEN", "url": "https://example/671"}, "Refs"),
        ("Refs #671", None, "live issue"),
        ("Refs #671", {"number": 670, "state": "OPEN", "url": "https://example/670"}, "number"),
        ("Refs #671", {"number": 671, "state": "CLOSED", "url": "https://example/671"}, "OPEN"),
    ],
)
def test_partial_issue_state_and_reference_mismatches_fail_closed(
    body: str,
    issue_payload: dict[str, object] | None,
    error: str,
) -> None:
    payload = pr_payload()
    payload["body"] = body
    payload["closingIssuesReferences"] = [{"number": 806}]

    with pytest.raises(EvidenceError, match=error):
        normalize_issue_reference(payload, expected_issue=671, issue_payload=issue_payload)


def test_build_evidence_maps_resolver_role_from_lane_roster() -> None:
    payload = threads_payload()
    thread = payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]  # type: ignore[index]
    assert isinstance(thread, dict)
    thread.pop("resolverRole")

    evidence = build_evidence(
        pr_payload(),
        payload,
        {
            "actor": "user",
            "source": "chat",
        },
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
    )

    assert evidence["review_threads"][0]["resolver_role"] == "reviewer_lane"
    assert evidence["review_threads"][0]["lane_id"] == "reviewer-1"
    assert evidence["review_threads"][0]["original_author"] == "reviewer"
    assert evidence["review_threads"][0]["original_comment_id"] == "PRRC_kwDOExampleRoot"
    assert evaluate_pr_gate(evidence)["decision"] == "allowed"


def test_resolver_role_map_supports_thread_specific_lane_override(
    tmp_path: Path,
) -> None:
    payload = threads_payload()
    nodes = payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]  # type: ignore[index]
    assert isinstance(nodes, list)
    first = nodes[0]
    assert isinstance(first, dict)
    first.pop("resolverRole")
    second = deepcopy(first)
    second["id"] = "PRRT_kwDOSecond"
    second["comments"]["nodes"][0]["id"] = "PRRC_kwDOSecondRoot"  # type: ignore[index]
    second["comments"]["nodes"][0]["author"] = {"login": "bot"}  # type: ignore[index]
    nodes.append(second)
    role_map = tmp_path / "resolver-map.json"
    role_map.write_text(
        json.dumps(
            {
                "resolver_roles": {
                    "reviewer": {
                        "resolver_role": "reviewer_lane",
                        "lane_id": "reviewer-root",
                    }
                },
                "thread_resolver_roles": {
                    "PRRT_kwDOSecond": {
                        "resolver_login": "reviewer",
                        "resolver_role": "reviewer_lane",
                        "lane_id": "reviewer-successor",
                        "successor_of": "bot-root",
                        "re_review_artifact_id": "current-clean",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    normalized = normalize_review_threads(
        payload,
        load_resolver_role_map(str(role_map)),
    )

    assert normalized[0]["lane_id"] == "reviewer-root"
    assert normalized[1]["lane_id"] == "reviewer-successor"
    assert normalized[1]["successor_of"] == "bot-root"
    assert normalized[1]["re_review_artifact_id"] == "current-clean"

    role_map.write_text(
        json.dumps(
            {
                "resolver_roles": {
                    "reviewer": {
                        "resolver_role": "reviewer_lane",
                        "lane_id": "reviewer-root",
                    }
                },
                "thread_resolver_roles": {
                    "PRRT_kwDOSecond": {
                        "resolver_login": "someone-else",
                        "resolver_role": "human",
                        "authorized_human_maintainer": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    mismatched = normalize_review_threads(
        payload,
        load_resolver_role_map(str(role_map)),
    )

    assert mismatched[1]["resolver_role"] == "reviewer_lane"
    assert mismatched[1]["lane_id"] == "reviewer-root"
    assert "authorized_human_maintainer" not in mismatched[1]


def test_thread_specific_resolver_override_requires_resolver_login(
    tmp_path: Path,
) -> None:
    role_map = tmp_path / "resolver-map.json"
    role_map.write_text(
        json.dumps(
            {
                "resolver_roles": {},
                "thread_resolver_roles": {
                    "PRRT_kwDOExample": {
                        "resolver_role": "human",
                        "authorized_human_maintainer": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvidenceError, match="resolver_login"):
        load_resolver_role_map(str(role_map))


@pytest.mark.parametrize(
    ("root_mutation", "message"),
    [
        ({"id": None}, "requires id"),
        ({"author": None}, "requires author.login"),
    ],
)
def test_build_evidence_requires_root_comment_identity(
    root_mutation: dict[str, object],
    message: str,
) -> None:
    payload = threads_payload()
    root = payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["comments"]["nodes"][0]  # type: ignore[index]
    root.update(root_mutation)  # type: ignore[union-attr]

    with pytest.raises(EvidenceError, match=message):
        build_evidence(
            pr_payload(),
            payload,
            review_source="independent_lane",
            review_evidence=clean_review_evidence(),
            resolver_roles=reviewer_resolver_roles(),
        )


def test_build_evidence_without_authorization_needs_human() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
    )

    assert "human_authorization" not in evidence
    result = evaluate_pr_gate(evidence)
    assert result["decision"] == "needs_human"
    assert "human_authorization" in result["missing"]


def test_build_evidence_can_record_merge_dispatch_ordering() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        {
            "actor": "user",
            "source": "chat",
        },
        "2026-07-04T00:00:10Z",
        "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
    )

    assert evidence["merge_dispatched_at"] == "2026-07-04T00:00:10Z"
    assert evidence["merge_head_sha"] == "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"


def test_authorization_flags_must_include_actor_and_source() -> None:
    assert build_human_authorization(None, None, None) is None
    assert build_human_authorization("user", "chat", "approved") == {
        "actor": "user",
        "source": "chat",
        "summary": "approved",
    }

    with pytest.raises(EvidenceError):
        build_human_authorization("user", None, None)

    with pytest.raises(EvidenceError):
        build_human_authorization(None, None, "approved")


def _round_cap_authorization() -> dict[str, object]:
    return {
        "authorization_id": "RCA-10-4",
        "pr": 10,
        "prior_head_sha": "a" * 40,
        "target_head_sha": "b" * 40,
        "review_round": 4,
        "decision": "continue_once",
        "actor": "maintainer",
        "source": "maintainer decision in issue #10",
        "authorized_at": "2026-07-23T12:00:00+08:00",
    }


def _write_round_cap_files(
    tmp_path: Path,
    authorization: dict[str, object] | None = None,
    role_entry: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    authorization_path = tmp_path / "round-cap-authorization.json"
    authorization_path.write_text(
        json.dumps(authorization or _round_cap_authorization()),
        encoding="utf-8",
    )
    role_map_path = tmp_path / "maintainer-role-map.json"
    role_map_path.write_text(
        json.dumps(
            {
                "maintainer_roles": {
                    "maintainer": role_entry
                    or {
                        "role": "maintainer",
                        "authorized_human_maintainer": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return authorization_path, role_map_path


def test_round_cap_authorization_requires_explicit_maintainer_role_map(
    tmp_path: Path,
) -> None:
    authorization_path, role_map_path = _write_round_cap_files(tmp_path)

    normalized = load_round_cap_authorizations(
        [str(authorization_path)],
        load_maintainer_role_map(str(role_map_path)),
    )

    assert normalized == [
        {
            **_round_cap_authorization(),
            "authorized_human_maintainer": True,
        }
    ]
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
        round_cap_authorizations=normalized,
    )
    assert evidence["round_cap_authorizations"] == normalized
    with pytest.raises(EvidenceError, match="explicitly authorized maintainer"):
        load_round_cap_authorizations([str(authorization_path)], {})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"decision": "merge"}, "continue_once"),
        ({"review_round": 3}, "greater than 3"),
        ({"pr": True}, "positive integer"),
        ({"prior_head_sha": "not-a-sha"}, "40-character Git SHA"),
        ({"target_head_sha": "a" * 40}, "distinct prior and target"),
        ({"authorized_at": "2026-07-23T12:00:00"}, "include a timezone"),
        ({"authorized_human_maintainer": True}, "unsupported fields"),
    ],
)
def test_round_cap_authorization_rejects_non_exact_input(
    tmp_path: Path,
    mutation: dict[str, object],
    message: str,
) -> None:
    payload = _round_cap_authorization()
    payload.update(mutation)
    authorization_path, role_map_path = _write_round_cap_files(
        tmp_path,
        authorization=payload,
    )

    with pytest.raises(EvidenceError, match=message):
        load_round_cap_authorizations(
            [str(authorization_path)],
            load_maintainer_role_map(str(role_map_path)),
        )


def test_round_cap_authorization_role_map_is_closed(
    tmp_path: Path,
) -> None:
    authorization_path, role_map_path = _write_round_cap_files(
        tmp_path,
        role_entry={
            "role": "maintainer",
            "authorized_human_maintainer": True,
            "inferred_from_github": True,
        },
    )

    with pytest.raises(EvidenceError, match="must contain only"):
        load_maintainer_role_map(str(role_map_path))

    role_map_path.write_text(
        json.dumps(
            {
                "maintainer_roles": {
                    "maintainer": {
                        "role": "reviewer_lane",
                        "authorized_human_maintainer": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceError, match="role must be maintainer"):
        load_round_cap_authorizations(
            [str(authorization_path)],
            load_maintainer_role_map(str(role_map_path)),
        )


def test_round_cap_authorization_ids_are_unique(tmp_path: Path) -> None:
    authorization_path, role_map_path = _write_round_cap_files(tmp_path)

    with pytest.raises(EvidenceError, match="duplicated"):
        load_round_cap_authorizations(
            [str(authorization_path), str(authorization_path)],
            load_maintainer_role_map(str(role_map_path)),
        )


def test_merge_authorization_does_not_create_round_cap_authorization() -> None:
    evidence = build_evidence(
        pr_payload(),
        threads_payload(),
        {"actor": "maintainer", "source": "implx auto"},
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
    )

    assert "human_authorization" in evidence
    assert "round_cap_authorizations" not in evidence


def test_pr_gate_schema_closes_round_audit_and_cap_authorizations() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "pr_review_gate.schema.json").read_text(encoding="utf-8")
    )
    authorization_schema = schema["properties"]["round_cap_authorizations"]
    normalized_authorization = {
        **_round_cap_authorization(),
        "authorized_human_maintainer": True,
    }
    validate_instance(authorization_schema, [normalized_authorization])
    unknown_authorization = {
        **normalized_authorization,
        "scope_alias": "future rounds",
    }
    with pytest.raises(SpecRailError, match="scope_alias"):
        validate_instance(authorization_schema, [unknown_authorization])

    round_audit_schema = schema["properties"]["review_evidence"]["properties"][
        "round_audit"
    ]
    round_audit = {
        "policy": "bounded_diff_v1",
        "cap": 3,
        "total_rounds": 1,
        "rounds": [
            {
                "artifact_id": "pr10-round-1",
                "review_round": 1,
                "review_mode": "full",
                "base_head_sha": None,
                "head_sha": "a" * 40,
                "diff_sha256": None,
                "escalation_authorization_id": None,
            }
        ],
    }
    validate_instance(round_audit_schema, round_audit)
    round_audit["rounds"][0]["caller_claimed_round"] = 99
    with pytest.raises(SpecRailError, match="caller_claimed_round"):
        validate_instance(round_audit_schema, round_audit)
