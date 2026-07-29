from __future__ import annotations

import importlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
installer = importlib.import_module("tools.install_codex_skills")


def test_failed_profile_copy_keeps_legacy_installation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    legacy = target / "specrail-workflow"
    legacy.mkdir(parents=True)

    def fail_copy(_source: Path, _destination: Path) -> None:
        raise OSError("copy failed")

    monkeypatch.setattr(installer.shutil, "copytree", fail_copy)

    with pytest.raises(installer.InstallError, match="copy failed"):
        installer.install_skills(ROOT, target, True, "core")

    assert legacy.is_dir()
    assert not (target / "specrail").exists()
