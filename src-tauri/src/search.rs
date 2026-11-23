use rusqlite::{functions::FunctionFlags, params, types::ValueRef, Connection};
use serde_json::{json, Map, Value};
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, Result, Workspace};

fn title_matches(title: &str, keyword: &str) -> bool {
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
    let mut statement = conn.prepare(sql)?;
    let keys: Vec<String> = statement
        .column_names()
        .into_iter()
        .map(str::to_owned)
        .collect();
    let rows = statement.query_map(params![query, limit], |row| {
        let mut result = Map::new();
        for (index, key) in keys.iter().enumerate() {
            let value = match row.get_ref(index)? {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(number) => json!(number),
                _ => json!(row.get::<_, String>(index)?),
            };
            result.insert(key.clone(), value);
        }
        Ok(Value::Object(result))
    })?;
    rows.collect()
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
            "SELECT DISTINCT c.id, c.name AS customer_name, json_extract(project.value, '$.name') AS title
             FROM customers c, json_each(CASE WHEN c.project_profile IS NULL THEN json_array(json_object('name', c.project_name))
                 ELSE json_extract(c.project_profile, '$.projects') END) AS project
             WHERE title_matches(json_extract(project.value, '$.name'), ?1) = 1
             ORDER BY c.updated_at DESC, c.id DESC, title COLLATE NOCASE LIMIT ?2",
            query, limit)?;
        let resources = find(conn,
            "SELECT id, name, kind, path, url, category FROM resources WHERE title_matches(name, ?1) = 1 ORDER BY updated_at DESC LIMIT ?2",
            query, limit)?;
        Ok(json!({ "scripts": scripts, "articles": articles, "tasks": [], "customers": customers,
            "customer_projects": customer_projects, "resources": resources, "passwords": [] }))
    }).await
}
