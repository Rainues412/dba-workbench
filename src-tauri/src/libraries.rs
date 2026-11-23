use rusqlite::{params, params_from_iter, types::Value as SqlValue, Connection, OptionalExtension};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, expected_revision, query_rows, CommandError, Result, Workspace};
use crate::search::register_title_matching;

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Library {
    Scripts,
    Articles,
}

impl Library {
    fn table(self) -> &'static str {
        match self {
            Self::Scripts => "scripts",
            Self::Articles => "articles",
        }
    }

    fn headings(self) -> (&'static str, &'static str, &'static str) {
        match self {
            Self::Scripts => (
                "db_type",
                "wb_type",
                "id, title, description, db_type, wb_type, tags, file_path,
                is_favorite, created_at, updated_at, version, revision",
            ),
            Self::Articles => (
                "wb_db",
                "category",
                "id, title, summary, category, tags, file_path, wb_db,
                is_favorite, is_pinned, view_count, created_at, updated_at, revision",
            ),
        }
    }

    fn defaults(self) -> &'static [(&'static str, &'static str)] {
        match self {
            Self::Scripts => &[
                ("description", ""),
                ("db_type", "通用"),
                ("tags", ""),
                ("content", ""),
                ("file_path", ""),
                ("wb_type", "其他"),
            ],
            Self::Articles => &[
                ("summary", ""),
                ("content", ""),
                ("category", "待确认"),
                ("tags", ""),
                ("file_path", ""),
                ("wb_db", "通用"),
            ],
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Filter {
    page: i64,
    page_size: i64,
    keyword: String,
    database: String,
    category: String,
    tag: String,
    favorite_only: bool,
    locate_id: Option<i64>,
    auto_pin: bool,
}

fn list(conn: &Connection, library: Library, user_id: i64, filter: Filter) -> Result<Value> {
    register_title_matching(conn)?;
    let table = library.table();
    let (database, category, columns) = library.headings();
    let keyword = filter.keyword.trim();
    let order = match library {
        Library::Scripts if filter.auto_pin && keyword.is_empty() => "CASE WHEN id IN (
            SELECT script_id FROM script_usage WHERE user_id = ?6 AND viewed_at >= datetime('now', '-30 days')
            GROUP BY script_id HAVING COUNT(*) >= 3
            ORDER BY COUNT(*) DESC, MAX(viewed_at) DESC, script_id DESC LIMIT 5
        ) THEN 0 ELSE 1 END, updated_at DESC, id DESC",
        Library::Scripts => "updated_at DESC, id DESC",
        Library::Articles => "is_pinned DESC, updated_at DESC, id DESC",
    };
    let conditions = format!(
        "WHERE (?1 = '' OR title_matches(title, ?1))
        AND (?2 = '' OR {database} = ?2) AND (?3 = '' OR {category} = ?3)
        AND (?4 = '' OR tags LIKE '%' || ?4 || '%') AND (NOT ?5 OR is_favorite = 1)"
    );
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM {table} {conditions}"),
        params![
            keyword,
            filter.database,
            filter.category,
            filter.tag,
            filter.favorite_only
        ],
        |row| row.get(0),
    )?;
    let page_size = filter.page_size.clamp(1, 200);
    let mut page = filter.page.max(1);
    if let Some(id) = filter.locate_id {
        let position: Option<i64> = conn
            .query_row(
                &format!(
            "SELECT position FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY {order}) AS position
             FROM {table} {conditions}) WHERE id = ?7"
        ),
                params![
                    keyword,
                    filter.database,
                    filter.category,
                    filter.tag,
                    filter.favorite_only,
                    user_id,
                    id
                ],
                |row| row.get(0),
            )
            .optional()?;
        if let Some(position) = position {
            page = (position - 1) / page_size + 1;
        }
    }
    let items = query_rows(
        conn,
        &format!(
            "SELECT {columns} FROM {table} {conditions}
        ORDER BY {order} LIMIT ?7 OFFSET ?8"
        ),
        params![
            keyword,
            filter.database,
            filter.category,
            filter.tag,
            filter.favorite_only,
            user_id,
            page_size,
            (page - 1).saturating_mul(page_size)
        ],
    )?;
    let pages = total.div_euclid(page_size) + i64::from(total % page_size != 0);
    Ok(
        json!({ "total": total, "items": items, "page": page, "page_size": page_size, "pages": pages,
        "has_next": page < pages, "has_previous": page > 1 && pages > 0 }),
    )
}

