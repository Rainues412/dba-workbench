CREATE TABLE vault_backup_layout (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE vault_backup_file_kinds (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('auto', 'manual', 'safety')),
    PRIMARY KEY (user_id, file_id)
);
