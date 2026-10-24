"""Read-only Word PDF export, following the native Office approach of docx2pdf.

Word owns all layout and rendering. PowerShell provides Windows COM without an
additional runtime dependency; other machines retain the bundled viewer.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading
import uuid

from backend import database


WORD_EXTENSIONS = {".doc", ".docx"}
_conversion_lock = threading.Lock()

# Documents.Open / ExportAsFixedFormat are the same native APIs used by
# https://github.com/AlJohri/docx2pdf and https://github.com/ncdai/docx2pdf-win.
# All paths are process environment values, never interpolated into the script.
_EXPORT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class WordWindow {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
}
'@
$previous = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$word = $null
$document = $null
$probe = $null
$owned = $false
$links = $null
$noSave = 0
try {
    $word = New-Object -ComObject Word.Application
    $probe = $word.Documents.Add()
    [uint32]$wordProcess = 0
    [WordWindow]::GetWindowThreadProcessId([IntPtr]$probe.Windows.Item(1).Hwnd, [ref]$wordProcess) | Out-Null
    if ($wordProcess -eq 0 -or $previous -contains $wordProcess) {
        throw 'Could not create an independent Word instance.'
    }
    $owned = $true
    $probe.Close([ref]$noSave)
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($probe) | Out-Null
    $probe = $null
    $process = Get-Process -Id $wordProcess
    @{ pid = $wordProcess; started = $process.StartTime.ToUniversalTime().Ticks.ToString() } |
        ConvertTo-Json -Compress | Set-Content -LiteralPath $env:DBA_WORD_PID_FILE -Encoding UTF8
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $links = $word.Options.UpdateLinksAtOpen
    $word.Options.UpdateLinksAtOpen = $false
    $password = [Guid]::NewGuid().ToString('N')
    $missing = [Type]::Missing
    $document = $word.Documents.Open($env:DBA_WORD_SOURCE, $false, $true, $false,
        $password, $password, $false, $password, $password, $missing, $missing, $false)
    $document.ExportAsFixedFormat($env:DBA_WORD_OUTPUT, 17, $false, 0)
} finally {
    if ($null -ne $probe) {
        try { $probe.Close([ref]$noSave) } finally {
            [Runtime.InteropServices.Marshal]::FinalReleaseComObject($probe) | Out-Null
        }
    }
    if ($null -ne $document) {
        try { $document.Close([ref]$noSave) } finally {
            [Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) | Out-Null
        }
    }
    if ($owned -and $null -ne $word) {
        try {
            if ($null -ne $links) { $word.Options.UpdateLinksAtOpen = $links }
        } finally { $word.Quit([ref]$noSave) }
    }
    if ($null -ne $word) {
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
    }
}
"""

_CLEANUP_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$owner = Get-Content -LiteralPath $env:DBA_WORD_PID_FILE -Raw | ConvertFrom-Json
if ($null -ne $owner) {
    $process = Get-Process -Id ([int]$owner.pid)
    if ($process.ProcessName -eq 'WINWORD' -and
        $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $owner.started) {
        Stop-Process -Id $process.Id
    }
}
"""


class WordPreviewError(RuntimeError):
    pass


def is_available() -> bool:
    if os.name != "nt":
        return False
    import winreg

    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID", 0, winreg.KEY_READ | view) as key:
                clsid = winreg.QueryValue(key, None)
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32", 0, winreg.KEY_READ | view) as key:
                command = winreg.QueryValue(key, None)
            match = re.match(r'^\s*"?(.+?\\WINWORD\.EXE)"?(?:\s|$)', command, re.IGNORECASE)
            if match and Path(match[1]).is_file():
                return True
        except OSError:
            continue
    return False


def pdf_name(target: Path) -> str:
    stat = target.stat()
    fingerprint = f"word-pdf-v1:{target.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
    return f"{digest}.pdf"


def _cache_root() -> Path:
    configured = os.environ.get("DBA_FILE_VIEWER_DATA_DIR", "").strip()
    root = Path(configured).expanduser().resolve() if configured else Path(database.DB_PATH).resolve().parent.parent / "file-viewer"
    return root / "word-pdf"


def _powershell(script: str) -> list[str]:
    executable = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return [str(executable), "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded]


def _export(target: Path, output: Path, owner: Path) -> None:
    environment = os.environ.copy()
    environment.update({
        "DBA_WORD_SOURCE": str(target), "DBA_WORD_OUTPUT": str(output),
        "DBA_WORD_PID_FILE": str(owner), "TEMP": str(output.parent), "TMP": str(output.parent),
    })
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(_powershell(_EXPORT_SCRIPT), env=environment, capture_output=True,
                                timeout=120, creationflags=flags, check=False)
        if result.returncode:
            raise WordPreviewError("Microsoft Word 转换失败，请确认 Word 可正常打开该文件且文档未加密")
    except subprocess.TimeoutExpired as exc:
        raise WordPreviewError("Microsoft Word 转换超时，请稍后重试或打开原文件") from exc
    except OSError as exc:
        raise WordPreviewError("无法启动 Microsoft Word 预览转换") from exc
    finally:
        if owner.is_file():
            try:
                subprocess.run(_powershell(_CLEANUP_SCRIPT), env=environment, capture_output=True,
                               timeout=10, creationflags=flags, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass


def convert(target: Path) -> Path:
    if target.suffix.lower() not in WORD_EXTENSIONS:
        raise WordPreviewError("只支持 Word 文档的原生转换")
    with _conversion_lock:
        name = pdf_name(target)
        root = _cache_root()
        root.mkdir(parents=True, exist_ok=True)
        destination = root / name
        if destination.is_file() and destination.stat().st_size:
            return destination
        worker_id = uuid.uuid4().hex
        partial = root / f"{worker_id}.pdf"
        owner = root / f"{worker_id}.json"
        try:
            _export(target, partial, owner)
            if pdf_name(target) != name:
                raise WordPreviewError("原文件在转换期间发生变化，请重新打开预览")
            if not partial.is_file() or not partial.stat().st_size:
                raise WordPreviewError("Microsoft Word 未生成预览文件，请打开原文件检查")
            partial.replace(destination)
            return destination
        finally:
            partial.unlink(missing_ok=True)
            owner.unlink(missing_ok=True)
