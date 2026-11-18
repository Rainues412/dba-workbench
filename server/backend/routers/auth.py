"""First-owner setup and local cookie-session authentication."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.auth import (
    MIN_PASSWORD_LENGTH,
    REAUTH_MINUTES,
    SESSION_COOKIE,
    SESSION_HOURS,
    UNSET_PASSWORD_HASH,
    attempt_identifier,
    clear_attempts,
    create_session,
    desktop_login_enabled,
    desktop_owner_id,
    hash_password,
    insert_owner,
    load_session,
    mark_reauthenticated,
    owner_exists,
    password_needs_rehash,
    record_failed_attempt,
    retry_after,
    revoke_session,
    validate_password,
    verify_desktop_login,
    verify_password,
)
from backend.config import settings
from backend.database import get_db_ctx


router = APIRouter()


class Credentials(BaseModel):
    username: Annotated[str, Field(min_length=3, max_length=64)]
    password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)]


class Reauthenticate(BaseModel):
    password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)]
    initialize_password: bool = False


def _username(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 3 or any(char.isspace() for char in normalized):
        raise HTTPException(422, "Username must be at least 3 characters without spaces")
    return normalized


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_HOURS * 60 * 60,
        httponly=True,
        secure=settings.mode == "lan",
        samesite="strict",
        path="/",
    )


def _session_payload(session: dict, csrf: str | None = None) -> dict:
    return {
        "authenticated": True,
        "setup_required": False,
        "user": {
            "id": session["user_id"],
            "username": session["username"],
            "roles": list(session["roles"]),
        },
        "csrf_token": csrf,
        "reauthenticated_until": session.get("reauthenticated_until"),
        "reauth_minutes": REAUTH_MINUTES,
        "password_setup_required": bool(session["password_setup_required"]),
    }


@router.get("/status")
def status(request: Request):
    session = load_session(request)
    if not session:
        return {"authenticated": False, "setup_required": not desktop_login_enabled() and not owner_exists()}
    return _session_payload(session, session["csrf_token"])


@router.post("/setup", status_code=201)
def setup(data: Credentials, response: Response):
    if desktop_login_enabled():
        raise HTTPException(403, "Manual owner setup is disabled in desktop mode")
    if owner_exists():
        raise HTTPException(409, "Owner already exists")
    username = _username(data.username)
    validate_password(data.password)
    password_hash = hash_password(data.password)
    with get_db_ctx() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise HTTPException(409, "Owner already exists")
            user_id = insert_owner(conn, username, password_hash)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    token, csrf = create_session(user_id)
    _set_cookie(response, token)
    return {
        "authenticated": True,
        "setup_required": False,
        "user": {"id": user_id, "username": username, "roles": ["owner"]},
        "csrf_token": csrf,
        "reauthenticated_until": None,
        "reauth_minutes": REAUTH_MINUTES,
    }


@router.post("/desktop", status_code=204)
def desktop_login(request: Request, response: Response):
    if settings.mode != "local" or not verify_desktop_login(request.headers.get("X-DBA-Desktop-Token")):
        raise HTTPException(401, "Invalid desktop launch token")
    user_id = desktop_owner_id()
    revoke_session(request.cookies.get(SESSION_COOKIE))
    token, _ = create_session(user_id)
    _set_cookie(response, token)


@router.post("/login")
def login(data: Credentials, request: Request, response: Response):
    username = _username(data.username)
    identifier = attempt_identifier(request, username)
    delay = retry_after(identifier)
    if delay:
        raise HTTPException(429, f"Too many login attempts; retry in {delay} seconds")
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        valid = bool(row and row["is_active"] and verify_password(row["password_hash"], data.password))
        if valid and password_needs_rehash(row["password_hash"]):
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (hash_password(data.password), row["id"]),
            )
            conn.commit()
    if not valid:
        record_failed_attempt(identifier)
        raise HTTPException(401, "Invalid username or password")
    clear_attempts(identifier)
    revoke_session(request.cookies.get(SESSION_COOKIE))
    token, csrf = create_session(int(row["id"]))
    _set_cookie(response, token)
    session = load_session(request)
    # load_session sees the old request cookie, so build the small response directly.
    return {
        "authenticated": True,
        "setup_required": False,
        "user": {"id": row["id"], "username": row["username"], "roles": ["owner"]},
        "csrf_token": csrf,
        "reauthenticated_until": None,
        "reauth_minutes": REAUTH_MINUTES,
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/reauthenticate")
def reauthenticate(data: Reauthenticate, request: Request):
    session = request.state.session
    identifier = attempt_identifier(request, f"reauth:{session['username']}")
    delay = retry_after(identifier)
    if delay:
        raise HTTPException(429, f"Too many verification attempts; retry in {delay} seconds")
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
            (session["user_id"],),
        ).fetchone()
        if row and data.initialize_password:
            if row["password_hash"] != UNSET_PASSWORD_HASH:
                raise HTTPException(409, "敏感操作密码已设置，请刷新后验证。")
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND password_hash = ? AND is_active = 1",
                (hash_password(data.password), session["user_id"], UNSET_PASSWORD_HASH),
            )
            if cursor.rowcount != 1:
                raise HTTPException(409, "敏感操作密码已设置，请刷新后验证。")
            conn.commit()
    if not row or (not data.initialize_password and not verify_password(row["password_hash"], data.password)):
        record_failed_attempt(identifier)
        raise HTTPException(401, "Invalid password")
    clear_attempts(identifier)
    until = mark_reauthenticated(session["id"])
    request.state.session["reauthenticated_until"] = until
    return {"reauthenticated_until": until}
