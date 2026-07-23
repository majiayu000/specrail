from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from shutil import copyfile


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
FIXTURES = ROOT / "examples" / "fixtures"
sys.path.insert(0, str(CHECKS))

from pr_gate import evaluate_pr_gate  # noqa: E402
from evidence_content_binding import build_content_binding_evidence  # noqa: E402
from review_result_semantics import load_review_manifest  # noqa: E402
from sensitive_enforcement import build_approved_spec_evidence  # noqa: E402
from specrail_lib import load_pack  # noqa: E402


def clean_evidence() -> dict[str, object]:
    return fixture("pr-clean-authorized.json")


def write_review_evidence(
    repo: Path, evidence: dict[str, object], artifacts: list[dict[str, object]],
) -> None:
    schema_dir = repo / "schemas"
    schema_dir.mkdir(exist_ok=True)
    for name in ["review_result.schema.json", "content_binding_evidence.schema.json"]:
        copyfile(ROOT / "schemas" / name, schema_dir / name)
    review_dir = repo / "artifacts/reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, artifact in enumerate(artifacts, start=1):
        path = review_dir / f"review-{index}.json"
        stored = {
            key: value for key, value in artifact.items() if key != "artifact_path"
        }
        path.write_text(json.dumps(stored), encoding="utf-8")
        paths.append(path.relative_to(repo).as_posix())
    manifest = {
        "version": 1,
        "pr": evidence["pr"],
        "head_sha": evidence["head_sha"],
        "human_final_review_required": False,
        "lanes": [{
            "lane_id": artifacts[0]["reviewer_lane"],
            "producer_identity": artifacts[0]["producer_identity"],
            "artifact_paths": paths,
        }],
    }
    manifest_path = review_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence["review_evidence"] = load_review_manifest(
        repo,
        manifest_path.relative_to(repo).as_posix(),
        expected_pr=evidence["pr"],
        expected_head_sha=evidence["head_sha"],
        current_binding={
            key: evidence[key]
            for key in ["content_binding_version", "snapshot", "content_hashes"]
        },
    )


def v1_reuse_evidence(
    repo: Path, evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    evidence = clean_evidence() if evidence is None else evidence
    current_head = evidence["head_sha"]
    prior_head = "b" * 40
    hashes = {
        "code_inputs": "1" * 64,
        "spec_files": "2" * 64,
        "pr_metadata": "3" * 64,
    }
    snapshot = {
        "head_sha": current_head,
        "base_tree_oid": "d" * 40,
        "algorithm": "sha256",
        "normalization": "specrail-v1",
        "collector": "github_pr_evidence",
    }
    evidence.update({
        "content_binding_version": 1,
        "snapshot": snapshot,
        "content_hashes": hashes,
    })
    check = evidence["checks"][0]
    check.update({
        "name": "workflow-check",
        "artifact_id": "ci-current",
        "head_sha": current_head,
        "content_binding_version": 1,
        "covered_categories": ["code_inputs", "spec_files"],
        "content_bindings": {
            key: hashes[key] for key in ["code_inputs", "spec_files"]
        },
    })
    artifact = evidence["review_evidence"]["artifacts"][0]
    artifact.update({
        "head_sha": prior_head,
        "content_binding_version": 1,
        "covered_categories": ["code_inputs", "spec_files"],
        "content_bindings": {
            key: hashes[key] for key in ["code_inputs", "spec_files"]
        },
    })
    sidecar = build_content_binding_evidence(evidence["pr"], {
        "content_binding_version": 1,
        "snapshot": {**snapshot, "head_sha": prior_head},
        "content_hashes": dict(hashes),
    })
    sidecar_path = repo / "artifacts/content-bindings/prior-review.json"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(sidecar, sort_keys=True).encode("utf-8")
    sidecar_path.write_bytes(raw)
    artifact["content_binding_evidence"] = {
        "artifact_id": sidecar["artifact_id"],
        "path": sidecar_path.relative_to(repo).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    evidence["reused_components"] = [{
        "artifact_id": artifact["artifact_id"],
        "original_head_sha": prior_head,
        "covered_categories": ["code_inputs", "spec_files"],
        "original_content_bindings": dict(artifact["content_bindings"]),
        "current_content_bindings": {
            key: hashes[key] for key in ["code_inputs", "spec_files"]
        },
        "collector_provenance": snapshot,
        "reason": "all covered categories match the current snapshot",
    }]
    write_review_evidence(repo, evidence, [artifact])
    return evidence


def sensitive_evidence(tmp_path: Path) -> tuple[dict[str, object], Path, object]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ["workflow.yaml", "states.yaml", "labels.yaml"]:
        copyfile(ROOT / name, repo / name)
    schema_dir = repo / "schemas"
    schema_dir.mkdir()
    copyfile(
        ROOT / "schemas" / "review_result.schema.json",
        schema_dir / "review_result.schema.json",
    )
    packet = repo / "specs" / "GH97"
    packet.mkdir(parents=True)
    for name in ["product.md", "tech.md"]:
        (packet / name).write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    commit = [
        "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
        "-c", "user.email=specrail@example.invalid", "commit", "-qm",
    ]
    subprocess.run([*commit, "approved specs"], check=True)
    base_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", base_head],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        check=True,
    )
    (repo / "README.md").write_text("implementation\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run([*commit, "implementation"], check=True)
    checkout_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    config = load_pack(repo)
    evidence = clean_evidence()
    issue = 97
    evidence["linked_issue"] = issue
    evidence["head_sha"] = checkout_head
    evidence["gate_query_head_sha"] = checkout_head
    evidence["review_evidence"]["head_sha"] = checkout_head
    evidence["review_evidence"]["artifacts"][0]["head_sha"] = checkout_head
    review_dir = repo / "artifacts" / "reviews"
    review_dir.mkdir(parents=True)
    artifact_path = review_dir / "pr718.json"
    artifact_path.write_text(json.dumps(evidence["review_evidence"]["artifacts"][0]), encoding="utf-8")
    manifest = {"version": 1, "pr": 718, "head_sha": checkout_head, "human_final_review_required": False, "lanes": [{"lane_id": "merge-reviewer-2", "producer_identity": "reviewer-1", "artifact_paths": [artifact_path.relative_to(repo).as_posix()]}]}
    manifest_path = review_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence["review_evidence"]["manifest_path"] = manifest_path.relative_to(repo).as_posix()
    evidence["review_evidence"]["manifest_sha256"] = __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest()
    evidence.update(
        {
            "repository": "majiayu000/specrail",
            "base_ref": "main",
            "base_sha": base_head,
            "default_base_ref": "main",
            "default_base_sha": base_head,
            "changed_files_count": 0,
            "changed_files_sha256": __import__("hashlib").sha256(b"[]").hexdigest(),
            "enforcement_sensitive": True,
            "sensitive_route": "approved_spec",
            "sensitive_classification": {
                "source": "github_changed_files",
                "changed_paths": [],
                "spec_refs": [],
            },
            "approved_spec": build_approved_spec_evidence(
                config, repo,
                repository="majiayu000/specrail", issue=issue,
                spec_revisions={
                    f"specs/GH97/{name}.md": {
                        "source_commit_sha": base_head,
                        "pr_number": 1,
                        "merged_at": "2029-01-01T00:00:00Z",
                        "merge_commit_sha": base_head,
                    }
                    for name in ["product", "tech"]
                },
                approved_at="2030-07-14T00:00:00Z",
                maintainer_actor="maintainer",
                gated_head_sha=checkout_head,
                default_base_ref="main",
                default_base_sha=base_head,
            ),
        }
    )
    return evidence, repo, config


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
