from __future__ import annotations

import base64
import hashlib
import subprocess
from copy import deepcopy

import pytest

from github_pr_evidence_test_support import (
    ROOT,
    approval_query_payload,
    base_sha,
    clean_review_evidence,
    file_snapshot,
    pr_payload,
    reviewer_resolver_roles,
    snapshot_page,
    threads_payload,
)
from github_approved_spec_evidence import (  # noqa: E402
    collect_approval_metadata,
    collect_spec_revision_approval,
)
from github_pr_evidence import (  # noqa: E402
    EvidenceError,
    build_evidence,
    collect_issue_view,
    run_gh_json,
)
from github_pr_snapshot import (  # noqa: E402
    assert_same_pr_file_snapshot,
    collect_pr_file_snapshot,
    derive_spec_refs,
)
from sensitive_enforcement import classify_sensitive_changes  # noqa: E402
from spec_revision_evidence import spec_artifacts_sha256_from_hashes  # noqa: E402
from specrail_lib import PackConfig, load_pack  # noqa: E402


def test_approval_metadata_collects_complete_label_timeline() -> None:
    calls: list[list[str]] = []

    def fake_run_json(args: list[str]) -> object:
        calls.append(args)
        return approval_query_payload()

    metadata = collect_approval_metadata("example/repo", 97, fake_run_json)

    assert metadata["approved_at"] == "2026-07-14T00:00:00Z"
    assert metadata["default_base_ref"] == "main"
    assert metadata["default_base_sha"] == base_sha()
    assert len(calls) == 2


def test_approval_metadata_blocks_incomplete_timeline_page() -> None:
    payload = approval_query_payload()
    payload["data"]["repository"]["issue"]["timelineItems"]["pageInfo"] = {}

    with pytest.raises(EvidenceError, match="pageInfo is incomplete"):
        collect_approval_metadata("example/repo", 97, lambda _args: payload)


def test_approval_metadata_blocks_incomplete_latest_matching_event() -> None:
    payload = approval_query_payload()
    payload["data"]["repository"]["issue"]["timelineItems"]["nodes"] = [
        {
            "createdAt": "2026-07-13T00:00:00Z",
            "actor": {"login": "old-maintainer"},
            "label": {"name": "ready_to_implement"},
        },
        {
            "createdAt": "2026-07-14T00:00:00Z",
            "actor": None,
            "label": {"name": "ready_to_implement"},
        },
    ]

    with pytest.raises(EvidenceError, match="actor/timestamp"):
        collect_approval_metadata("example/repo", 97, lambda _args: payload)


def test_approval_metadata_paginates_more_than_100_events() -> None:
    first = approval_query_payload()
    second = approval_query_payload()
    first_labels = first["data"]["repository"]["issue"]["labels"]
    first_labels["nodes"] = [{"name": f"label-{index}"} for index in range(100)]
    first_labels["pageInfo"] = {"hasNextPage": True, "endCursor": "next"}
    label_responses = [first, second]

    def fake_run(args: list[str]) -> object:
        if "SpecRailApprovalLabels" in args[-1]:
            return label_responses.pop(0)
        return approval_query_payload()

    metadata = collect_approval_metadata(
        "example/repo", 97, fake_run
    )

    assert metadata["maintainer_actor"] == "maintainer"


def test_approval_metadata_blocks_pagination_drift() -> None:
    first = approval_query_payload()
    second = approval_query_payload()
    first["data"]["repository"]["issue"]["labels"]["pageInfo"] = {
        "hasNextPage": True, "endCursor": "next"
    }
    second["data"]["repository"]["defaultBranchRef"]["name"] = "other"
    responses = [first, second]

    with pytest.raises(EvidenceError, match="drifted"):
        collect_approval_metadata(
            "example/repo", 97, lambda _args: responses.pop(0)
        )


def test_approval_metadata_blocks_default_base_sha_drift() -> None:
    first = approval_query_payload()
    second = approval_query_payload()
    first["data"]["repository"]["issue"]["labels"]["pageInfo"] = {
        "hasNextPage": True, "endCursor": "next"
    }
    second["data"]["repository"]["defaultBranchRef"]["target"]["oid"] = "c" * 40
    responses = [first, second]

    with pytest.raises(EvidenceError, match="drifted"):
        collect_approval_metadata(
            "example/repo", 97, lambda _args: responses.pop(0)
        )


def test_approval_metadata_requires_merged_pr_for_each_spec() -> None:
    responses: list[object] = [
        approval_query_payload(), approval_query_payload(), []
    ]

    with pytest.raises(EvidenceError, match="exactly one merged"):
        collect_approval_metadata(
            "example/repo", 97, lambda _args: responses.pop(0),
            spec_source_commits={"specs/GH97/product.md": "a" * 40},
        )


