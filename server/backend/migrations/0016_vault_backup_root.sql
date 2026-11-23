CREATE TABLE vault_backup_root_layout (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    user_id INTEGER NOT NULL REFERENCES users(id)
);