fn record(conn: &Connection, library: Library, id: i64) -> Result<Value> {
    query_rows(
        conn,
        &format!("SELECT * FROM {} WHERE id = ?1", library.table()),
        [id],
    )?
    .pop()
    .ok_or_else(|| CommandError::new(404, "Record not found"))
}

fn text<'a>(input: &'a Map<String, Value>, field: &str) -> Result<Option<&'a str>> {
    match input.get(field) {
        None | Some(Value::Null) => Ok(None),
        Some(value) => value
            .as_str()
            .map(Some)
            .ok_or_else(|| CommandError::new(422, format!("{field} 必须为文本"))),
    }
}

fn create(conn: &Connection, library: Library, input: Map<String, Value>) -> Result<Value> {
    let title = text(&input, "title")?.ok_or_else(|| CommandError::new(422, "标题必填"))?;
    let mut fields = vec!["title"];
    let mut values = vec![title];
    for (field, default) in library.defaults() {
        fields.push(field);
        values.push(text(&input, field)?.unwrap_or(default));
    }
    let placeholders = vec!["?"; fields.len()].join(", ");
    conn.execute(
        &format!(
            "INSERT INTO {} ({}) VALUES ({placeholders})",
            library.table(),
            fields.join(", ")
        ),
        params_from_iter(values),
    )?;
    record(conn, library, conn.last_insert_rowid())
}

fn update(
    conn: &Connection,
    library: Library,
    id: i64,
    revision: i64,
    input: Map<String, Value>,
) -> Result<Value> {
    expected_revision(revision)?;
    let old = record(conn, library, id)?;
    let mut fields = Vec::new();
    let mut values = Vec::new();
    for field in std::iter::once("title").chain(library.defaults().iter().map(|(name, _)| *name)) {
        if let Some(value) = text(&input, field)? {
            fields.push(format!("{field} = ?"));
            values.push(SqlValue::Text(value.into()));
        }
    }
    let flags: &[&str] = match library {
        Library::Scripts => &["is_favorite"],
        Library::Articles => &["is_favorite", "is_pinned"],
    };
    for field in flags {
        if let Some(value) = input.get(*field).filter(|value| !value.is_null()) {
            let number = value
                .as_i64()
                .ok_or_else(|| CommandError::new(422, format!("{field} 必须为整数")))?;
            fields.push(format!("{field} = ?"));
            values.push(SqlValue::Integer(number));
        }
    }
    if fields.is_empty() {
        return Ok(old);
    }
    if old["revision"].as_i64() != Some(revision) {
        return Err(CommandError::new(
            409,
            "Record was changed by another client",
        ));
    }
    if matches!(library, Library::Scripts) {
        if text(&input, "content")?.is_some_and(|content| old["content"].as_str() != Some(content))
        {
            let version = old["version"]
                .as_i64()
                .ok_or_else(|| CommandError::new(500, "脚本版本号无效"))?;
            conn.execute(
                "INSERT INTO script_versions (script_id, content, version) VALUES (?1, ?2, ?3)",
                params![id, old["content"].as_str(), version],
            )?;
            fields.push("version = version + 1".into());
        }
    }
    values.extend([SqlValue::Integer(id), SqlValue::Integer(revision)]);
    conn.execute(
        &format!(
            "UPDATE {} SET {}, updated_at = CURRENT_TIMESTAMP, revision = revision + 1
        WHERE id = ? AND revision = ?",
            library.table(),
            fields.join(", ")
        ),
        params_from_iter(values),
    )?;
    record(conn, library, id)
}

#[tauri::command]
pub async fn library_list(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    library: Library,
    filter: Filter,
) -> Result<Value> {
    desktop_db::read_user(window, &workspace, false, move |conn, user_id| {
        list(conn, library, user_id, filter)
    })
    .await
}

