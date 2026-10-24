"""Secure hand-off from authenticated records to the bundled kkFileView service."""
from __future__ import annotations

import base64
import mimetypes
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from backend import word_preview
from backend.config import settings
from backend.database import get_db_ctx
from backend.local_capabilities import audit_local_action, require_local_action, resolve_allowed_path


VIEWER_VERSION = "5.0.3"
VIEWER_KEY = os.environ.get("DBA_FILE_VIEWER_KEY", "false")
TOKEN_TTL_SECONDS = 30 * 60
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
IMAGE_EXTENSIONS = {".png", ".apng", ".jpg", ".jpeg", ".jfif", ".gif", ".webp", ".bmp", ".avif", ".svg", ".ico"}
router = APIRouter()


def _viewer_origin() -> str:
    raw = os.environ.get("DBA_FILE_VIEWER_URL", "http://127.0.0.1:8012").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("DBA_FILE_VIEWER_URL must be a loopback HTTP origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("DBA_FILE_VIEWER_URL contains an invalid port") from exc
    if port is None or not 1 <= port <= 65535:
        raise ValueError("DBA_FILE_VIEWER_URL must include a valid port")
    return raw


VIEWER_ORIGIN = _viewer_origin()


@dataclass(frozen=True)
class PreviewGrant:
    target: Path
    expires_at: float


_grants: dict[str, PreviewGrant] = {}
_grant_lock = threading.Lock()


def _viewer_available() -> bool:
    try:
        request = urllib.request.Request(f"{VIEWER_ORIGIN}/actuator/health", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=1.0) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _record_path(module: str, record_id: int) -> Path:
    if module not in {"articles", "scripts"}:
        raise HTTPException(404, "记录不存在")
    with get_db_ctx() as conn:
        row = conn.execute(f"SELECT file_path FROM {module} WHERE id = ?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "记录不存在")
    if not row["file_path"]:
        raise HTTPException(404, "未关联本地文件")
    require_local_action("open")
    return resolve_allowed_path(row["file_path"], expect="file")


def _new_grant(target: Path) -> str:
    now = time.time()
    token = secrets.token_urlsafe(32)
    with _grant_lock:
        expired = [key for key, grant in _grants.items() if grant.expires_at <= now]
        for key in expired:
            _grants.pop(key, None)
        _grants[token] = PreviewGrant(target=target, expires_at=now + TOKEN_TTL_SECONDS)
    return token


def visual_preview_linked_file(module: str, record_id: int) -> JSONResponse:
    target = None
    try:
        target = _record_path(module, record_id)
        if target.suffix.lower() in MARKDOWN_EXTENSIONS:
            token = _new_grant(target)
            filename = urllib.parse.quote(target.name, safe="")
            audit_local_action("preview", "viewer_granted", target)
            return JSONResponse({
                "filename": target.name,
                "viewer": "markdown",
                "viewer_url": f"/preview-file/{token}/{filename}",
                "asset_url": f"/preview-file/assets/{token}",
            }, headers={"Cache-Control": "no-store"})
        if not _viewer_available():
            raise HTTPException(503, "内置文件预览服务正在启动或不可用，请稍后重试")
        native_word = target.suffix.lower() in word_preview.WORD_EXTENSIONS and word_preview.is_available()
        if native_word:
            try:
                rendered = word_preview.convert(target)
                target = resolve_allowed_path(str(target), expect="file")
            except word_preview.WordPreviewError as exc:
                raise HTTPException(503, str(exc)) from exc
        token = _new_grant(target)
        filename = urllib.parse.quote(rendered.name if native_word else target.name, safe="")
        source_route = f"word/{token}" if native_word else token
        source_url = f"http://127.0.0.1:{settings.port}/preview-file/{source_route}/{filename}"
        encoded = base64.b64encode(source_url.encode("utf-8")).decode("ascii")
        query = urllib.parse.urlencode({"url": encoded, "key": VIEWER_KEY})
        viewer_url = f"{VIEWER_ORIGIN}/onlinePreview?{query}"
        audit_local_action("preview", "viewer_granted", target)
        return JSONResponse(
            {
                "filename": target.name,
                "viewer": "kkFileView",
                "viewer_version": VIEWER_VERSION,
                "converter": "Microsoft Word" if native_word else "kkFileView",
                "viewer_url": viewer_url,
            },
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        audit_local_action("preview", "viewer_denied", target)
        raise
    except OSError:
        audit_local_action("preview", "viewer_unavailable", target)
        raise HTTPException(404, "文件不存在或暂时无法读取")


def _take_grant(token: str) -> Path:
    now = time.time()
    with _grant_lock:
        grant = _grants.get(token)
        if not grant or grant.expires_at <= now:
            _grants.pop(token, None)
            raise HTTPException(404, "预览链接已失效，请重新打开预览")
    require_local_action("open")
    return resolve_allowed_path(str(grant.target), expect="file")


@router.api_route("/assets/{token}", methods=["GET", "HEAD"])
def serve_markdown_image(token: str, reference: str = Query(alias="path", min_length=1, max_length=4096)):
    target = None
    try:
        document = _take_grant(token)
        if document.suffix.lower() not in MARKDOWN_EXTENSIONS:
            raise HTTPException(404, "图片预览链接无效")
        parsed = urllib.parse.urlsplit(reference)
        image_path = urllib.parse.unquote(parsed.path).replace("\\", "/")
        if parsed.scheme or parsed.netloc or image_path.startswith("/") or PureWindowsPath(image_path).drive:
            raise HTTPException(403, "只允许文档目录内的相对图片路径")
        target = resolve_allowed_path(str(document.parent / image_path), expect="file")
        if not target.is_relative_to(document.parent) or target.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(403, "只允许文档目录内的图片文件")
        audit_local_action("preview", "image_read", target)
        media_type = "image/jpeg" if target.suffix.lower() == ".jfif" else mimetypes.guess_type(target.name)[0]
        return FileResponse(target, media_type=media_type, headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        })
    except HTTPException:
        audit_local_action("preview", "image_denied", target)
        raise
    except (OSError, ValueError):
        raise HTTPException(404, "图片不存在或暂时无法读取")


@router.api_route("/word/{token}/{filename}", methods=["GET", "HEAD"])
def serve_word_pdf(token: str, filename: str):
    try:
        target = _take_grant(token)
        if target.suffix.lower() not in word_preview.WORD_EXTENSIONS or filename != word_preview.pdf_name(target):
            raise HTTPException(404, "预览文件已变化，请重新打开预览")
        rendered = word_preview.convert(target)
        resolve_allowed_path(str(target), expect="file")
        audit_local_action("preview", "word_pdf_read", target)
        return FileResponse(rendered, media_type="application/pdf", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        })
    except word_preview.WordPreviewError as exc:
        raise HTTPException(503, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(404, "预览文件不存在或暂时无法读取") from exc


@router.api_route("/{token}/{filename}", methods=["GET", "HEAD"])
def serve_preview_file(token: str, filename: str):
    target = None
    try:
        target = _take_grant(token)
        if filename != target.name:
            raise HTTPException(404, "预览链接无效")
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        audit_local_action("preview", "viewer_read", target)
        return FileResponse(
            target,
            media_type=media_type,
            filename=target.name,
            content_disposition_type="inline",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    except HTTPException:
        audit_local_action("preview", "viewer_read_denied", target)
        raise
    except (OSError, PermissionError):
        audit_local_action("preview", "viewer_read_unavailable", target)
        raise HTTPException(404, "文件不存在或暂时无法读取")
