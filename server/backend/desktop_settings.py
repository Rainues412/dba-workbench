"""Device preferences and current-user Windows login startup registration."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
from pathlib import Path

from fastapi import HTTPException

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULTS = {"silent_start": False, "close_to_tray": True}


class WindowsStartup:
    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = subprocess.list2cmdline(command)

    def read(self) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, kind = winreg.QueryValueEx(key, self.name)
                if kind != winreg.REG_SZ:
                    raise OSError("工作台启动项格式不正确。")
                return value
        except FileNotFoundError:
            return None

    def write(self, value: str | None) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE) as key:
            if value is None:
                try:
                    winreg.DeleteValue(key, self.name)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, self.name, 0, winreg.REG_SZ, value)
        if self.read() != value:
            raise OSError("无法确认工作台启动项已保存。")


class DesktopSettings:
    def __init__(self, path: Path, startup: WindowsStartup):
        self.path = path
        self.startup = startup
        self.native_window = False
        self._lock = threading.RLock()

    def options(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return DEFAULTS.copy()
        if not isinstance(value, dict) or set(value) != set(DEFAULTS) or any(type(v) is not bool for v in value.values()):
            raise ValueError("窗口与启动设置格式不正确。")
        return value

    def read(self) -> dict:
        with self._lock:
            options = self.options()
            registered = self.startup.read()
            digest = hashlib.sha256(json.dumps([options, registered, self.startup.command], sort_keys=True).encode()).hexdigest()
            return {
                **options,
                "auto_start": registered == self.startup.command,
                "startup_conflict": registered is not None and registered != self.startup.command,
                "native_window": self.native_window,
                "revision": int(digest[:12], 16) + 1,
            }

    def close_to_tray(self) -> bool:
        try:
            return self.options()["close_to_tray"]
        except (OSError, ValueError):
            logging.exception("无法读取关闭偏好，保留关闭到托盘行为。")
            return True

    def update(self, changes: dict, revision: int) -> dict:
        with self._lock:
            before = self.read()
            if revision != before["revision"]:
                raise HTTPException(409, "设置已发生变化，请重新读取后再试。")
            if before["startup_conflict"] and "auto_start" in changes:
                raise HTTPException(409, "启动项指向其他位置，请先在 Windows 中核对该启动项。")
            enabled = changes.get("auto_start", before["auto_start"])
            if "close_to_tray" in changes and not self.native_window:
                raise HTTPException(409, "关闭到托盘需要使用桌面窗口。")
            options = {key: changes.get(key, before[key]) for key in DEFAULTS}
            old_registration = self.startup.read()
            temporary = self.path.with_suffix(".tmp")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                temporary.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
                if "auto_start" in changes:
                    self.startup.write(self.startup.command if enabled else None)
                os.replace(temporary, self.path)
            except OSError:
                if "auto_start" in changes:
                    self.startup.write(old_registration)
                raise
            finally:
                temporary.unlink(missing_ok=True)
            return self.read()


def startup_command(source: Path, executable: Path, *, compiled: bool, host: str = "") -> tuple[str, list[str]]:
    if compiled:
        return "DBAWorkbench", [str(executable.resolve()), "--on-logon"]
    root = source.resolve().parents[1]
    launcher = root / "tools" / "windows" / "launch_dba_workbench.py"
    pythonw = executable.with_name("pythonw.exe")
    command = [str(pythonw if pythonw.is_file() else executable), str(launcher)]
    if host:
        command.extend(["--desktop-host", host])
    command.append("--on-logon")
    identity = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:12]
    return f"DBAWorkbench.Source.{identity}", command
