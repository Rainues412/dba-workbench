use rusqlite::{functions::FunctionFlags, params, Connection};
use serde_json::{json, Value};
use tauri::{State, WebviewWindow};

use crate::customers::{PROJECT_NAME, PROJECT_ROWS};
use crate::desktop_db::{self, Result, Workspace};

pub fn title_matches(title: &str, keyword: &str) -> bool {
    let title = caseless::default_case_fold_str(title);
    caseless::default_case_fold_str(keyword)
        .split(|ch: char| ch.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&ch))
        .filter(|term| !term.is_empty())
        .all(|term| {
            let ascii_word = term
                .bytes()
                .all(|ch| ch.is_ascii_alphanumeric() || b"_.+%_-".contains(&ch));
            if !ascii_word {
                return title.contains(term);
            }
            let bytes = title.as_bytes();
            bytes.windows(term.len()).enumerate().any(|(start, part)| {
                part == term.as_bytes() && (start == 0 || !bytes[start - 1].is_ascii_lowercase())
            })
        })
}

pub fn register_title_matching(conn: &Connection) -> rusqlite::Result<()> {
    conn.create_scalar_function(
        "title_matches",
        2,
        FunctionFlags::SQLITE_DETERMINISTIC,
        |ctx| {
            let title = ctx.get::<Option<String>>(0)?.unwrap_or_default();
            let keyword = ctx.get_raw(1).as_str()?;
            Ok(title_matches(&title, keyword))
        },
    )
}

fn find(conn: &Connection, sql: &str, query: &str, limit: i64) -> rusqlite::Result<Vec<Value>> {
    if query.is_empty() {
        return Ok(Vec::new());
    }
    desktop_db::query_rows(conn, sql, params![query, limit])
}

#[tauri::command]
pub async fn global_search(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    query: String,
    limit: i64,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| {
        register_title_matching(conn)?;
        let query = query.trim();
        let limit = if limit == 0 { -1 } else { limit.clamp(1, 100) };
        let scripts = find(conn,
            "SELECT id, title, description, db_type, tags FROM scripts WHERE title_matches(title, ?1) = 1 ORDER BY updated_at DESC LIMIT ?2",
            query, limit)?;
        let articles = find(conn,
            "SELECT id, title, summary, category, tags FROM articles WHERE title_matches(title, ?1) = 1 ORDER BY updated_at DESC LIMIT ?2",
            query, limit)?;
        let customers = find(conn,
            "SELECT id, name, project_name, group_name, status FROM customers WHERE title_matches(name, ?1) = 1 ORDER BY updated_at DESC LIMIT ?2",
            query, limit)?;
        let customer_projects = find(conn,
            &format!("SELECT DISTINCT c.id, c.name AS customer_name, {PROJECT_NAME} AS title
             FROM customers c, {PROJECT_ROWS} WHERE title_matches({PROJECT_NAME}, ?1) = 1
             ORDER BY c.updated_at DESC, c.id DESC, title COLLATE NOCASE LIMIT ?2"),
            query, limit)?;
        let resources = find(conn,
            "SELECT id, name, kind, path, url, category FROM resources WHERE title_matches(name, ?1) = 1 ORDER BY updated_at DESC LIMIT ?2",
            query, limit)?;
        Ok(json!({ "scripts": scripts, "articles": articles, "tasks": [], "customers": customers,
            "customer_projects": customer_projects, "resources": resources, "passwords": [] }))
    }).await
}
