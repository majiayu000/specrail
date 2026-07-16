from __future__ import annotations

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
from sensitive_enforcement import build_approved_spec_evidence  # noqa: E402
from specrail_lib import load_pack  # noqa: E402


def clean_evidence() -> dict[str, object]:
    return fixture("pr-clean-authorized.json")


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