def test_approval_metadata_records_merged_spec_pr() -> None:
    responses: list[object] = [
        approval_query_payload(),
        approval_query_payload(),
        [{
            "number": 7,
            "merged_at": "2026-07-13T00:00:00Z",
            "merge_commit_sha": "b" * 40,
            "base": {"ref": "main"},
        }],
    ]

    metadata = collect_approval_metadata(
        "example/repo", 97, lambda _args: responses.pop(0),
        spec_source_commits={"specs/GH97/product.md": "a" * 40},
    )

    assert metadata["spec_revisions"]["specs/GH97/product.md"]["pr_number"] == 7


def test_approval_metadata_rejects_wrong_json_shapes() -> None:
    with pytest.raises(EvidenceError, match="JSON object"):
        collect_approval_metadata("example/repo", 97, lambda _args: [])

    responses: list[object] = [
        approval_query_payload(), approval_query_payload(), {"not": "an array"}
    ]
    with pytest.raises(EvidenceError, match="JSON array"):
        collect_approval_metadata(
            "example/repo", 97, lambda _args: responses.pop(0),
            spec_source_commits={"specs/GH97/product.md": "a" * 40},
        )


def _spec_revision_payload(
    query: str,
    *,
    lifecycle: str = "spec_approved",
    head_sha: str = "a" * 40,
    review_commit: str | None = None,
    has_next: bool = False,
    cursor: str | None = None,
) -> dict[str, object]:
    issue: dict[str, object] = {"state": "OPEN"}
    pull: dict[str, object] = {"headRefOid": head_sha}
    page_info = {"hasNextPage": has_next, "endCursor": cursor}
    if "SpecRevisionLabels" in query:
        issue["labels"] = {
            "pageInfo": page_info,
            "nodes": [{"id": "label-1", "name": lifecycle}],
        }
    elif "SpecRevisionTimeline" in query:
        issue["timelineItems"] = {
            "pageInfo": page_info,
            "nodes": [{
                "id": "event-1",
                "createdAt": "2026-07-23T01:00:00Z",
                "actor": {"login": "maintainer"},
                "label": {"name": lifecycle},
            }],
        }
    else:
        pull["reviews"] = {
            "pageInfo": page_info,
            "nodes": [{
                "id": "review-1",
                "state": "APPROVED",
                "submittedAt": "2026-07-23T02:00:00Z",
                "url": "https://github.com/example/repo/pull/10#pullrequestreview-1",
                "author": {"login": "maintainer"},
                "commit": {"oid": review_commit or head_sha},
            }],
        }
    return {"data": {"repository": {"issue": issue, "pullRequest": pull}}}


def _spec_revision_runner(
    *,
    lifecycle: str = "spec_approved",
    head_sha: str = "a" * 40,
    review_commit: str | None = None,
    permission: str = "maintain",
    artifact: bytes = b"approved spec\n",
) -> object:
    def run(args: list[str]) -> object:
        endpoint = args[-1]
        if endpoint.startswith("query="):
            return _spec_revision_payload(
                endpoint,
                lifecycle=lifecycle,
                head_sha=head_sha,
                review_commit=review_commit,
            )
        if "/collaborators/" in endpoint:
            return {"permission": permission}
        if "/contents/" in endpoint:
            return {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(artifact).decode("ascii"),
            }
        raise AssertionError(args)

    return run


def test_spec_revision_approval_collects_closed_exact_head_contract() -> None:
    path = "specs/GH168/product.md"
    content = b"approved spec\n"
    expected_digest = spec_artifacts_sha256_from_hashes(
        {path: hashlib.sha256(content).hexdigest()}
    )

    approval = collect_spec_revision_approval(
        "example/repo", 168, 10, "a" * 40, (path,),
        _spec_revision_runner(artifact=content),  # type: ignore[arg-type]
    )

    assert approval == {
        "lifecycle_state": "spec_approved",
        "state_source": "label",
        "state_trusted": True,
        "maintainer_actor": "maintainer",
        "approved_at": "2026-07-23T02:00:00Z",
        "approval_source": "github_pr_review",
        "approval_url": "https://github.com/example/repo/pull/10#pullrequestreview-1",
        "commit_oid": "a" * 40,
        "artifact_paths": [path],
        "spec_artifacts_sha256": expected_digest,
    }


