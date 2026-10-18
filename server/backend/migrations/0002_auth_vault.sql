CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO roles(name) VALUES ('owner'), ('admin'), ('member'), ('read-only');

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memberships (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reauthenticated_until TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE login_attempts (
    identifier TEXT PRIMARY KEY,
    failures INTEGER NOT NULL DEFAULT 0,
    first_failed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    blocked_until TEXT
);

CREATE TABLE vault_profiles (
    user_id INTEGER PRIMARY KEY,
    envelope_version INTEGER NOT NULL,
    kdf_name TEXT NOT NULL,
    kdf_salt TEXT NOT NULL,
    kdf_memory_kib INTEGER NOT NULL,
    kdf_iterations INTEGER NOT NULL,
    kdf_parallelism INTEGER NOT NULL,
    wrapped_dek TEXT NOT NULL,
    wrapped_dek_nonce TEXT NOT NULL,
    recovery_wrapped_dek TEXT NOT NULL,
    recovery_key_id TEXT NOT NULL,
    recovery_confirmed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE vault_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    envelope_version INTEGER NOT NULL,
    ciphertext TEXT NOT NULL,
    nonce TEXT NOT NULL,
    aad TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE legacy_password_backups (
    id INTEGER PRIMARY KEY,
    site_name TEXT NOT NULL,
    site_url TEXT DEFAULT '',
    username TEXT DEFAULT '',
    password_enc TEXT DEFAULT '',
    category TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    is_favorite INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vault_backup_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    digest TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
