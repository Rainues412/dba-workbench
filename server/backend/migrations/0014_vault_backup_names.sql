CREATE TABLE vault_backup_names (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    display_name TEXT NOT NULL,
    PRIMARY KEY (user_id, filename)
);
