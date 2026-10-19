"""SQLite access and versioned migration entry point for DBA Workspace."""
from __future__ import annotations

import math
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.migrations import latest_version, migrate


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace.db"
)

PAGE_SIZE_MIN = 1
PAGE_SIZE_MAX = 200


def get_db() -> sqlite3.Connection:
    """Open an application connection with consistent safety settings."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_db_ctx():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def validate_page(page: int, page_size: int):
    page = max(1, page)
    page_size = max(PAGE_SIZE_MIN, min(page_size, PAGE_SIZE_MAX))
    return (page - 1) * page_size, page_size


def page_response(total: int, rows, page: int, page_size: int, **extra):
    page = max(1, page)
    pages = math.ceil(total / page_size) if total else 0
    return {
        "total": total,
        "items": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1 and pages > 0,
        **extra,
    }


def check_schema_compatibility() -> None:
    """Reject databases produced by a newer application before writing."""
    path = Path(DB_PATH).resolve()
    if not path.exists():
        return
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > latest_version():
            raise RuntimeError(
                f"database schema version {version} is newer than supported "
                f"version {latest_version()}"
            )
    finally:
        conn.close()


def run_startup_migrations() -> None:
    """Apply tested, forward-only migrations in a transaction per version."""
    check_schema_compatibility()
    migrate(Path(DB_PATH))
