import base64
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import word_preview


def test_conversion_cache_tracks_source_version_and_preserves_original(tmp_path, monkeypatch):
    monkeypatch.setenv("DBA_FILE_VIEWER_DATA_DIR", str(tmp_path / "viewer"))
    source = tmp_path / "原件.docx"
    source.write_bytes(b"original")
    calls = []

    def export(target, output, owner):
        calls.append(target.read_bytes())
        output.write_bytes(b"%PDF-1.7\nconverted")

    monkeypatch.setattr(word_preview, "_export", export)
    first = word_preview.convert(source)
    assert word_preview.convert(source) == first
    assert calls == [b"original"]
    assert source.read_bytes() == b"original"
    source.write_bytes(b"changed document")
    second = word_preview.convert(source)
    assert second != first
    assert calls == [b"original", b"changed document"]
    assert list(first.parent.glob("*.json")) == []


@pytest.mark.parametrize("failure", ["error", "empty", "changed"])
def test_failed_or_outdated_export_is_not_cached(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("DBA_FILE_VIEWER_DATA_DIR", str(tmp_path / "viewer"))
    source = tmp_path / "original.docx"
    source.write_bytes(b"original")

    def export(target, output, owner):
        owner.write_text("{}")
        if failure == "error":
            output.write_bytes(b"partial")
            raise word_preview.WordPreviewError("failed")
        if failure == "changed":
            output.write_bytes(b"%PDF")
            target.write_bytes(b"edited during export")

    monkeypatch.setattr(word_preview, "_export", export)
    with pytest.raises(word_preview.WordPreviewError):
        word_preview.convert(source)
    assert list(word_preview._cache_root().iterdir()) == []


def test_worker_keeps_paths_out_of_shell_code_and_times_out_safely(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    source = tmp_path / "原件 ' $().docx"
    output, owner = tmp_path / "result.pdf", tmp_path / "owner.json"
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        script = base64.b64decode(command[-1]).decode("utf-16le")
        assert str(source) not in script
        assert kwargs["env"]["DBA_WORD_SOURCE"] == str(source)
        if len(calls) == 1:
            assert "AutomationSecurity = 3" in script
            assert "UpdateLinksAtOpen = $false" in script
            assert "Documents.Open($env:DBA_WORD_SOURCE, $false, $true, $false" in script
            assert "$previous -contains $wordProcess" in script
            owner.write_text("{}")
            raise subprocess.TimeoutExpired(command, 120)
        assert "StartTime.ToUniversalTime().Ticks" in script
        assert "'WINWORD'" in script
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(word_preview.subprocess, "run", run)
    with pytest.raises(word_preview.WordPreviewError, match="超时"):
        word_preview._export(source, output, owner)
    assert len(calls) == 2


def test_worker_reports_native_failure_without_exposing_output(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setattr(word_preview.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(word_preview.WordPreviewError, match="Word 转换失败"):
        word_preview._export(tmp_path / "private.docx", tmp_path / "out.pdf", tmp_path / "owner.json")
