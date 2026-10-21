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


def test_task_retention_upgrade_preserves_records_and_only_backfills_undated_completions(tmp_path, monkeypatch):
    path = tmp_path / "pre-retention.db"
    files = migration_module._migration_files()
    with monkeypatch.context() as patch:
        patch.setattr(migration_module, "_migration_files", lambda: files[:5])
        migrate(path)
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO tasks(title, status, completed_at, created_at, description) VALUES (?, ?, ?, '2000-01-01', '保留正文')", [
            ("未完成", "待处理", None),
            ("无完成日期", "已完成", None),
            ("日期无效", "已完成", "invalid"),
            ("有完成日期", "已完成", "2020-01-02T03:00:00Z"),
        ])
        conn.execute("INSERT INTO scripts(title, content) VALUES ('原脚本', 'select 1')")
        conn.commit()
        before = conn.execute("SELECT id, title, description, status, created_at, completed_at, revision FROM tasks ORDER BY id").fetchall()
    migrate(path)
    migrate(path)
    with sqlite3.connect(path) as conn:
        after = conn.execute("SELECT id, title, description, status, created_at, completed_at, revision FROM tasks ORDER BY id").fetchall()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT title, content FROM scripts").fetchall() == [("原脚本", "select 1")]
        for old, new in zip(before, after, strict=True):
            assert old[:5] == new[:5]
        assert before[0] == after[0] and before[3] == after[3]
        for row in after[1:3]:
            assert row[-2] is not None and row[-1] == 2
            assert conn.execute("SELECT julianday(?) > julianday('now', '-1 minute')", (row[-2],)).fetchone()[0]
