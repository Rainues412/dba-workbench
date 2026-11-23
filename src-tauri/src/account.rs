use std::time::Duration;

use hmac::{Hmac, KeyInit, Mac};
use rusqlite::{Connection, OpenFlags, TransactionBehavior};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, query_rows, CommandError, Result, Workspace};

#[tauri::command]
pub async fn account_status(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> Result<Value> {
    let Some(token) = desktop_db::session_token(&window, &workspace)? else {
        return Ok(json!({"authenticated": false, "setup_required": false}));
    };
    let path = workspace.path.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut conn = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_WRITE)?;
        conn.busy_timeout(Duration::from_secs(5))?;
        conn.pragma_update(None, "foreign_keys", true)?;
        let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let row = query_rows(&tx,
            "SELECT s.id, s.reauthenticated_until, u.id AS user_id, u.username,
                CASE WHEN u.is_active <> 0 AND datetime(s.expires_at) > CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS valid,
                GROUP_CONCAT(r.name) AS roles
             FROM sessions s JOIN users u ON u.id = s.user_id
             JOIN memberships m ON m.user_id = u.id JOIN roles r ON r.id = m.role_id
             WHERE s.token_hash = ?1 GROUP BY s.id",
            [hex::encode(Sha256::digest(&token))],
        )?.pop();
        let Some(row) = row else { return Ok(json!({"authenticated": false, "setup_required": false})); };
        let session_id = row["id"].as_i64().ok_or_else(CommandError::storage)?;
        if row["valid"].as_i64() != Some(1) {
            tx.execute("DELETE FROM sessions WHERE id = ?1", [session_id])?;
            tx.commit()?;
            return Ok(json!({"authenticated": false, "setup_required": false}));
        }
        tx.execute("UPDATE sessions SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now') WHERE id = ?1", [session_id])?;
        tx.commit()?;
        // Match the existing server's CSRF derivation for the same HttpOnly session.
        let mut mac = Hmac::<Sha256>::new_from_slice(token.as_bytes()).map_err(|_| CommandError::storage())?;
        mac.update(b"dba-workbench-csrf-v1");
        let roles: Vec<&str> = row["roles"].as_str().unwrap_or_default().split(',').filter(|role| !role.is_empty()).collect();
        Ok(json!({
            "authenticated": true, "setup_required": false, "vault_password_only": true, "reauth_minutes": 30,
            "user": { "id": row["user_id"], "username": row["username"], "roles": roles },
            "csrf_token": hex::encode(mac.finalize().into_bytes()),
            "reauthenticated_until": row["reauthenticated_until"],
        }))
    }).await.map_err(|_| CommandError::storage())?
}

#[tauri::command]
pub async fn vault_profile(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> Result<Value> {
    desktop_db::read_user(window, &workspace, false, |conn, user_id| {
        let profile = query_rows(conn,
            "SELECT envelope_version, kdf_name, kdf_salt, kdf_memory_kib, kdf_iterations, kdf_parallelism,
                wrapped_dek, wrapped_dek_nonce, recovery_wrapped_dek, recovery_key_id,
                recovery_confirmed_at, created_at, updated_at FROM vault_profiles WHERE user_id = ?1",
            [user_id])?.pop();
        let questions_set = conn.query_row("SELECT EXISTS(SELECT 1 FROM vault_recovery_questions WHERE user_id = ?1)",
            [user_id], |row| row.get::<_, bool>(0))?;
        Ok(json!({ "initialized": profile.is_some(), "profile": profile, "questions_set": questions_set }))
    }).await
}
