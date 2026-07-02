from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))

from check_workflow import REQUIRED_FILES, validate_required_file_globs  # noqa: E402


def test_required_files_do_not_enumerate_fixtures_or_schemas() -> None:
    assert not any(path.startswith("examples/fixtures/") for path in REQUIRED_FILES)
    assert not any(path.startswith("schemas/") for path in REQUIRED_FILES)


def test_required_file_globs_discover_existing_fixture_and_schema_files() -> None:
    assert validate_required_file_globs(ROOT) == []


def test_required_file_globs_require_at_least_one_match(tmp_path: Path) -> None:
    errors = validate_required_file_globs(tmp_path)

    assert "missing required files matching: examples/fixtures/*" in errors
    assert "missing required files matching: schemas/*.schema.json" in errors
