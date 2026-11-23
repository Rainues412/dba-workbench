CREATE TABLE vault_backup_keys (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    vault_identity TEXT NOT NULL,
    recipient TEXT NOT NULL,
    wrapped_dek TEXT NOT NULL,
    exported INTEGER NOT NULL DEFAULT 0 CHECK (exported IN (0, 1))
);
