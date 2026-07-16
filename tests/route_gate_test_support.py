from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checks"))

from sensitive_enforcement import build_approved_spec_evidence  # noqa: E402
from specrail_lib import load_pack  # noqa: E402


def run_route_gate(
    *args: str,
    repo: Path = ROOT,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = subprocess.run(
        [
            sys.executable,
            "checks/route_gate.py",
            "--repo",
            str(repo),
            *args,
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return result, payload


def write_custom_pack(repo: Path, spec_root: str = "docs/specs") -> None:
    repo.mkdir()
    workflow = (ROOT / "workflow.yaml").read_text(encoding="utf-8").replace(
        "specs/GH{issue_number}",
        f"{spec_root}/GH{{issue_number}}",
    )
    (repo / "workflow.yaml").write_text(workflow, encoding="utf-8")
    for name in ["states.yaml", "labels.yaml"]:
        (repo / name).write_text(
            (ROOT / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def write_sensitive_pack(
    repo: Path,
    planned_paths: list[str] | None = None,
    manifest_count: int = 1,
    render_manifest: bool = True,
) -> str:
    write_custom_pack(repo, "specs")
    workflow_path = repo / "workflow.yaml"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(
            "    paths: []", "    paths:\n      - checks/**"
        ),
        encoding="utf-8",
    )
    schema_dir = repo / "schemas"
    schema_dir.mkdir()
    (schema_dir / "duplicate_work_evidence.schema.json").write_text(
        (ROOT / "schemas" / "duplicate_work_evidence.schema.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid", "commit", "-qm", "pack",
        ],
        check=True,
    )
    packet = repo / "specs" / "GH999"
    packet.mkdir(parents=True)
    (packet / "product.md").write_text("GitHub issue: `#999`\n", encoding="utf-8")
    manifest = {
        "version": 1,
        "issue": 999,
        "complete": True,
        "paths": planned_paths if planned_paths is not None else ["checks/route_gate.py"],
        "spec_refs": [],
    }
    template = (ROOT / "templates" / "tech_spec.md").read_text(encoding="utf-8")
    template_manifest = (
        '<!-- specrail-planned-changes\n'
        '{"version":1,"issue":0,"complete":false,"paths":[],"spec_refs":[]}\n'
        '-->'
    )
    manifest_text = (
        "<!-- specrail-planned-changes\n"
        + json.dumps(manifest, separators=(",", ":"))
        + "\n-->"
    )
    assert template.count(template_manifest) == 1
    replacement = manifest_text if render_manifest and manifest_count else ""
    if not render_manifest:
        replacement = template_manifest
    rendered_tech = template.replace(template_manifest, replacement)
    (packet / "tech.md").write_text(
        "GitHub issue: `#999`\n" + rendered_tech
        + ("\n" + manifest_text) * (manifest_count - 1),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=SpecRail Test",
            "-c", "user.email=specrail@example.invalid", "commit", "-qm", "spec",
        ],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", head],
        check=True,
    )
    subprocess.run(
        [
            "git", "-C", str(repo), "symbolic-ref",
            "refs/remotes/origin/HEAD", "refs/remotes/origin/main",
        ],
        check=True,
    )
    return head


def sensitive_route_evidence(repo: Path, head: str) -> dict[str, object]:
    revisions = {
        f"specs/GH999/{name}.md": {
            "source_commit_sha": head,
            "pr_number": 10,
            "merged_at": "2029-01-01T00:00:00Z",
            "merge_commit_sha": head,
        }
        for name in ["product", "tech"]
    }
    approval = build_approved_spec_evidence(
        load_pack(repo),
        repo,
        repository="example/consumer",
        issue=999,
        spec_revisions=revisions,
        approved_at="2030-07-14T00:00:00Z",
        maintainer_actor="maintainer",
        default_base_ref="main",
        default_base_sha=head,
    )
    return {
        "github_state": "OPEN",
        "state": "ready_to_implement",
        "state_source": "label",
        "state_trusted": True,
        "repository": "example/consumer",
        "base_ref": "main",
        "base_sha": head,
        "default_base_ref": "main",
        "default_base_sha": head,
        "enforcement_sensitive": True,
        "sensitive_classification": {
            "source": "tech_spec",
            "changed_paths": ["checks/route_gate.py"],
            "spec_refs": [],
        },
        "approved_spec": approval,
    }


def write_duplicate_evidence(
    tmp_path: Path,
    *,
    issue: int = 999,
    open_prs: list[dict[str, object]] | None = None,
    remote_branches: list[str] | None = None,
) -> Path:
    path = tmp_path / "duplicate-evidence.json"
    path.write_text(
        json.dumps(
            {
                "issue": issue,
                "collected_at": "2026-07-04T00:00:00Z",
                "open_prs_complete": True,
                "open_pr_limit": 100,
                "open_prs": [] if open_prs is None else open_prs,
                "remote_branches": [] if remote_branches is None else remote_branches,
            }
        ),
        encoding="utf-8",
    )
    return path
