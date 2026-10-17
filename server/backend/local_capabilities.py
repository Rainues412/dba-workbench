"""Policy helpers for capabilities that touch the host computer."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from backend.config import settings


audit_logger = logging.getLogger("dba.audit")


def audit_local_action(action: str, result: str, target: Optional[Path] = None) -> None:
    """Record a non-secret local capability event without file contents."""
    target_type = "none"
    target_suffix = ""
    if target is not None:
        target_type = "directory" if target.is_dir() else "file"
        target_suffix = target.suffix.lower()[:16]
    audit_logger.info(
        "local_capability action=%s result=%s target_type=%s target_suffix=%s",
        action,
        result,
        target_type,
        target_suffix,
    )


def require_local_action(action: str) -> None:
    if not settings.local_capabilities:
        audit_local_action(action, "denied_disabled")
        raise HTTPException(403, "本机能力已关闭")
    if action not in settings.allowed_local_actions:
        audit_local_action(action, "denied_action")
        raise HTTPException(403, f"本机动作未获允许: {action}")


def resolve_allowed_path(
    raw_path: str,
    *,
    must_exist: bool = True,
    expect: Optional[str] = None,
) -> Path:
    """Resolve a local path and keep it inside one explicitly allowed root."""
    cleaned = raw_path.strip().strip('"')
    if not cleaned:
        raise HTTPException(400, "路径为空")
    if cleaned.startswith(("\\\\", "//")):
        raise HTTPException(403, "不允许 UNC 或网络路径")

    candidate = Path(cleaned)
    if not candidate.is_absolute():
        raise HTTPException(403, "路径必须是绝对路径")
    try:
        resolved = candidate.resolve(strict=must_exist)
    except (OSError, RuntimeError):
        raise HTTPException(404, "路径不存在或无法解析")

    allowed = False
    for configured_root in settings.allowed_roots:
        root = Path(configured_root).resolve(strict=True)
        try:
            resolved.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise HTTPException(403, "路径超出允许目录")

    if expect == "file" and not resolved.is_file():
        raise HTTPException(400, "路径不是文件")
    if expect == "directory" and not resolved.is_dir():
        raise HTTPException(400, "路径不是目录")
    return resolved