@pytest.mark.parametrize(
    ("lifecycle", "review_commit", "permission", "message"),
    [
        ("spec_review", None, "maintain", "spec_approved"),
        ("spec_approved", "b" * 40, "maintain", "exact-head"),
        ("spec_approved", None, "read", "not from a maintainer"),
    ],
)
def test_spec_revision_approval_fails_closed(
    lifecycle: str,
    review_commit: str | None,
    permission: str,
    message: str,
) -> None:
    with pytest.raises(EvidenceError, match=message):
        collect_spec_revision_approval(
            "example/repo", 168, 10, "a" * 40,
            ("specs/GH168/product.md",),
            _spec_revision_runner(
                lifecycle=lifecycle,
                review_commit=review_commit,
                permission=permission,
            ),  # type: ignore[arg-type]
        )


def test_spec_revision_approval_blocks_pagination_head_drift() -> None:
    calls = 0

    def run(args: list[str]) -> object:
        nonlocal calls
        endpoint = args[-1]
        if endpoint.startswith("query="):
            calls += 1
            return _spec_revision_payload(
                endpoint,
                head_sha="a" * 40 if calls == 1 else "b" * 40,
                has_next=calls == 1,
                cursor="next" if calls == 1 else None,
            )
        raise AssertionError(args)

    with pytest.raises(EvidenceError, match="drifted during pagination"):
        collect_spec_revision_approval(
            "example/repo", 168, 10, "a" * 40,
            ("specs/GH168/product.md",), run,
        )


def _spec_revision_build_inputs() -> tuple[
    dict[str, object], PackConfig, dict[str, object], dict[str, object]
]:
    payload = pr_payload()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    payload.update({
        "headRefOid": head,
        "body": "Closes #168\nenforcement_sensitive: true",
        "closingIssuesReferences": [{"number": 168}],
    })
    base = load_pack(ROOT)
    workflow = deepcopy(base.workflow)
    workflow["enforcement"]["sensitive_registry"]["specs"] = ["specs/GH*/**"]
    config = PackConfig(ROOT, workflow, base.states, base.labels)
    path = "specs/GH168/product.md"
    snapshot = file_snapshot([path], head_sha=head)
    approval = {
        "lifecycle_state": "spec_approved",
        "state_source": "label",
        "state_trusted": True,
        "maintainer_actor": "maintainer",
        "approved_at": "2026-07-23T02:00:00Z",
        "approval_source": "github_pr_review",
        "approval_url": (
            "https://github.com/majiayu000/specrail/"
            "pull/178#pullrequestreview-1"
        ),
        "commit_oid": head,
        "artifact_paths": [path],
        "spec_artifacts_sha256": "a" * 64,
    }
    return payload, config, snapshot, approval


def _build_spec_revision_evidence(spec_approval: object) -> dict[str, object]:
    payload, config, snapshot, _approval = _spec_revision_build_inputs()
    return build_evidence(
        payload,
        threads_payload(),
        {"actor": "user", "source": "chat"},
        review_source="independent_lane",
        review_evidence=clean_review_evidence(),
        resolver_roles=reviewer_resolver_roles(),
        repo=ROOT,
        config=config,
        repository="majiayu000/specrail",
        pr_snapshot=snapshot,
        spec_approval=spec_approval,  # type: ignore[arg-type]
    )


def test_build_evidence_emits_collected_spec_revision_contract() -> None:
    _payload, _config, _snapshot, approval = _spec_revision_build_inputs()

    evidence = _build_spec_revision_evidence(approval)

    assert evidence["sensitive_route"] == "spec_revision"
    assert evidence["spec_approval"] == approval
    assert "approved_spec" not in evidence


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("not_object", "trusted spec approval"),
        ("partial", "field contract is incomplete"),
        ("old_head", "commit must match"),
        ("wrong_path", "artifacts must match"),
    ],
)
def test_build_evidence_rejects_invalid_collected_spec_revision_contract(
    mutation: str,
    message: str,
) -> None:
    payload, _config, _snapshot, approval = _spec_revision_build_inputs()
    if mutation == "not_object":
        candidate: object = None
    else:
        candidate = dict(approval)
        if mutation == "partial":
            candidate.pop("approval_url")
        elif mutation == "old_head":
            candidate["commit_oid"] = "b" * 40
        else:
            candidate["artifact_paths"] = ["specs/GH168/tech.md"]

    with pytest.raises(EvidenceError, match=message):
        _build_spec_revision_evidence(candidate)


