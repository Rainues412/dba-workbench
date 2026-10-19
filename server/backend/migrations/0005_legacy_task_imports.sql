-- Idempotency receipts keep explicit legacy archive imports safe to retry.
CREATE TABLE legacy_task_imports (
    source_key TEXT PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
