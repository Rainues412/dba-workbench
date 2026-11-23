CREATE TABLE vault_backup_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    interval_hours INTEGER NOT NULL DEFAULT 24 CHECK (interval_hours IN (0, 6, 12, 24, 48, 168)),
    retention INTEGER NOT NULL DEFAULT 10 CHECK (retention IN (3, 5, 10, 15, 20, 30, 50)),
    portable_seal TEXT,
    signing_key TEXT,
    vault_identity TEXT
);
