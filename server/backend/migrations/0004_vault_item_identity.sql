ALTER TABLE vault_items ADD COLUMN item_key TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX idx_vault_items_user_item_key ON vault_items(user_id, item_key);
CREATE UNIQUE INDEX idx_vault_items_user_nonce ON vault_items(user_id, nonce);
