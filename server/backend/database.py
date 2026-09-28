"""Database connection and initialization for DBA Workspace."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace.db")


def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _column_names(c, table):
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(c, table, column, decl):
    """Idempotent ALTER TABLE ADD COLUMN."""
    if column not in _column_names(c, table):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def migrate_db(conn):
    """Add new tables/columns for v0.2 (resource index, vault, scan)."""
    c = conn.cursor()

    # ── 文件路径索引：脚本 / 文章可关联本地文件 ──
    _add_column(c, "scripts", "file_path", "TEXT DEFAULT ''")
    _add_column(c, "articles", "file_path", "TEXT DEFAULT ''")

    # ── 单文件前端（ops-workbench.html）的自有分类字段 ──
    _add_column(c, "scripts", "wb_type", "TEXT DEFAULT '其他'")
    _add_column(c, "articles", "wb_db", "TEXT DEFAULT '通用'")
    _add_column(c, "customers", "wb_person", "TEXT DEFAULT ''")
    _add_column(c, "customers", "wb_contact", "TEXT DEFAULT ''")

    # ── 工具箱 / 资源索引（安装包、软件、本地文件、网址）──
    c.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT DEFAULT '安装包',
            path TEXT DEFAULT '',
            url TEXT DEFAULT '',
            version TEXT DEFAULT '',
            size_mb REAL DEFAULT 0,
            category TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 密码本（Fernet 加密，密钥存本地 .workspace_secret）──
    c.execute("""
        CREATE TABLE IF NOT EXISTS passwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT NOT NULL,
            site_url TEXT DEFAULT '',
            username TEXT DEFAULT '',
            password_enc TEXT DEFAULT '',
            category TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 扫描入库：监听目录配置 ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS scan_dirs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()


def init_db():
    """Create all tables and FTS indexes."""
    conn = get_db()
    c = conn.cursor()

    # ── 脚本库 ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            db_type TEXT DEFAULT '通用',
            tags TEXT DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            version INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS script_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
        )
    """)

    # ── 知识库 ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            category TEXT DEFAULT '学习记录',
            tags TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            is_pinned INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 客户管理 (must be before tasks due to FK) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_name TEXT DEFAULT '',
            group_name TEXT DEFAULT '',
            status TEXT DEFAULT '活跃',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 任务清单 ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT '待处理',
            priority TEXT DEFAULT '中',
            due_date TEXT,
            customer_id INTEGER,
            is_overdue INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            wechat TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS communications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            follow_up TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)

    migrate_db(conn)
    conn.commit()
    conn.close()
