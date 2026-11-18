"""Register and load the Windows tray icon using the application's ICO."""

from __future__ import annotations

import ctypes
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from PIL import Image
from pystray import Icon
from pystray._util import win32


class WorkbenchTrayIcon(Icon):
    def __init__(self, path: Path, title: str, menu) -> None:
        self._icon_path = path.resolve()
        # The Shell otherwise shares cached entries based on the Python host.
        identity = uuid5(NAMESPACE_URL, f"dba-workbench:tray:{str(self._icon_path).casefold()}")
        self._tray_guid = win32.NOTIFYICONDATAW.GUID.from_buffer_copy(identity.bytes_le)
        with Image.open(self._icon_path) as source:
            super().__init__("dba-workbench", source.copy(), title, menu)

    def _message(self, code, flags, **kwargs):
        # pystray prepares the image with NIM_MODIFY before its first NIM_ADD.
        if code == win32.NIM_MODIFY and not self.visible:
            return
        return super()._message(code, flags | win32.NIF_GUID, guidItem=self._tray_guid, **kwargs)

    def _assert_icon_handle(self) -> None:
        if self._icon_handle:
            return
        user32 = ctypes.windll.user32
        # Ask Windows for the notification-area dimensions and use the ICO directly.
        self._icon_handle = win32.LoadImage(
            None, str(self._icon_path), win32.IMAGE_ICON,
            user32.GetSystemMetrics(49),  # SM_CXSMICON
            user32.GetSystemMetrics(50),  # SM_CYSMICON
            win32.LR_LOADFROMFILE,
        )
        if not self._icon_handle:
            raise OSError("无法加载系统托盘图标。")