def test_pr_file_snapshot_finds_sensitive_path_after_first_100() -> None:
    first = [f"docs/file-{index}.md" for index in range(100)]
    pages = [
        snapshot_page(first, total=101, has_next=True, cursor="page-2"),
        snapshot_page(["checks/pr_gate.py"], total=101, has_next=False, cursor=None),
    ]
    snapshot = collect_pr_file_snapshot(
        "majiayu000", "specrail", 10, lambda _args: pages.pop(0)
    )
    base = load_pack(ROOT)
    workflow = deepcopy(base.workflow)
    workflow["enforcement"]["sensitive_registry"]["paths"] = ["checks/**"]
    config = PackConfig(ROOT, workflow, base.states, base.labels)

    classification = classify_sensitive_changes(
        config, ROOT, snapshot["paths"], [], source="github_changed_files"
    )

    assert snapshot["path_count"] == 101
    assert classification["matched_paths"] == ["checks/pr_gate.py"]


@pytest.mark.parametrize("spec_index", [10, 100])
def test_complete_snapshot_derives_specs_only_registry_match(
    spec_index: int,
) -> None:
    paths = [f"docs/file-{index}.md" for index in range(101)]
    paths[spec_index] = "specs/GH97/tech.md"
    pages = [
        snapshot_page(paths[:100], total=101, has_next=True, cursor="page-2"),
        snapshot_page(paths[100:], total=101, has_next=False, cursor=None),
    ]
    snapshot = collect_pr_file_snapshot(
        "majiayu000", "specrail", 10, lambda _args: pages.pop(0)
    )
    base = load_pack(ROOT)
    workflow = deepcopy(base.workflow)
    workflow["enforcement"]["sensitive_registry"]["specs"] = ["specs/GH*/**"]
    config = PackConfig(ROOT, workflow, base.states, base.labels)
    spec_refs = derive_spec_refs(config, ROOT, None, snapshot["paths"])

    classification = classify_sensitive_changes(
        config, ROOT, snapshot["paths"], spec_refs, source="github_changed_files"
    )

    assert classification["matched_specs"] == ["specs/GH97/tech.md"]


def test_pr_file_snapshot_rejects_incomplete_pagination() -> None:
    page = snapshot_page(
        [f"docs/file-{index}.md" for index in range(100)],
        total=101,
        has_next=False,
        cursor=None,
    )

    with pytest.raises(EvidenceError, match="collected 100 of 101"):
        collect_pr_file_snapshot(
            "majiayu000", "specrail", 10, lambda _args: page
        )


def test_pr_file_snapshot_rejects_double_snapshot_drift() -> None:
    before = file_snapshot(["README.md"])
    after = file_snapshot(["README.md", "checks/pr_gate.py"])

    with pytest.raises(EvidenceError, match="snapshot drifted"):
        assert_same_pr_file_snapshot(before, after)


def test_pr_file_snapshot_includes_sensitive_rename_source_path() -> None:
    graph = snapshot_page(["docs/safe.py"], total=1, has_next=False, cursor=None)
    snapshot = collect_pr_file_snapshot(
        "majiayu000", "specrail", 10, lambda _args: graph,
        lambda _args: [{
            "filename": "docs/safe.py",
            "previous_filename": "checks/pr_gate.py",
        }],
    )
    base = load_pack(ROOT)
    workflow = deepcopy(base.workflow)
    workflow["enforcement"]["sensitive_registry"]["paths"] = ["checks/**"]
    config = PackConfig(ROOT, workflow, base.states, base.labels)

    classification = classify_sensitive_changes(
        config, ROOT, snapshot["paths"], [], source="github_changed_files"
    )

    assert snapshot["file_count"] == 1
    assert classification["matched_paths"] == ["checks/pr_gate.py"]


def test_pr_file_snapshot_rejects_non_array_rest_response() -> None:
    graph = snapshot_page(["docs/safe.py"], total=1, has_next=False, cursor=None)

    with pytest.raises(EvidenceError, match="JSON array"):
        collect_pr_file_snapshot(
            "majiayu000", "specrail", 10, lambda _args: graph,
            lambda _args: {"filename": "docs/safe.py"},
        )


def test_production_runner_array_reaches_rest_array_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = snapshot_page(["docs/safe.py"], total=1, has_next=False, cursor=None)
    completed = subprocess.CompletedProcess(
        args=["gh"], returncode=0,
        stdout='[{"filename":"docs/safe.py"}]', stderr="",
    )
    monkeypatch.setattr("github_pr_evidence.subprocess.run", lambda *_args, **_kwargs: completed)

    snapshot = collect_pr_file_snapshot(
        "majiayu000", "specrail", 10, lambda _args: graph, run_gh_json
    )

    assert snapshot["paths"] == ["docs/safe.py"]


def test_object_collector_rejects_production_runner_array_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("github_pr_evidence.run_gh_json", lambda _args: [])

    with pytest.raises(EvidenceError, match="JSON object"):
        collect_issue_view("example/repo", 1)
