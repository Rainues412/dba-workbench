from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import backend.migrations as migration_module
from backend.migrations import latest_version, migrate


def test_empty_database_upgrades_to_current_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    migrate(path)
    migrate(path)
    with sqlite3.connect(path) as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version()
    assert versions == list(range(1, latest_version() + 1))
    assert {"users", "sessions", "vault_profiles", "vault_items"}.issubset(tables)
    assert "idx_vault_items_user_nonce" in indexes


def test_stage_one_legacy_schema_is_baselined_then_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    sql = (Path(__file__).parents[1] / "backend" / "migrations" / "0001_initial.sql").read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(sql)
        conn.execute("DELETE FROM schema_migrations")
        conn.execute("PRAGMA user_version = 0")
    migrate(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version()
        assert conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 4


def test_query_plan_uses_filter_indexes(tmp_path: Path) -> None:
    path = tmp_path / "plans.db"
    migrate(path)
    with sqlite3.connect(path) as conn:
        script_plan = " ".join(
            row[3]
            for row in conn.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM scripts WHERE db_type = ? AND wb_type = ? ORDER BY updated_at DESC, id DESC",
                ("Oracle", "巡检"),
            )
        )
        article_plan = " ".join(
            row[3]
            for row in conn.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM articles WHERE wb_db = ? AND category = ? ORDER BY updated_at DESC, id DESC",
                ("Oracle", "巡检规范"),
            )
        )
    assert "idx_scripts_filter_updated" in script_plan
    assert "idx_articles_filter_updated" in article_plan


def test_failed_migration_is_rolled_back_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "atomic.db"
    original_files = migration_module._migration_files()
    current_version = original_files[-1][0]
    broken = tmp_path / f"{current_version + 1:04d}_broken.sql"
    broken.write_text("CREATE TABLE must_rollback(id INTEGER);\nTHIS IS NOT SQL;", encoding="utf-8")
    monkeypatch.setattr(migration_module, "_migration_files", lambda: [*original_files, (current_version + 1, broken)])

    with pytest.raises(sqlite3.OperationalError):
        migrate(path)

    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        assert "must_rollback" not in tables
        assert versions == list(range(1, current_version + 1))
        assert conn.execute("PRAGMA user_version").fetchone()[0] == current_version
