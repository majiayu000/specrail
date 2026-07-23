from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from github_pr_evidence_test_support import (
    ROOT,
    clean_review_evidence,
    file_snapshot,
    pr_payload,
    threads_payload,
)
from evidence_content_binding import (  # noqa: E402
    build_component_binding,
    build_content_binding,
    content_bindings_match,
    hash_code_inputs,
    hash_pr_metadata,
    hash_spec_files,
    load_versioned_pr_evidence,
    normalize_repo_path,
    validate_component_binding,
    validate_content_binding,
)
from github_pr_evidence import (  # noqa: E402
    EvidenceError,
    _collect_content_binding,
    build_evidence,
    collect_evidence,
    main as github_evidence_main,
)
from github_evidence_common import trusted_ci_coverage  # noqa: E402
from specrail_lib import PackConfig, load_pack  # noqa: E402


PACK = load_pack(ROOT)


def _pack_config(
    repo: Path = ROOT,
    *,
    coverage: dict[str, list[str]] | None = None,
    spec_root: str | None = None,
) -> PackConfig:
    workflow = deepcopy(PACK.workflow)
    if coverage is not None:
        workflow["evidence"]["ci_component_coverage"] = coverage
    if spec_root is not None:
        packet = f"{spec_root}/GH{{issue_number}}"
        workflow["artifacts"].update({
            "spec_packet": packet + "/",
            "product_spec": packet + "/product.md",
            "tech_spec": packet + "/tech.md",
            "task_plan": packet + "/tasks.md",
        })
    return PackConfig(repo, workflow, PACK.states, PACK.labels)


def test_content_binding_code_hash_includes_base_tree() -> None:
    patch = b"diff --git a/a.py b/a.py\n"

    assert hash_code_inputs("a" * 40, patch) != hash_code_inputs("b" * 40, patch)


def test_content_binding_spec_hash_binds_paths_lengths_and_raw_bytes() -> None:
    original = {
        "specs/GH1/product.md": b"abc",
        "specs/GH1/tech.md": b"def",
    }
    reordered = dict(reversed(list(original.items())))
    renamed = {
        "specs/GH1/product-renamed.md": b"abc",
        "specs/GH1/tech.md": b"def",
    }
    split = {
        "specs/GH1/product.md": b"a",
        "specs/GH1/tech.md": b"bcdef",
    }

    assert hash_spec_files(original) == hash_spec_files(reordered)
    assert hash_spec_files(original) != hash_spec_files(renamed)
    assert hash_spec_files(original) != hash_spec_files(split)
    assert hash_spec_files({"specs/GH1/a": b"bc"}) != hash_spec_files(
        {"specs/GH1/ab": b"c"}
    )


def test_content_binding_metadata_is_canonical_json() -> None:
    first = {"title": "x", "relation": {"number": 1, "verified": True}}
    second = {"relation": {"verified": True, "number": 1}, "title": "x"}

    assert hash_pr_metadata(first) == hash_pr_metadata(second)


def test_content_binding_coverage_matcher_is_closed_and_fail_closed() -> None:
    current = build_content_binding(
        "a" * 40,
        "b" * 40,
        b"patch",
        {"specs/GH1/product.md": b"spec"},
        {"title": "PR"},
    )
    component = build_component_binding(
        ["code_inputs", "spec_files"], current["content_hashes"]
    )

    assert content_bindings_match(component, current["content_hashes"])
    component["content_bindings"].pop("spec_files")
    with pytest.raises(EvidenceError, match="keys must equal"):
        content_bindings_match(component, current["content_hashes"])