#[tauri::command]
pub async fn library_facets(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    library: Library,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| {
        let (database, category, _) = library.headings();
        let items = query_rows(
            conn,
            &format!(
                "SELECT {database}, {category}, COUNT(*) AS count FROM {}
            GROUP BY {database}, {category}",
                library.table()
            ),
            [],
        )?;
        let total: i64 = items.iter().filter_map(|row| row["count"].as_i64()).sum();
        Ok(json!({ "total": total, "items": items }))
    })
    .await
}

#[tauri::command]
pub async fn library_detail(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    library: Library,
    id: i64,
) -> Result<Value> {
    desktop_db::read_user(window, &workspace, matches!(library, Library::Articles), move |conn, _| {
        let mut item = record(conn, library, id)?;
        match library {
            Library::Scripts => item["versions"] = json!(query_rows(conn,
                "SELECT version, created_at FROM script_versions WHERE script_id = ?1 ORDER BY version DESC", [id])?),
            Library::Articles => {
                conn.execute("UPDATE articles SET view_count = view_count + 1 WHERE id = ?1", [id])?;
                item["view_count"] = json!(item["view_count"].as_i64().unwrap_or_default() + 1);
            }
        }
        Ok(item)
    }).await
}

#[tauri::command]
pub async fn library_create(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    library: Library,
    input: Map<String, Value>,
    csrf_token: String,
) -> Result<Value> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "post",
        library.table(),
        None,
        move |conn| create(conn, library, input),
    )
    .await
}

#[tauri::command]
pub async fn library_update(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    library: Library,
    id: i64,
    revision: i64,
    input: Map<String, Value>,
    csrf_token: String,
) -> Result<Value> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "put",
        library.table(),
        Some(id),
        move |conn| update(conn, library, id, revision, input),
    )
    .await
}

#[tauri::command]
pub async fn library_delete(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    library: Library,
    id: i64,
    revision: i64,
    csrf_token: String,
) -> Result<()> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "delete",
        library.table(),
        Some(id),
        move |conn| {
            expected_revision(revision)?;
            let old = record(conn, library, id)?;
            if old["revision"].as_i64() != Some(revision) {
                return Err(CommandError::new(
                    409,
                    "Record was changed by another client",
                ));
            }
            conn.execute(
                &format!(
                    "DELETE FROM {} WHERE id = ?1 AND revision = ?2",
                    library.table()
                ),
                params![id, revision],
            )?;
            Ok(())
        },
    )
    .await
}

#[tauri::command]
pub async fn script_version(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
    version: i64,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| query_rows(conn,
        "SELECT version, content, created_at FROM script_versions WHERE script_id = ?1 AND version = ?2 ORDER BY id DESC LIMIT 1",
        params![id, version])?.pop().ok_or_else(|| CommandError::new(404, "Script version not found"))).await
}

#[tauri::command]
pub async fn script_recent_views(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> Result<Value> {
    desktop_db::read_user(window, &workspace, false, |conn, user_id| {
        Ok(json!(query_rows(
            conn,
            "SELECT scripts.id, scripts.title, MAX(script_usage.viewed_at) AS viewed_at
         FROM script_usage JOIN scripts ON scripts.id = script_usage.script_id
         WHERE script_usage.user_id = ?1 AND script_usage.viewed_at >= datetime('now', '-30 days')
         GROUP BY scripts.id ORDER BY viewed_at DESC, MAX(script_usage.id) DESC LIMIT 5",
            [user_id]
        )?))
    })
    .await
}

#[tauri::command]
pub async fn script_record_view(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
    csrf_token: String,
) -> Result<()> {
    desktop_db::write_user(window, &workspace, csrf_token, "post", "scripts", Some(id), move |conn, user_id| {
        let changed = conn.execute("INSERT INTO script_usage(user_id, script_id) SELECT ?1, id FROM scripts WHERE id = ?2", params![user_id, id])?;
        if changed == 0 { return Err(CommandError::new(404, "Script not found")); }
        conn.execute("DELETE FROM script_usage WHERE user_id = ?1 AND viewed_at < datetime('now', '-30 days')", [user_id])?;
        Ok(())
    }).await
}
