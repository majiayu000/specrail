from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from github_approved_spec_evidence import collect_spec_revision_approval
from github_evidence_common import EvidenceError
from pr_gate import evaluate_pr_gate
from pr_gate_test_support import sensitive_evidence
from runtime_ledger_gate import evaluate_checkpoint
from runtime_ledger_test_support import clean_checkpoint
from sensitive_enforcement import classify_sensitive_changes
from specrail_lib import PackConfig, validate_instance


def _schema(name: str) -> dict[str, object]:
    return json.loads(
        (ROOT / "schemas" / name).read_text(encoding="utf-8")
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=SpecRail Test",
        "-c",
        "user.email=specrail@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _live_runner(
    artifact: bytes,
    *,
    lifecycle: str = "spec_approved",
    review_commit: str,
    head_sha: str | None = None,
):
    def run(args: list[str]) -> object:
        endpoint = args[-1]
        if endpoint.startswith("query="):
            issue: dict[str, object] = {"state": "OPEN"}
            pull: dict[str, object] = {"headRefOid": head_sha or review_commit}
            page = {"hasNextPage": False, "endCursor": None}
            if "SpecRevisionLabels" in endpoint:
                issue["labels"] = {
                    "pageInfo": page,
                    "nodes": [{"id": "label-1", "name": lifecycle}],
                }
            elif "SpecRevisionTimeline" in endpoint:
                issue["timelineItems"] = {
                    "pageInfo": page,
                    "nodes": [{
                        "id": "event-1",
                        "createdAt": "2026-07-23T01:00:00Z",
                        "actor": {"login": "maintainer"},
                        "label": {"name": lifecycle},
                    }],
                }
            else:
                pull["reviews"] = {
                    "pageInfo": page,
                    "nodes": [{
                        "id": "review-1",
                        "state": "APPROVED",
                        "submittedAt": "2026-07-23T02:00:00Z",
                        "url": (
                            "https://github.com/majiayu000/specrail/"
                            "pull/718#pullrequestreview-1"
                        ),
                        "author": {"login": "maintainer"},
                        "commit": {"oid": review_commit},
                    }],
                }
            return {"data": {"repository": {"issue": issue, "pullRequest": pull}}}
        if "/collaborators/" in endpoint:
            return {"permission": "maintain"}
        if "/contents/" in endpoint:
            return {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(artifact).decode("ascii"),
            }
        raise AssertionError(args)

    return run