def test_content_binding_rejects_ambiguous_or_partial_inputs() -> None:
    with pytest.raises(EvidenceError, match="normalized repo-relative"):
        normalize_repo_path("../specs/GH1/product.md")
    with pytest.raises(EvidenceError, match="object ID"):
        hash_code_inputs("not-an-oid", b"patch")
    with pytest.raises(EvidenceError, match="must be bytes"):
        hash_code_inputs("a" * 40, "patch")  # type: ignore[arg-type]
    with pytest.raises(EvidenceError, match="duplicate spec file"):
        hash_spec_files([("specs/GH1/a", b"x"), ("specs/GH1/a", b"x")])
    with pytest.raises(EvidenceError, match="must be bytes"):
        hash_spec_files({"specs/GH1/a": "x"})  # type: ignore[dict-item]
    with pytest.raises(EvidenceError, match="canonical JSON"):
        hash_pr_metadata({"value": float("nan")})
    with pytest.raises(EvidenceError, match="version"):
        validate_content_binding({"content_binding_version": 2})
    with pytest.raises(EvidenceError, match="must contain the closed"):
        validate_content_binding({
            "content_binding_version": 1,
            "snapshot": {},
            "content_hashes": {},
        })
    untrusted = build_content_binding(
        "a" * 40, "b" * 40, b"patch", {}, {"title": "PR"}
    )
    untrusted["snapshot"]["collector"] = "caller_supplied"
    with pytest.raises(EvidenceError, match="trusted github_pr_evidence"):
        validate_content_binding(untrusted)
    with pytest.raises(EvidenceError, match="duplicates"):
        validate_component_binding({
            "content_binding_version": 1,
            "covered_categories": ["code_inputs", "code_inputs"],
            "content_bindings": {"code_inputs": "a" * 64},
        })


def test_content_binding_workflow_check_is_spec_aware() -> None:
    current = build_content_binding(
        "a" * 40, "b" * 40, b"patch",
        {"specs/GH1/product.md": b"v1"}, {"title": "PR"},
    )
    changed_spec = build_content_binding(
        "a" * 40, "b" * 40, b"patch",
        {"specs/GH1/product.md": b"v2"}, {"title": "PR"},
    )
    evidence = build_evidence(
        pr_payload(), threads_payload(), content_binding=current, config=PACK
    )
    workflow_check = evidence["checks"][0]

    assert evidence["reused_components"] == []
    assert workflow_check["covered_categories"] == ["code_inputs", "spec_files"]
    assert not content_bindings_match(
        workflow_check, changed_spec["content_hashes"]
    )


def test_ci_component_coverage_comes_only_from_repo_config() -> None:
    current = build_content_binding(
        "a" * 40, "b" * 40, b"patch",
        {"specs/GH1/product.md": b"v1"}, {"title": "PR"},
    )
    payload = pr_payload()
    payload["statusCheckRollup"][0]["name"] = "consumer-check"  # type: ignore[index]
    config = _pack_config(coverage={"consumer-check": ["pr_metadata"]})

    evidence = build_evidence(
        payload, threads_payload(), content_binding=current, config=config
    )

    assert evidence["checks"][0]["covered_categories"] == ["pr_metadata"]
    assert "content_binding_version" not in evidence["checks"][1]
    assert trusted_ci_coverage(_pack_config(coverage={}), "lint") is None


@pytest.mark.parametrize(
    ("coverage", "error"),
    [
        ({"workflow-check": []}, "non-empty list"),
        ({"workflow-check": ["code_inputs", "code_inputs"]}, "duplicates"),
        ({"workflow-check": ["undeclared"]}, "unknown category"),
    ],
)
def test_ci_component_coverage_rejects_invalid_repo_config(
    coverage: dict[str, list[str]], error: str,
) -> None:
    current = build_content_binding(
        "a" * 40, "b" * 40, b"patch", {}, {"title": "PR"}
    )

    with pytest.raises(EvidenceError, match=error):
        build_evidence(
            pr_payload(), threads_payload(), content_binding=current,
            config=_pack_config(coverage=coverage),
        )


