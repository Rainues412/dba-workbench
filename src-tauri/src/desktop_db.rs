use std::{path::PathBuf, time::Duration};

use rusqlite::{
    params, types::ValueRef, Connection, OpenFlags, OptionalExtension, Params, TransactionBehavior,
};
use serde::Serialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use tauri::WebviewWindow;
use uuid::Uuid;

pub struct Workspace {
    pub path: PathBuf,
    pub origin: tauri::Url,
}

#[derive(Debug, Serialize)]
pub struct CommandError {
    status: u16,
    message: String,
}

impl CommandError {
    pub fn new(status: u16, message: impl Into<String>) -> Self {
        Self {
            status,
            message: message.into(),
        }
    }

    fn unauthorized() -> Self {
        Self::new(401, "Authentication required")
    }

    fn storage() -> Self {
        Self::new(500, "读取或保存本机数据失败，请重试。")
    }
}

pub fn expected_revision(revision: i64) -> Result<()> {
    if revision < 1 {
        return Err(CommandError::new(
            400,
            "If-Match must contain a positive revision",
        ));
    }
    Ok(())
}

impl From<rusqlite::Error> for CommandError {
    fn from(error: rusqlite::Error) -> Self {
        eprintln!("workspace SQLite operation failed: {error}");
        Self::storage()
    }
}

pub type Result<T> = std::result::Result<T, CommandError>;

pub fn query_rows(
    conn: &Connection,
    sql: &str,
    params: impl Params,
) -> rusqlite::Result<Vec<Value>> {
    let mut statement = conn.prepare(sql)?;
    let keys: Vec<String> = statement
        .column_names()
        .into_iter()
        .map(str::to_owned)
        .collect();
    let rows = statement.query_map(params, |row| {
        let mut result = Map::new();
        for (index, key) in keys.iter().enumerate() {
            let value = match row.get_ref(index)? {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(number) => json!(number),
                ValueRef::Real(number) => json!(number),
                _ => json!(row.get::<_, String>(index)?),
            };
            result.insert(key.clone(), value);
        }
        Ok(Value::Object(result))
    })?;
    rows.collect()
}

fn session_token(window: &WebviewWindow, workspace: &Workspace) -> Result<Option<String>> {
    let current = window.url().map_err(|_| CommandError::unauthorized())?;
    if current.origin() != workspace.origin.origin() {
        return Err(CommandError::unauthorized());
    }
    let cookies = window
        .cookies_for_url(workspace.origin.clone())
        .map_err(|_| CommandError::storage())?;
    Ok(cookies
        .into_iter()
        .find(|cookie| cookie.name() == "dba_session")
        .map(|cookie| cookie.value().to_owned()))
}

fn session(
    connection: &Connection,
    token: Option<&str>,
) -> rusqlite::Result<Option<(i64, String, String, i64)>> {
    let Some(token) = token else { return Ok(None) };
    connection.query_row(
        "SELECT s.id, u.username, s.csrf_hash, u.id FROM sessions s
         JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = ?1 AND u.is_active <> 0
           AND datetime(s.expires_at) > CURRENT_TIMESTAMP
           AND EXISTS (SELECT 1 FROM memberships m JOIN roles r ON r.id = m.role_id WHERE m.user_id = u.id)",
        [hex::encode(Sha256::digest(token))],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
    ).optional()
}

pub async fn read<T: Send + 'static>(
    window: WebviewWindow,
    workspace: &Workspace,
    query: impl FnOnce(&Connection) -> Result<T> + Send + 'static,
) -> Result<T> {
    read_user(window, workspace, false, move |conn, _| query(conn)).await
}

pub async fn read_user<T: Send + 'static>(
    window: WebviewWindow,
    workspace: &Workspace,
    count_view: bool,
    query: impl FnOnce(&Connection, i64) -> Result<T> + Send + 'static,
) -> Result<T> {
    let token = session_token(&window, workspace)?;
    let path = workspace.path.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (flags, behavior) = if count_view {
            (
                OpenFlags::SQLITE_OPEN_READ_WRITE,
                TransactionBehavior::Immediate,
            )
        } else {
            (
                OpenFlags::SQLITE_OPEN_READ_ONLY,
                TransactionBehavior::Deferred,
            )
        };
        let mut conn = Connection::open_with_flags(path, flags)?;
        conn.busy_timeout(Duration::from_secs(5))?;
        let tx = conn.transaction_with_behavior(behavior)?;
        let (_, _, _, user_id) =
            session(&tx, token.as_deref())?.ok_or_else(CommandError::unauthorized)?;
        let result = query(&tx, user_id)?;
        tx.commit()?;
        Ok(result)
    })
    .await
    .map_err(|_| CommandError::storage())?
}

pub async fn write<T: Send + 'static>(
    window: WebviewWindow,
    workspace: &Workspace,
    csrf_token: String,
    action: &'static str,
    object_type: &'static str,
    object_id: Option<i64>,
    change: impl FnOnce(&Connection) -> Result<T> + Send + 'static,
) -> Result<T> {
    write_user(
        window,
        workspace,
        csrf_token,
        action,
        object_type,
        object_id,
        move |conn, _| change(conn),
    )
    .await
}

pub async fn write_user<T: Send + 'static>(
    window: WebviewWindow,
    workspace: &Workspace,
    csrf_token: String,
    action: &'static str,
    object_type: &'static str,
    object_id: Option<i64>,
    change: impl FnOnce(&Connection, i64) -> Result<T> + Send + 'static,
) -> Result<T> {
    let token = session_token(&window, workspace)?;
    let path = workspace.path.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut conn = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_WRITE)?;
        conn.busy_timeout(Duration::from_secs(5))?;
        conn.pragma_update(None, "foreign_keys", true)?;
        let mut tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let (actor, result) = match session(&tx, token.as_deref())? {
            None => ("local-user".into(), Err(CommandError::unauthorized())),
            Some((session_id, actor, csrf_hash, user_id)) => {
                tx.execute(
                    "UPDATE sessions SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now') WHERE id = ?1",
                    [session_id],
                )?;
                let result = if csrf_token.is_empty() || hex::encode(Sha256::digest(&csrf_token)) != csrf_hash {
                    Err(CommandError::new(403, "Invalid CSRF token"))
                } else {
                    // Roll back a partial change before recording an unsuccessful operation.
                    let changes = tx.savepoint()?;
                    let result = change(&changes, user_id);
                    if result.is_ok() { changes.commit()?; }
                    result
                };
                (actor, result)
            }
        };
        let outcome = match &result {
            Ok(_) => "success",
            Err(error) if matches!(error.status, 401 | 403) => "denied",
            Err(_) => "failed",
        };
        tx.execute(
            "INSERT INTO audit_events (request_id, actor, action, object_type, object_id, result, source)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'tauri')",
            params![Uuid::new_v4().to_string(), actor, action, object_type, object_id.map(|id| id.to_string()).unwrap_or_default(), outcome],
        )?;
        tx.commit()?;
        result
    }).await.map_err(|_| CommandError::storage())?
}