def _bind_review(evidence: dict[str, object], repo: Path, head: str) -> None:
    review = evidence["review_evidence"]
    assert isinstance(review, dict)
    review["head_sha"] = head
    artifacts = review["artifacts"]
    assert isinstance(artifacts, list) and len(artifacts) == 1
    artifact = artifacts[0]
    assert isinstance(artifact, dict)
    artifact["head_sha"] = head
    manifest_path = repo / str(review["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["head_sha"] = head
    artifact_path = repo / manifest["lanes"][0]["artifact_paths"][0]
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    review["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _live_route_case(
    tmp_path: Path,
    *,
    collector_artifact: bytes | None = None,
) -> tuple[dict[str, object], Path, object]:
    evidence, repo, config = sensitive_evidence(tmp_path)
    workflow = deepcopy(config.workflow)
    workflow["enforcement"]["sensitive_registry"]["specs"] = ["specs/GH*/**"]
    config = PackConfig(repo, workflow, config.states, config.labels)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    path = "specs/GH97/product.md"
    revised = b"# live revised product\n"
    (repo / path).write_bytes(revised)
    head = _commit(repo, "revise product spec")
    paths = [path]
    classification = classify_sensitive_changes(
        config, repo, paths, paths, source="github_changed_files"
    )
    approval = collect_spec_revision_approval(
        "majiayu000/specrail",
        97,
        718,
        head,
        tuple(paths),
        _live_runner(
            revised if collector_artifact is None else collector_artifact,
            review_commit=head,
        ),
    )
    evidence.update({
        "base_sha": base,
        "default_base_sha": base,
        "head_sha": head,
        "gate_query_head_sha": head,
        "linked_issue": 97,
        "changed_files_count": 1,
        "changed_files_sha256": hashlib.sha256(
            json.dumps(paths, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "sensitive_classification": classification,
        "sensitive_route": "spec_revision",
        "spec_approval": approval,
    })
    evidence.pop("approved_spec")
    _bind_review(evidence, repo, head)
    return evidence, repo, config


def _runtime_checkpoint(
    repo: Path,
    evidence: dict[str, object],
) -> dict[str, object]:
    artifact_dir = repo / "artifacts" / "runtime"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = artifact_dir / "spec-approval.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    checkpoint = clean_checkpoint()
    checkpoint["repo"] = evidence["repository"]
    item = checkpoint["items"][0]
    assert isinstance(item, dict)
    item.update({
        "issue": evidence["linked_issue"],
        "state": "running",
        "head_sha": evidence["head_sha"],
        "enforcement_sensitive": True,
        "sensitive_route": "spec_revision",
        "spec_approval_evidence": evidence_path.relative_to(repo).as_posix(),
    })
    return checkpoint


def test_live_collector_schema_pr_gate_and_runtime_route_end_to_end(
    tmp_path: Path,
) -> None:
    evidence, repo, config = _live_route_case(tmp_path)

    validate_instance(_schema("pr_review_gate.schema.json"), evidence)
    gate = evaluate_pr_gate(evidence, repo=repo, config=config)
    assert gate["decision"] == "allowed"
    assert gate["sensitive_route_audit"]["commit_oid"] == evidence["head_sha"]

    checkpoint = _runtime_checkpoint(repo, evidence)
    validate_instance(_schema("runtime_checkpoint.schema.json"), checkpoint)
    runtime = evaluate_checkpoint(checkpoint, repo=repo, config=config)
    assert runtime["decision"] == "allowed"


@pytest.mark.parametrize(
    ("lifecycle", "review_commit", "message"),
    [
        ("spec_review", "a" * 40, "spec_approved"),
        ("spec_approved", "b" * 40, "exact-head APPROVED"),
    ],
)
def test_live_collector_rejects_unapproved_lifecycle_or_stale_review(
    lifecycle: str,
    review_commit: str,
    message: str,
) -> None:
    with pytest.raises(EvidenceError, match=message):
        collect_spec_revision_approval(
            "majiayu000/specrail",
            97,
            718,
            "a" * 40,
            ("specs/GH97/product.md",),
            _live_runner(
                b"# revised\n",
                lifecycle=lifecycle,
                review_commit=review_commit,
                head_sha="a" * 40,
            ),
        )


def test_live_collector_artifact_bytes_are_revalidated_by_pr_gate(
    tmp_path: Path,
) -> None:
    evidence, repo, config = _live_route_case(
        tmp_path, collector_artifact=b"# forged remote bytes\n"
    )

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert any("gated-head artifacts" in reason for reason in result["reasons"])


@pytest.mark.parametrize("mutation", ["linked_issue", "mixed_path"])
def test_live_route_rejects_wrong_issue_or_mixed_snapshot(
    tmp_path: Path,
    mutation: str,
) -> None:
    evidence, repo, config = _live_route_case(tmp_path)
    if mutation == "linked_issue":
        evidence["linked_issue"] = 98
    else:
        paths = ["specs/GH97/product.md", "README.md"]
        evidence["changed_files_count"] = len(paths)
        evidence["changed_files_sha256"] = hashlib.sha256(
            json.dumps(paths, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        evidence["sensitive_classification"] = classify_sensitive_changes(
            config, repo, paths, [paths[0]], source="github_changed_files"
        )

    result = evaluate_pr_gate(evidence, repo=repo, config=config)

    assert result["decision"] == "blocked"
    assert result["sensitive_route_audit"] is None
