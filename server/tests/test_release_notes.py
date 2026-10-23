import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "tools" / "release_notes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_release_notes_select_only_the_requested_version_and_include_its_assets():
    changelog = "# 更新日志\n\n## 2.0.0 - 2026-10-25\n\n新版本功能\n\n## 1.0.0 - 2026-10-20\n\n旧版本功能\n"
    notes = module.release_notes(changelog, "v2.0.0", "owner/repo", sha256="ab" * 32)
    assert "新版本功能" in notes
    assert "旧版本功能" not in notes
    assert "releases/download/v2.0.0/DBA-Workbench-Setup-2.0.0-x64.exe" in notes
    assert "AB" * 32 in notes


@pytest.mark.parametrize("changelog,version", [
    ("## 1.0.0 - 2026-10-20\n\n旧版本", "1.1.0"),
    ("## 1.0.0 - 2026-10-20\n\n", "1.0.0"),
    ("## 1.0.0 - 2026-10-20\n\n第一条\n\n## 1.0.0 - 2026-10-20\n\n重复条目", "1.0.0"),
    ("## 1.0.0 - 2026-10-20\n\n旧版本", "1.0.0-preview"),
])
def test_release_notes_fail_closed_if_release_history_is_missing_or_ambiguous(changelog, version):
    with pytest.raises(ValueError):
        module.release_notes(changelog, version, "owner/repo")


def test_all_recorded_versions_have_release_notes_without_inventing_old_assets():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for version in ["1.0.3", "1.0.4", "1.0.5", "1.0.6", "1.1.0"]:
        notes = module.release_notes(changelog, version, "Rainues412/dba-workbench", assets=version != "1.0.3")
        assert f"## {version} - " in notes
        if version == "1.0.3":
            assert "releases/download/v1.0.3" not in notes
