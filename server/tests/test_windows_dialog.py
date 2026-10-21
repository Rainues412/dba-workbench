from __future__ import annotations

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
