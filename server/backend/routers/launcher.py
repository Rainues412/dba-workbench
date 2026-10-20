"""Launcher API - open local files/folders/URLs from the workspace.

The workspace only stores *paths*; opening happens here via os.startfile
(files/folders) or webbrowser (URLs). Files never move.
"""
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.local_capabilities import (
    allowed_roots,
    audit_local_action,
    enroll_allowed_root,
    folder_enrollment_enabled,
    require_local_action,
    resolve_allowed_path,
)

router = APIRouter()

def _discover_editors() -> list[str]:
    """Resolve configured/PATH editors without fixed installation directories."""
    candidates = [os.environ.get("DBA_EDITOR", ""), "code", "notepad++"]
    resolved: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip().strip('"')
        if not candidate:
            continue
        executable = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if executable and executable not in resolved:
            resolved.append(executable)
    return resolved


EDITORS = _discover_editors()


class OpenRequest(BaseModel):
    path: str
    mode: str = "open"  # open | folder | edit | run


class PickFolderRequest(BaseModel):
    title: str = "选择文件夹"
    initial_dir: str = ""


def _normalize(path: str) -> str:
    return path.strip().strip('"')


def _target(path: str, *, expect: Optional[str] = None) -> Path:
    try:
        return resolve_allowed_path(path, expect=expect)
    except HTTPException:
        audit_local_action("path", "denied_path")
        raise


@router.post("/path")
def open_path(req: OpenRequest):
    """Open a local path or URL according to mode."""
    p = _normalize(req.path)
    mode = req.mode.strip().lower()
    if mode not in {"open", "folder", "edit", "run"}:
        raise HTTPException(400, "不支持的本机动作")
    require_local_action(mode)

    # URL
    if p.lower().startswith(("http://", "https://")):
        if mode != "open":
            raise HTTPException(400, "网址仅支持 open 动作")
        webbrowser.open(p)
        audit_local_action(mode, "success")
        return {"ok": True, "action": "browser", "path": p}
    if "://" in p:
        audit_local_action(mode, "denied_scheme")
        raise HTTPException(400, "仅允许 http/https 网址")

    target = _target(p)

    if mode == "folder":
        # Open the containing folder, select the file if possible
        if target.is_file():
            # 用列表形式调用 explorer，避免路径中引号/特殊字符触发 shell 注入
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            os.startfile(str(target))  # noqa: S606
        audit_local_action(mode, "success", target)
        return {"ok": True, "action": "explorer", "path": str(target)}

    if mode == "edit":
        target = _target(p, expect="file")
        editor = next((e for e in EDITORS if os.path.exists(e)), None)
        if editor:
            subprocess.Popen([editor, str(target)])
        else:
            subprocess.Popen(["notepad.exe", str(target)])
        audit_local_action(mode, "success", target)
        return {"ok": True, "action": "editor", "path": str(target)}

    if mode == "run":
        target = _target(p, expect="file")
        suffix = target.suffix.lower()
        if suffix not in settings.allowed_run_extensions:
            audit_local_action(mode, "denied_extension", target)
            raise HTTPException(403, f"文件类型未获执行许可: {suffix or '(无扩展名)'}")
        if suffix in (".bat", ".cmd"):
            subprocess.Popen(
                ["cmd.exe", "/d", "/s", "/c", f'"{target}"'],
                cwd=str(target.parent),
            )
        elif suffix == ".ps1":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-File", str(target)],
                cwd=str(target.parent),
            )
        elif suffix == ".py":
            subprocess.Popen([sys.executable, str(target)], cwd=str(target.parent))
        elif suffix == ".sh":
            # Run via Git Bash if available
            configured_bash = os.environ.get("DBA_GIT_BASH", "").strip().strip('"')
            bash = configured_bash if configured_bash and Path(configured_bash).is_file() else shutil.which("bash")
            if bash:
                subprocess.Popen([bash, str(target)], cwd=str(target.parent))
            else:
                raise HTTPException(400, "未找到 Git Bash，无法执行 .sh")
        audit_local_action(mode, "success", target)
        return {"ok": True, "action": "run", "path": str(target)}

    # default: open
    os.startfile(str(target))  # noqa: S606
    audit_local_action(mode, "success", target)
    return {"ok": True, "action": "open", "path": str(target)}


@router.post("/check")
def check_path(req: OpenRequest):
    """Check whether a path exists (used to mark broken links in UI)."""
    require_local_action("check")
    p = _normalize(req.path)
    if p.lower().startswith(("http://", "https://")):
        audit_local_action("check", "success")
        return {"exists": True, "type": "url"}
    target = _target(p)
    audit_local_action("check", "success", target)
    return {
        "type": "dir" if target.is_dir() else ("file" if target.is_file() else "missing"),
        "exists": True,
    }


@router.post("/pick-folder")
def pick_folder(req: PickFolderRequest):
    """Open a native folder picker dialog and return the selected path."""
    native_enrollment = folder_enrollment_enabled()
    if not native_enrollment:
        require_local_action("pick-folder")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        kwargs = {"title": req.title}
        roots = allowed_roots()
        if req.initial_dir and roots:
            try:
                kwargs["initialdir"] = str(_target(req.initial_dir, expect="directory"))
            except HTTPException:
                pass
        elif roots:
            kwargs["initialdir"] = roots[0]

        path = filedialog.askdirectory(**kwargs)
        root.destroy()

        if path:
            selected = enroll_allowed_root(path) if native_enrollment else _target(path, expect="directory")
            audit_local_action("pick-folder", "success", selected)
            return {"ok": True, "path": str(selected)}
        else:
            audit_local_action("pick-folder", "cancelled")
            return {"ok": False, "path": "", "reason": "cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        audit_local_action("pick-folder", "error")
        raise HTTPException(500, "打开文件夹选择器失败") from e
