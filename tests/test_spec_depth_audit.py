from pathlib import Path
import subprocess
import sys

from tools.spec_depth_audit import (
    EARS_RE,
    METRIC_SEMANTICS_VERSION,
    anchor_count,
    boundary_cov,
    spec_labels,
)


def test_metric_semantics_version_is_explicit() -> None:
    assert METRIC_SEMANTICS_VERSION == 3


def test_anchor_count_includes_extensionless_files_without_counting_ids() -> None:
    tech = """\
`checks/gate.py:9`
`Dockerfile:12`
`Makefile:5`
`CODEOWNERS:3`
`config/hooks/pre-commit:7`
B-001:4
GH-93:2
status:200
http://localhost:8080
`123:4`
"""

    assert anchor_count(tech) == 5


def test_ears_ratio_requires_a_conditional_trigger() -> None:
    assert EARS_RE.search("WHEN evidence is missing, the tool SHALL fail closed")
    assert EARS_RE.search("当证据缺失时，工具须明确失败")
    assert EARS_RE.search("The tool SHALL fail closed") is None
    assert EARS_RE.search("工具应明确失败") is None


def test_boundary_coverage_uses_current_checklist_verdicts() -> None:
    product = """\
## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-001 |
| Error / failure paths |  |
| Authorization / permission | N/A: local-only tool |
| Concurrency / race |  |
| Retry / idempotency | covered: B-002 |
| Illegal state transitions |  |
| Compatibility / migration |  |
| Degradation / fallback | covered: B-003 |
| Evidence / audit integrity |  |
| Cancellation / interruption |  |
"""

    assert boundary_cov(product) == {
        "empty",
        "permission",
        "retry_idempotency",
        "degradation",
    }