def test_collect_content_binding_uses_exact_git_base_and_head(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "SpecRail"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "specrail@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "specs/GH1").mkdir(parents=True)
    (tmp_path / "specs/GH1/product.md").write_text("v1", encoding="utf-8")
    (tmp_path / "code.py").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    (tmp_path / "specs/GH1/product.md").write_text("v2", encoding="utf-8")
    (tmp_path / "code.py").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "head"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    payload = pr_payload()
    payload.update({
        "headRefOid": head, "headRefName": "feature", "baseRefName": "main",
        "title": "Change", "body": "Closes #9",
    })
    binding = _collect_content_binding(
        tmp_path, payload,
        {"head_sha": head, "base_sha": base, "base_ref": "main"},
        {"number": 9, "kind": "closing", "verified": True},
        _pack_config(tmp_path),
    )

    expected_tree = subprocess.run(
        ["git", "rev-parse", f"{base}^{{tree}}"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    assert binding["snapshot"]["base_tree_oid"] == expected_tree
    assert binding["snapshot"]["head_sha"] == head


def test_collect_content_binding_uses_configured_spec_packet_root(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "SpecRail"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "specrail@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    spec_path = tmp_path / "docs/rail/GH9/product.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("v1", encoding="utf-8")
    (tmp_path / "code.py").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    spec_path.write_text("v2", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "head"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    payload = pr_payload()
    payload.update({
        "headRefOid": head, "headRefName": "feature", "baseRefName": "main",
        "title": "Change", "body": "Closes #9",
    })

    binding = _collect_content_binding(
        tmp_path, payload,
        {"head_sha": head, "base_sha": base, "base_ref": "main"},
        {"number": 9, "kind": "closing", "verified": True},
        _pack_config(tmp_path, spec_root="docs/rail"),
    )

    assert binding["content_hashes"]["spec_files"] == hash_spec_files({
        "docs/rail/GH9/product.md": b"v2"
    })


@pytest.mark.parametrize("drift", ["head_sha", "base_sha", "paths_sha256"])
def test_content_binding_collector_rejects_snapshot_drift(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    payload = pr_payload()
    before = file_snapshot(["README.md"])
    after = deepcopy(before)
    after[drift] = "c" * 40 if drift != "paths_sha256" else "c" * 64
    snapshots = [before, after]
    monkeypatch.setattr("github_pr_evidence._checkout_is_exact_head", lambda *_: True)
    monkeypatch.setattr("github_pr_evidence.collect_pr_view", lambda *_: payload)
    monkeypatch.setattr(
        "github_pr_evidence.collect_review_threads", lambda *_: threads_payload()
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_file_snapshot", lambda *_: snapshots.pop(0)
    )

    with pytest.raises(EvidenceError, match="snapshot drifted"):
        collect_evidence(
            "majiayu000/specrail", 10, None, repo=ROOT,
            config=PACK, content_binding_v1=True,
        )


def test_content_binding_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_payload()
    monkeypatch.setattr("github_pr_evidence._checkout_is_exact_head", lambda *_: True)
    monkeypatch.setattr("github_pr_evidence.collect_pr_view", lambda *_: payload)
    monkeypatch.setattr(
        "github_pr_evidence.collect_review_threads", lambda *_: threads_payload()
    )

    evidence = collect_evidence("majiayu000/specrail", 10, None, repo=ROOT)

    assert "content_binding_version" not in evidence
    assert "reused_components" not in evidence


def test_content_binding_v1_requires_repo_owned_workflow_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "github_pr_evidence.collect_pr_view", lambda *_: pr_payload()
    )

    with pytest.raises(EvidenceError, match="repo-owned workflow configuration"):
        collect_evidence(
            "majiayu000/specrail", 10, None, repo=ROOT,
            content_binding_v1=True,
        )


def test_collector_binding_only_cli_emits_schema_sidecar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    binding = build_content_binding(
        "a" * 40, "b" * 40, b"patch",
        {"specs/GH9/product.md": b"spec"}, {"title": "PR"},
    )
    monkeypatch.setattr("github_pr_evidence.collect_evidence", lambda *args, **kwargs: binding)
    monkeypatch.setattr(
        "sys.argv",
        [
            "github_pr_evidence.py", "--github-repo", "owner/repo",
            "--repo", str(ROOT), "--pr", "489", "--content-binding-only", "--json",
        ],
    )

    assert github_evidence_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == 1
    assert payload["artifact_id"] == "content-binding-pr-489-aaaaaaaaaaaa"
    assert payload["snapshot"]["collector"] == "github_pr_evidence"


def test_build_evidence_reuses_previous_head_ci_with_complete_audit() -> None:
    previous = build_content_binding(
        "b" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"same"}, {"title": "same"},
    )
    current = build_content_binding(
        "d" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"same"}, {"title": "same"},
    )
    previous_payload = pr_payload()
    previous_payload["headRefOid"] = "b" * 40
    prior_evidence = build_evidence(
        previous_payload, threads_payload(), content_binding=previous, config=PACK
    )
    current_payload = pr_payload()
    current_payload["headRefOid"] = "d" * 40
    current_payload["statusCheckRollup"][0].update(  # type: ignore[index]
        {"status": "IN_PROGRESS", "conclusion": ""}
    )

    evidence = build_evidence(
        current_payload,
        threads_payload(),
        content_binding=current,
        reusable_ci_evidence=prior_evidence,
        config=PACK,
    )

    reused = evidence["checks"][0]
    assert reused["head_sha"] == "b" * 40
    assert evidence["reused_components"] == [{
        "artifact_id": reused["artifact_id"],
        "original_head_sha": "b" * 40,
        "covered_categories": ["code_inputs", "spec_files"],
        "original_content_bindings": reused["content_bindings"],
        "current_content_bindings": reused["content_bindings"],
        "collector_provenance": current["snapshot"],
        "reason": "covered content categories match the current trusted snapshot",
    }]


def test_build_evidence_does_not_replace_completed_current_failure() -> None:
    previous = build_content_binding(
        "b" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"same"}, {"title": "same"},
    )
    current = build_content_binding(
        "d" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"same"}, {"title": "same"},
    )
    previous_payload = pr_payload()
    previous_payload["headRefOid"] = "b" * 40
    prior_evidence = build_evidence(
        previous_payload, threads_payload(), content_binding=previous, config=PACK
    )
    current_payload = pr_payload()
    current_payload["headRefOid"] = "d" * 40
    current_payload["statusCheckRollup"][0].update(  # type: ignore[index]
        {"status": "COMPLETED", "conclusion": "FAILURE"}
    )

    evidence = build_evidence(
        current_payload, threads_payload(), content_binding=current,
        reusable_ci_evidence=prior_evidence, config=PACK,
    )

    workflow_check = evidence["checks"][0]
    assert workflow_check["conclusion"] == "FAILURE"
    assert workflow_check["head_sha"] == "d" * 40
    assert evidence["reused_components"] == []


def test_build_evidence_rejects_same_head_component_from_stale_wrapper() -> None:
    current = build_content_binding(
        "d" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"same"}, {"title": "same"},
    )
    current_payload = pr_payload()
    current_payload["headRefOid"] = "d" * 40
    prior_evidence = build_evidence(
        current_payload, threads_payload(), content_binding=current, config=PACK
    )
    prior_evidence["head_sha"] = "b" * 40
    current_payload["statusCheckRollup"][0].update(  # type: ignore[index]
        {"status": "IN_PROGRESS", "conclusion": ""}
    )

    with pytest.raises(EvidenceError, match="snapshot must come from a previous head"):
        build_evidence(
            current_payload,
            threads_payload(),
            content_binding=current,
            reusable_ci_evidence=prior_evidence,
            config=PACK,
        )


