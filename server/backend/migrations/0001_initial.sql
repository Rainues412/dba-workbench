CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    db_type TEXT DEFAULT '通用',
    tags TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    is_favorite INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    file_path TEXT DEFAULT '',
    wb_type TEXT DEFAULT '其他',
    revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE script_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
);

CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    category TEXT DEFAULT '学习记录',
    tags TEXT DEFAULT '',
    is_favorite INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT DEFAULT '',
    wb_db TEXT DEFAULT '通用',
    revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_name TEXT DEFAULT '',
    group_name TEXT DEFAULT '',
    status TEXT DEFAULT '活跃',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    wb_person TEXT DEFAULT '',
    wb_contact TEXT DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT '待处理',
    priority TEXT DEFAULT '中',
    due_date TEXT,
    customer_id INTEGER,
    is_overdue INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
);

CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    wechat TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
);

CREATE TABLE communications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    content TEXT NOT NULL,
    follow_up TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
);

CREATE TABLE resources (
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    wb_db TEXT DEFAULT '通用',
    revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE passwords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT NOT NULL,
    site_url TEXT DEFAULT '',
    username TEXT DEFAULT '',
    password_enc TEXT DEFAULT '',
    category TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    is_favorite INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scan_dirs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT DEFAULT '',
    result TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
