"""Settings available only while the desktop entry point owns this server."""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from backend.concurrency import expected_revision
from backend.desktop_settings import DesktopSettings

router = APIRouter()


class DesktopChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_start: StrictBool | None = None
    silent_start: StrictBool | None = None
    close_to_tray: StrictBool | None = None


def _settings(request: Request) -> DesktopSettings:
    value = getattr(request.app.state, "desktop_settings", None)
    if value is None:
        raise HTTPException(404, "窗口与启动设置由桌面工作台提供。")
    return value


@router.get("/settings")
def read_settings(settings: DesktopSettings = Depends(_settings)):
    try:
        return settings.read()
    except (OSError, ValueError):
        logging.exception("无法读取窗口与启动设置。")
        raise HTTPException(503, "无法读取窗口与启动设置，请检查本机权限后重试。")


@router.put("/settings")
def update_settings(changes: DesktopChanges, settings: DesktopSettings = Depends(_settings), if_match: str | None = Header(default=None)):
    revision = expected_revision(if_match)
    if any(value is None for value in changes.model_dump(exclude_unset=True).values()):
        raise HTTPException(422, "设置值必须为布尔值。")
    try:
        return settings.update(changes.model_dump(exclude_unset=True), revision)
    except (OSError, ValueError):
        logging.exception("无法保存窗口与启动设置。")
        raise HTTPException(503, "设置保存失败，请检查本机权限并重新读取后重试。")
