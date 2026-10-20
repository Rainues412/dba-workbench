from __future__ import annotations

from pathlib import Path

import desktop


def test_packaged_data_directory_defaults_to_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DBA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert desktop._data_directory() == tmp_path / "DBA Workbench" / "data"


def test_packaged_data_directory_honors_explicit_override(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "portable-data"
    monkeypatch.setenv("DBA_DATA_DIR", str(selected))

    assert desktop._data_directory() == selected.resolve()
