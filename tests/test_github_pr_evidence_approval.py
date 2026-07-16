from __future__ import annotations

import subprocess
from copy import deepcopy

import pytest

from github_pr_evidence_test_support import (
    ROOT,
    approval_query_payload,
    base_sha,
    file_snapshot,
    snapshot_page,
)
from github_approved_spec_evidence import collect_approval_metadata  # noqa: E402
from github_pr_evidence import EvidenceError, collect_issue_view, run_gh_json  # noqa: E402
from github_pr_snapshot import (  # noqa: E402
    assert_same_pr_file_snapshot,
    collect_pr_file_snapshot,
    derive_spec_refs,
)
from sensitive_enforcement import classify_sensitive_changes  # noqa: E402
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
