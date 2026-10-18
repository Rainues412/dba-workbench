"""Minimal ordered SQL migration runner for the local SQLite database."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path


MIGRATION_PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
LEGACY_TABLES = {
    "articles", "audit_events", "communications", "contacts", "customers",
    "passwords", "resources", "scan_dirs", "script_versions", "scripts", "tasks",
}
LEGACY_COLUMNS = {
    "articles": {"file_path", "wb_db", "revision"},
    "customers": {"wb_person", "wb_contact", "revision"},
    "resources": {"wb_db", "revision"},
    "scripts": {"file_path", "wb_type", "revision"},
    "tasks": {"revision"},
}


def _migration_files() -> list[tuple[int, Path]]:
    root = Path(__file__).parent
    files: list[tuple[int, Path]] = []
    for path in sorted(root.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if match:
            files.append((int(match.group(1)), path))
    actual = [version for version, _ in files]
    expected = list(range(1, len(files) + 1))
    if actual != expected:
        raise RuntimeError(f"migration versions must be contiguous: {actual}")
    return files


def latest_version() -> int:
    files = _migration_files()
    return files[-1][0] if files else 0


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not row[0].startswith("sqlite_")
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _baseline_legacy_database(conn: sqlite3.Connection) -> None:
    if "schema_migrations" in _tables(conn):
        recorded = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        if recorded:
            return
    application_tables = _tables(conn) - {"schema_migrations"}
    if not application_tables:
        return
    if not LEGACY_TABLES.issubset(application_tables):
        missing = sorted(LEGACY_TABLES - application_tables)
        raise RuntimeError(
            "database cannot be baselined; missing legacy tables: " + ", ".join(missing)
        )
    for table, required in LEGACY_COLUMNS.items():
        missing = required - _columns(conn, table)
        if missing:
            raise RuntimeError(
                f"database cannot be baselined; {table} is missing columns: "
                + ", ".join(sorted(missing))
            )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, name) VALUES(1, 'initial')"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    if "schema_migrations" not in _tables(conn):
        return set()
    return {int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations")}


def migrate(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        _baseline_legacy_database(conn)
        applied = _applied_versions(conn)
        for version, path in _migration_files():
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            name = path.stem.split("_", 1)[1].replace("'", "''")
            script = (
                "BEGIN IMMEDIATE;\n" + sql
                + f"\nINSERT INTO schema_migrations(version, name) VALUES({version}, '{name}');\n"
                + f"PRAGMA user_version = {version};\nCOMMIT;"
            )
            try:
                conn.executescript(script)
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            applied.add(version)
        present = _applied_versions(conn)
        expected = set(range(1, latest_version() + 1))
        if present != expected:
            raise RuntimeError(
                f"migration history mismatch: expected {sorted(expected)}, got {sorted(present)}"
            )
    finally:
        conn.close()
