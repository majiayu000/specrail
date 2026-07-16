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