def test_build_evidence_rejects_previous_ci_when_spec_binding_changed() -> None:
    previous = build_content_binding(
        "b" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"before"}, {"title": "same"},
    )
    current = build_content_binding(
        "d" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"after"}, {"title": "same"},
    )
    previous_payload = pr_payload()
    previous_payload["headRefOid"] = "b" * 40
    prior_evidence = build_evidence(
        previous_payload, threads_payload(), content_binding=previous, config=PACK
    )
    current_payload = pr_payload()
    current_payload["headRefOid"] = "d" * 40
    current_payload["statusCheckRollup"][0].update(  # type: ignore[index]
        {"status": "IN_PROGRESS", "conclusion": ""}
    )

    with pytest.raises(EvidenceError, match="bindings do not match"):
        build_evidence(
            current_payload,
            threads_payload(),
            content_binding=current,
            reusable_ci_evidence=prior_evidence,
            config=PACK,
        )


def test_versioned_pr_evidence_loader_requires_repo_local_schema_backed_input(
    tmp_path: Path,
) -> None:
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas/pr_review_gate.schema.json").write_text(
        (ROOT / "schemas/pr_review_gate.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    evidence = json.loads(
        (ROOT / "examples/fixtures/pr-clean-authorized.json").read_text(
            encoding="utf-8"
        )
    )
    binding = build_content_binding(
        evidence["head_sha"], "c" * 40, b"patch", {}, {"title": "prior"}
    )
    evidence.update(binding)
    evidence["reused_components"] = []
    (tmp_path / "prior.json").write_text(json.dumps(evidence), encoding="utf-8")

    loaded = load_versioned_pr_evidence(tmp_path, "prior.json")

    assert loaded["snapshot"] == binding["snapshot"]

    evidence["head_sha"] = "b" * 40
    (tmp_path / "prior.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(EvidenceError, match="head_sha must match"):
        load_versioned_pr_evidence(tmp_path, "prior.json")


def test_build_evidence_audits_previous_head_review_component() -> None:
    current = build_content_binding(
        "d" * 40, "c" * 40, b"patch",
        {"specs/GH9/product.md": b"same"}, {"title": "same"},
    )
    review_evidence = clean_review_evidence()
    artifact = review_evidence["artifacts"][0]
    artifact["head_sha"] = "b" * 40
    artifact.update(build_component_binding(
        ["code_inputs", "spec_files"], current["content_hashes"]
    ))
    review_evidence["head_sha"] = "d" * 40
    payload = pr_payload()
    payload["headRefOid"] = "d" * 40

    evidence = build_evidence(
        payload,
        threads_payload(),
        review_source="independent_lane",
        review_evidence=review_evidence,
        content_binding=current,
    )

    assert evidence["reused_components"][0]["artifact_id"] == artifact["artifact_id"]
    assert evidence["reused_components"][0]["original_head_sha"] == "b" * 40


def _partial_pr_payload() -> dict[str, object]:
    payload = pr_payload()
    payload["body"] = "Closes #806\nRefs #671"
    payload["closingIssuesReferences"] = [{"number": 806}]
    return payload


def test_partial_issue_relation_is_requeried_after_final_pr_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _partial_pr_payload()
    live_issue = {
        "number": 671,
        "state": "OPEN",
        "url": "https://github.com/majiayu000/specrail/issues/671",
    }
    issue_queries: list[tuple[str, int]] = []

    monkeypatch.setattr("github_pr_evidence.collect_pr_view", lambda *_: payload)
    monkeypatch.setattr(
        "github_pr_evidence.collect_review_threads", lambda *_: threads_payload()
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_issue_view",
        lambda repo, issue: issue_queries.append((repo, issue)) or dict(live_issue),
    )

    evidence = collect_evidence(
        "majiayu000/specrail", 10, None, expected_issue=671
    )

    assert issue_queries == [
        ("majiayu000/specrail", 671),
        ("majiayu000/specrail", 671),
    ]
    assert evidence["issue_reference"]["url"] == live_issue["url"]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"state": "CLOSED"}, "must be OPEN"),
        ({"number": 672}, "does not match expected issue"),
        ({"url": "https://example.invalid/issues/671"}, "partial issue relation changed"),
    ],
)
def test_partial_issue_relation_drift_after_final_pr_snapshot_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, object],
    error: str,
) -> None:
    payload = _partial_pr_payload()
    issue_before = {
        "number": 671,
        "state": "OPEN",
        "url": "https://github.com/majiayu000/specrail/issues/671",
    }
    issue_after = {**issue_before, **mutation}
    issue_payloads = [issue_before, issue_after]

    monkeypatch.setattr("github_pr_evidence.collect_pr_view", lambda *_: payload)
    monkeypatch.setattr(
        "github_pr_evidence.collect_review_threads", lambda *_: threads_payload()
    )
    monkeypatch.setattr(
        "github_pr_evidence.collect_issue_view", lambda *_: issue_payloads.pop(0)
    )

    with pytest.raises(EvidenceError, match=error):
        collect_evidence("majiayu000/specrail", 10, None, expected_issue=671)

    assert issue_payloads == []
