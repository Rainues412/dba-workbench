CREATE TABLE script_usage (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    script_id INTEGER NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
    viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_script_usage_recent ON script_usage(user_id, viewed_at, script_id);
CREATE INDEX idx_script_usage_script ON script_usage(script_id);
