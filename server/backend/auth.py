"""Local owner authentication, server-side sessions, CSRF and reauthentication."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request

from backend.database import get_db_ctx


SESSION_COOKIE = "dba_session"
SESSION_HOURS = 12
REAUTH_MINUTES = 30
MIN_PASSWORD_LENGTH = 9
PUBLIC_API_PATHS = {
    "/api/auth/status",
    "/api/auth/setup",
    "/api/auth/login",
    "/api/health",
}

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_for_session(token: str) -> str:
    """Return a stable CSRF token bound to one HttpOnly session cookie."""
    return hmac.new(
        token.encode("utf-8"),
        b"dba-workbench-csrf-v1",
        hashlib.sha256,
    ).hexdigest()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_hasher.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, f"Password must contain at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 256:
        raise HTTPException(422, "Password is too long")


def owner_exists() -> bool:
    with get_db_ctx() as conn:
        return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())


def _session_row(token: str):
    with get_db_ctx() as conn:
        row = conn.execute(
            """SELECT sessions.*, users.username, users.is_active,
                      GROUP_CONCAT(roles.name) AS roles
               FROM sessions
               JOIN users ON users.id = sessions.user_id
               JOIN memberships ON memberships.user_id = users.id
               JOIN roles ON roles.id = memberships.role_id
               WHERE sessions.token_hash = ?
               GROUP BY sessions.id""",
            (digest(token),),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        expires = parse_timestamp(data["expires_at"])
        if not data["is_active"] or not expires or expires <= utcnow():
            conn.execute("DELETE FROM sessions WHERE id = ?", (data["id"],))
            conn.commit()
            return None
        conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
            (timestamp(utcnow()), data["id"]),
        )
        conn.commit()
        data["roles"] = tuple(filter(None, (data.get("roles") or "").split(",")))
        return data


def load_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = _session_row(token)
    if session:
        session["csrf_token"] = csrf_for_session(token)
    return session


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = csrf_for_session(token)
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (timestamp(utcnow()),))
        conn.execute(
            """INSERT INTO sessions
               (user_id, token_hash, csrf_hash, expires_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                user_id,
                digest(token),
                digest(csrf),
                timestamp(utcnow() + timedelta(hours=SESSION_HOURS)),
                timestamp(utcnow()),
            ),
        )
        conn.commit()
    return token, csrf


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token),))
        conn.commit()


def verify_csrf(session: dict, supplied: str | None) -> bool:
    expected = session.get("csrf_token")
    return bool(supplied and expected) and hmac.compare_digest(expected, supplied)


def mark_reauthenticated(session_id: int) -> str:
    until = timestamp(utcnow() + timedelta(minutes=REAUTH_MINUTES))
    with get_db_ctx() as conn:
        conn.execute(
            "UPDATE sessions SET reauthenticated_until = ? WHERE id = ?",
            (until, session_id),
        )
        conn.commit()
    return until


def require_recent_reauth(request: Request) -> dict:
    session = getattr(request.state, "session", None)
    if not session:
        raise HTTPException(401, "Authentication required")
    until = parse_timestamp(session.get("reauthenticated_until"))
    if not until or until <= utcnow():
        raise HTTPException(403, "Recent password verification required")
    return session


def attempt_identifier(request: Request, username: str) -> str:
    source = request.client.host if request.client else "unknown"
    return digest(f"{source}|{username.casefold()}")


def retry_after(identifier: str) -> int:
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT blocked_until FROM login_attempts WHERE identifier = ?",
            (identifier,),
        ).fetchone()
    if not row:
        return 0
    blocked_until = parse_timestamp(row["blocked_until"])
    if not blocked_until or blocked_until <= utcnow():
        return 0
    return max(1, int((blocked_until - utcnow()).total_seconds()) + 1)


def record_failed_attempt(identifier: str) -> int:
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT failures FROM login_attempts WHERE identifier = ?",
            (identifier,),
        ).fetchone()
        failures = (int(row["failures"]) if row else 0) + 1
        delay = min(300, 2 ** max(0, failures - 5)) if failures >= 5 else 0
        blocked_until = timestamp(utcnow() + timedelta(seconds=delay)) if delay else None
        conn.execute(
            """INSERT INTO login_attempts(identifier, failures, first_failed_at, blocked_until)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(identifier) DO UPDATE SET
                   failures = excluded.failures,
                   blocked_until = excluded.blocked_until""",
            (identifier, failures, timestamp(utcnow()), blocked_until),
        )
        conn.commit()
    return delay


def clear_attempts(identifier: str) -> None:
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM login_attempts WHERE identifier = ?", (identifier,))
        conn.commit()
