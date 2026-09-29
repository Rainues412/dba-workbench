"""Vault API - password manager with Fernet encryption.

Security model (per PRD M04):
- Passwords encrypted with Fernet (AES-128-CBC + HMAC) before hitting SQLite.
- The key lives in `.workspace_secret` next to workspace.db, auto-generated
  on first use, never uploaded anywhere.
- List endpoints NEVER return plaintext passwords; use GET /{id}/reveal.
"""
import logging
import os
import secrets
import stat
import string
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db_ctx, validate_page, DB_PATH

logger = logging.getLogger(__name__)
router = APIRouter()

KEY_FILE = Path(DB_PATH).parent / ".workspace_secret"

CATEGORIES = ["生产系统", "测试环境", "网站", "工具", "其他"]

# 模块级缓存的 Fernet 实例 + 初始化锁（避免并发首次请求时双重生成密钥）
_fernet: Optional[Fernet] = None
_fernet_lock = threading.Lock()


def _get_fernet() -> Fernet:
    """Load or create the local encryption key (cached, thread-safe)."""
    global _fernet
    if _fernet is not None:
        return _fernet
    with _fernet_lock:
        if _fernet is not None:
            return _fernet
        if KEY_FILE.exists():
            key = KEY_FILE.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            KEY_FILE.write_bytes(key)
            # Best-effort: restrict to owner-only on Windows
            try:
                os.chmod(KEY_FILE, stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                pass
            logger.info("Generated new Fernet key at %s", KEY_FILE)
        _fernet = Fernet(key)
        return _fernet


def _encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise HTTPException(500, "解密失败：密钥文件可能已更换（.workspace_secret）")


class PasswordCreate(BaseModel):
    site_name: str
    site_url: str = ""
    username: str = ""
    password: str = ""
    category: str = "其他"
    notes: str = ""


class PasswordUpdate(BaseModel):
    site_name: Optional[str] = None
    site_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # plaintext in, encrypted at rest
    category: Optional[str] = None
    notes: Optional[str] = None
    is_favorite: Optional[int] = None


def _safe_row(row) -> dict:
    d = dict(row)
    d.pop("password_enc", None)
    d["has_password"] = 1 if row["password_enc"] else 0
    return d


@router.get("/")
def list_passwords(keyword: str = "", category: str = "", page: int = 1, page_size: int = 100):
    with get_db_ctx() as conn:
        conditions, params = [], []
        if keyword:
            conditions.append("(site_name LIKE ? OR site_url LIKE ? OR username LIKE ? OR notes LIKE ?)")
            params.extend([f"%{keyword}%"] * 4)
        if category:
            conditions.append("category = ?")
            params.append(category)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM passwords {where}", params).fetchone()[0]
        offset, ps = validate_page(page, page_size)
        rows = conn.execute(
            f"SELECT * FROM passwords {where} ORDER BY is_favorite DESC, updated_at DESC LIMIT ? OFFSET ?",
            params + [ps, offset],
        ).fetchall()
        return {"total": total, "items": [_safe_row(r) for r in rows], "categories": CATEGORIES}


@router.post("/")
def create_password(data: PasswordCreate):
    with get_db_ctx() as conn:
        c = conn.execute(
            """INSERT INTO passwords (site_name, site_url, username, password_enc, category, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (data.site_name, data.site_url, data.username,
             _encrypt(data.password), data.category, data.notes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM passwords WHERE id = ?", (c.lastrowid,)).fetchone()
        return _safe_row(row)


@router.get("/{pid}")
def get_password(pid: int):
    with get_db_ctx() as conn:
        row = conn.execute("SELECT * FROM passwords WHERE id = ?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Password entry not found")
        return _safe_row(row)


@router.get("/{pid}/reveal")
def reveal_password(pid: int):
    """Return the plaintext password (only place it is ever exposed)."""
    with get_db_ctx() as conn:
        row = conn.execute("SELECT password_enc FROM passwords WHERE id = ?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Password entry not found")
        logger.info("Password revealed: id=%s", pid)
        return {"password": _decrypt(row["password_enc"])}


@router.put("/{pid}")
def update_password(pid: int, data: PasswordUpdate):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM passwords WHERE id = ?", (pid,)).fetchone():
            raise HTTPException(404, "Password entry not found")
        updates, params = [], []
        for field in ["site_name", "site_url", "username", "category", "notes", "is_favorite"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if data.password is not None:
            # 允许密码更新（包括设为空字符串表示清除）
            updates.append("password_enc = ?")
            params.append(_encrypt(data.password))
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(pid)
            conn.execute(f"UPDATE passwords SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM passwords WHERE id = ?", (pid,)).fetchone()
        return _safe_row(row)


@router.delete("/{pid}")
def delete_password(pid: int):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM passwords WHERE id = ?", (pid,)).fetchone():
            raise HTTPException(404, "Password entry not found")
        conn.execute("DELETE FROM passwords WHERE id = ?", (pid,))
        conn.commit()
        return {"ok": True}


@router.post("/{pid}/toggle-favorite")
def toggle_favorite(pid: int):
    with get_db_ctx() as conn:
        row = conn.execute("SELECT is_favorite FROM passwords WHERE id = ?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Password entry not found")
        new_val = 0 if row["is_favorite"] else 1
        conn.execute("UPDATE passwords SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_val, pid))
        conn.commit()
        return {"is_favorite": new_val}


@router.post("/generate")
def generate_password(length: int = 16):
    """Random password generator (letters + digits + safe symbols)."""
    length = max(8, min(64, length))
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)
                and any(c in "!@#$%^&*-_" for c in pwd)):
            return {"password": pwd}