def test_duplicate_explicit_spec_names_use_resolved_paths(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline" / "GH58"
    experiment = tmp_path / "experiment" / "GH58"

    assert spec_labels([baseline, experiment], explicit=True) == [
        str(baseline.resolve()),
        str(experiment.resolve()),
    ]
    assert spec_labels([baseline], explicit=True) == ["GH58"]


def test_mixed_valid_and_invalid_explicit_dirs_fail_closed(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    invalid = tmp_path / "invalid"
    valid.mkdir()
    invalid.mkdir()
    (valid / "product.md").write_text("# Product Spec\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "tools/spec_depth_audit.py",
            "--spec-dir",
            str(valid),
            "--spec-dir",
            str(invalid),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert f"spec dirs missing product.md: {invalid}" in result.stderr


BOUNDARY_LABELS = [
    "Empty / missing input",
    "Error / failure paths",
    "Authorization / permission",
    "Concurrency / race",
    "Retry / idempotency",
    "Illegal state transitions",
    "Compatibility / migration",
    "Degradation / fallback",
    "Evidence / audit integrity",
    "Cancellation / interruption",
]


def _write_spec(
    spec_dir: Path,
    *,
    invariants: int = 8,
    boundary_rows: int = 8,
    anchors: int = 5,
    trivial: bool = False,
    tech: bool = True,
    conditional: bool = True,
    trivial_outside_linked_issue: bool = False,
) -> None:
    spec_dir.mkdir(parents=True)
    linked = "GH-999\n"
    if trivial:
        linked += "\ncomplexity: trivial\n"
    if conditional:
        inv_lines = [
            f"{i}. B-{i:03d} WHEN the audited set is scanned, the tool reports row {i}."
            for i in range(1, invariants + 1)
        ]
    else:
        inv_lines = [
            f"{i}. B-{i:03d} the tool reports row {i} without a trigger clause."
            for i in range(1, invariants + 1)
        ]
    rows = [
        f"| {label} | covered: B-001 |" if idx < boundary_rows else f"| {label} |  |"
        for idx, label in enumerate(BOUNDARY_LABELS)
    ]
    extra = "\n## Non-Goals\n\ncomplexity: trivial\n" if trivial_outside_linked_issue else ""
    product = (
        "# Product Spec\n\n"
        f"## Linked Issue\n\n{linked}\n"
        f"{extra}"
        "## Behavior Invariants\n\n" + "\n".join(inv_lines) + "\n\n"
        "## Boundary Checklist\n\n"
        "| Category | Verdict |\n| --- | --- |\n" + "\n".join(rows) + "\n"
    )
    (spec_dir / "product.md").write_text(product, encoding="utf-8")
    if tech:
        anchor_lines = [f"`checks/gate.py:{9 + i}`" for i in range(anchors)]
        (spec_dir / "tech.md").write_text(
            "# Tech Spec\n\n" + "\n".join(anchor_lines) + "\n", encoding="utf-8"
        )


def _run_audit(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/spec_depth_audit.py", *argv],
        check=False,
        capture_output=True,
        text=True,
    )


def test_gate_blocks_shallow_spec_with_reasons(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH900", invariants=5, boundary_rows=0, anchors=0)

    result = _run_audit("--spec-dir", str(tmp_path / "GH900"), "--gate")

    assert result.returncode == 1
    assert "FAIL GH900" in result.stdout
    assert "invariants=5 < 8" in result.stdout
    assert "boundary_categories=0 < 8" in result.stdout
    assert "anchors=0 < 5" in result.stdout


def test_gate_passes_deep_spec(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH901", invariants=8, boundary_rows=8, anchors=5)

    result = _run_audit("--spec-dir", str(tmp_path / "GH901"), "--gate")

    assert result.returncode == 0
    assert "gate: PASS" in result.stdout


def test_gate_exempts_trivial_spec(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH902", invariants=3, boundary_rows=0, anchors=0, trivial=True)

    result = _run_audit("--spec-dir", str(tmp_path / "GH902"), "--gate")

    assert result.returncode == 0
    assert "exempt (complexity: trivial): GH902" in result.stdout


def test_trivial_marker_outside_linked_issue_is_not_exempt(tmp_path: Path) -> None:
    _write_spec(
        tmp_path / "GH903",
        invariants=3,
        boundary_rows=0,
        anchors=0,
        trivial_outside_linked_issue=True,
    )

    result = _run_audit("--spec-dir", str(tmp_path / "GH903"), "--gate")

    assert result.returncode == 1
    assert "FAIL GH903" in result.stdout


def test_gate_thresholds_are_configurable(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH904", invariants=2, boundary_rows=1, anchors=0)

    result = _run_audit(
        "--spec-dir", str(tmp_path / "GH904"), "--gate",
        "--min-invariants", "1", "--min-boundary", "0", "--min-anchors", "0",
    )

    assert result.returncode == 0
    assert "gate: PASS" in result.stdout


def test_gate_ignores_ears_ratio(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH905", invariants=8, boundary_rows=8, anchors=5, conditional=False)

    result = _run_audit("--spec-dir", str(tmp_path / "GH905"), "--gate")

    assert result.returncode == 0
    assert "EARS 占比:        均值=0%" in result.stdout


def test_gate_counts_missing_tech_as_zero_anchors(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH906", invariants=8, boundary_rows=8, tech=False)

    result = _run_audit("--spec-dir", str(tmp_path / "GH906"), "--gate")

    assert result.returncode == 1
    assert "anchors=0 < 5" in result.stdout


def test_gate_is_read_only(tmp_path: Path) -> None:
    spec_dir = tmp_path / "GH907"
    _write_spec(spec_dir, invariants=5, boundary_rows=0, anchors=0)
    before = {p: p.read_bytes() for p in sorted(spec_dir.rglob("*")) if p.is_file()}

    _run_audit("--spec-dir", str(spec_dir), "--gate")

    after = {p: p.read_bytes() for p in sorted(spec_dir.rglob("*")) if p.is_file()}
    assert before == after


def test_audit_without_gate_keeps_current_behavior(tmp_path: Path) -> None:
    _write_spec(tmp_path / "GH908", invariants=2, boundary_rows=0, anchors=0)

    result = _run_audit("--spec-dir", str(tmp_path / "GH908"))

    assert result.returncode == 0
    assert "gate" not in result.stdout
