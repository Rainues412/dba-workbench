"""Short-lived desktop vault grants, independent of workbench login."""
from __future__ import annotations

import hmac
import secrets
import threading
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

from backend.auth import REAUTH_MINUTES, desktop_login_enabled, digest, require_recent_reauth, timestamp, utcnow
from backend.database import get_db_ctx


_grants: dict[str, tuple[str, datetime, str, bytes]] = {}
_lock = threading.Lock()


def grant_access(session: dict, envelope: str, wrapping_key: bytes) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(minutes=REAUTH_MINUTES)
    with _lock:
        for session_key in [key for key, entry in _grants.items() if entry[1] <= now]:
            del _grants[session_key]
        _grants[session["token_hash"]] = (digest(token), expires, envelope, wrapping_key)
    return {"token": token, "expires_at": timestamp(expires)}


def revoke_access(request: Request) -> None:
    session_key = request.state.session["token_hash"]
    supplied = request.headers.get("X-DBA-Vault-Token", "")
    with _lock:
        grant = _grants.get(session_key)
        if grant and supplied and hmac.compare_digest(grant[0], digest(supplied)):
            del _grants[session_key]


def _active_grant(request: Request):
    session = request.state.session
    supplied = request.headers.get("X-DBA-Vault-Token", "")
    with _lock:
        grant = _grants.get(session["token_hash"])
    if not grant or grant[1] <= utcnow() or not supplied or not hmac.compare_digest(grant[0], digest(supplied)):
        raise HTTPException(403, "Vault unlock required")
    with get_db_ctx() as conn:
        profile = conn.execute("SELECT wrapped_dek FROM vault_profiles WHERE user_id = ?", (session["user_id"],)).fetchone()
    if not profile or profile["wrapped_dek"] != grant[2]:
        raise HTTPException(403, "Vault unlock required")
    return grant


def device_wrapping_key(request: Request) -> tuple[str, bytes]:
    grant = _active_grant(request)
    return grant[2], grant[3]


def renew_access(request: Request) -> dict[str, str]:
    grant = _active_grant(request)
    session_key = request.state.session["token_hash"]
    expires = utcnow() + timedelta(minutes=REAUTH_MINUTES)
    with _lock:
        if _grants.get(session_key) is not grant:
            raise HTTPException(403, "Vault unlock required")
        _grants[session_key] = (grant[0], expires, grant[2], grant[3])
    return {"expires_at": timestamp(expires)}


def require_vault_access(request: Request) -> dict:
    if not desktop_login_enabled():
        return require_recent_reauth(request)
    _active_grant(request)
    return request.state.session
