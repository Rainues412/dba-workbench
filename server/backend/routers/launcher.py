"""Launcher API - open local files/folders/URLs from the workspace.

The workspace only stores *paths*; opening happens here via os.startfile
(files/folders) or webbrowser (URLs). Files never move.
"""
import os
import subprocess
import webbrowser
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Common editors, first existing one wins
EDITORS = [
    r"C:\Program Files\Microsoft VS Code\Code.exe",
    r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    r"C:\Program Files\Notepad++\notepad++.exe",
]


class OpenRequest(BaseModel):
    path: str
    mode: str = "open"  # open | folder | edit | run


def _normalize(path: str) -> str:
    return path.strip().strip('"')


@router.post("/path")
def open_path(req: OpenRequest):
    """Open a local path or URL according to mode."""
    p = _normalize(req.path)
    if not p:
        raise HTTPException(400, "路径为空")

    # URL
    if p.lower().startswith(("http://", "https://", "ftp://", "file://")):
        webbrowser.open(p)
        return {"ok": True, "action": "browser", "path": p}

    target = Path(p)
    if not target.exists():
        raise HTTPException(404, f"路径不存在: {p}")

    if req.mode == "folder":
        # Open the containing folder, select the file if possible
        if target.is_file():
            # 用列表形式调用 explorer，避免路径中引号/特殊字符触发 shell 注入
            subprocess.Popen(["explorer", "/select,", str(target.resolve())])
        else:
            os.startfile(str(target.resolve()))  # noqa: S606
        return {"ok": True, "action": "explorer", "path": str(target)}

    if req.mode == "edit":
        if target.is_dir():
            raise HTTPException(400, "目录无法用编辑器打开")
        editor = next((e for e in EDITORS if os.path.exists(e)), None)
        if editor:
            subprocess.Popen([editor, str(target.resolve())])
        else:
            subprocess.Popen(["notepad.exe", str(target.resolve())])
        return {"ok": True, "action": "editor", "path": str(target)}

    if req.mode == "run":
        if target.is_dir():
            raise HTTPException(400, "目录无法执行")
        suffix = target.suffix.lower()
        if suffix in (".bat", ".cmd"):
            subprocess.Popen(["cmd.exe", "/c", str(target.resolve())], cwd=str(target.parent))
        elif suffix == ".ps1":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target.resolve())],
                cwd=str(target.parent),
            )
        elif suffix == ".py":
            subprocess.Popen(["python", str(target.resolve())], cwd=str(target.parent))
        elif suffix == ".sh":
            # Run via Git Bash if available
            bash = r"C:\Program Files\Git\bin\bash.exe"
            if os.path.exists(bash):
                subprocess.Popen([bash, str(target.resolve())], cwd=str(target.parent))
            else:
                raise HTTPException(400, "未找到 Git Bash，无法执行 .sh")
        else:
            os.startfile(str(target.resolve()))  # noqa: S606
        return {"ok": True, "action": "run", "path": str(target)}

    # default: open
    os.startfile(str(target.resolve()))  # noqa: S606
    return {"ok": True, "action": "open", "path": str(target)}


@router.post("/check")
def check_path(req: OpenRequest):
    """Check whether a path exists (used to mark broken links in UI)."""
    p = _normalize(req.path)
    if p.lower().startswith(("http://", "https://")):
        return {"exists": True, "type": "url"}
    target = Path(p)
    return {
        "exists": target.exists(),
        "type": "dir" if target.is_dir() else ("file" if target.is_file() else "missing"),
    }
