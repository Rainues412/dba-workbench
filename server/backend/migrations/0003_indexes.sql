CREATE INDEX idx_scripts_filter_updated ON scripts(db_type, wb_type, updated_at DESC, id DESC);
CREATE INDEX idx_articles_filter_updated ON articles(wb_db, category, updated_at DESC, id DESC);
CREATE INDEX idx_resources_filter_updated ON resources(wb_db, kind, updated_at DESC, id DESC);
CREATE INDEX idx_tasks_status_due ON tasks(status, due_date, id DESC);
CREATE INDEX idx_customers_status_updated ON customers(status, updated_at DESC, id DESC);
CREATE INDEX idx_audit_created ON audit_events(created_at DESC, id DESC);
CREATE INDEX idx_sessions_user_expiry ON sessions(user_id, expires_at);
CREATE INDEX idx_vault_items_user_updated ON vault_items(user_id, updated_at DESC, id DESC);
