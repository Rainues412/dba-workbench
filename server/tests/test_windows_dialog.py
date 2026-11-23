from __future__ import annotations

import ctypes
import ctypes.wintypes
import os

import pytest

from backend import windows_dialog


def test_folder_picker_uses_the_current_foreground_window_as_owner(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr(windows_dialog.os, "name", "nt")
    monkeypatch.setattr(windows_dialog, "_foreground_window", lambda: 2468)
    monkeypatch.setattr(
        windows_dialog,
        "_pick_folder_sta",
        lambda title, initial_dir, owner: calls.append((title, initial_dir, owner)) or r"D:\Note",
    )

    assert windows_dialog.pick_folder("选择文档目录", r"D:\Note") == r"D:\Note"
    assert calls == [("选择文档目录", r"D:\Note", 2468)]


def test_file_picker_passes_the_starting_directory_and_filter(monkeypatch) -> None:
    monkeypatch.setattr(windows_dialog.os, "name", "nt")
    monkeypatch.setattr(windows_dialog, "_foreground_window", lambda: 2468)
    calls = []
    monkeypatch.setattr(windows_dialog, "_pick_item_sta", lambda *args: calls.append(args) or "")
    assert windows_dialog.pick_file("选择备份文件", r"D:\work\backups", "*.age;*.json") == ""
    assert calls == [("选择备份文件", r"D:\work\backups", 2468, "*.age;*.json")]


@pytest.mark.skipif(os.name != "nt", reason="Windows COM calling convention")
@pytest.mark.parametrize(("hresult", "accepted"), [(0, True), (0x800704C7, False), (0x80004005, None)])
def test_folder_picker_show_distinguishes_cancellation_from_failure(hresult, accepted) -> None:
    method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.wintypes.HWND)(
        lambda *_: ctypes.c_long(hresult).value,
    )
    address = ctypes.cast(method, ctypes.c_void_p).value
    assert address is not None
    if accepted is None:
        with pytest.raises(OSError) as exc:
            windows_dialog._show_dialog(ctypes.c_void_p(), address, 0)
        assert (exc.value.winerror & 0xFFFFFFFF) == hresult
    else:
        assert windows_dialog._show_dialog(ctypes.c_void_p(), address, 0) is accepted
