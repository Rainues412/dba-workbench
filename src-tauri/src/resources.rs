use rusqlite::{params, params_from_iter, types::Value as SqlValue, Connection};
use serde::Deserialize;
use serde_json::{json, Value};
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, query_rows, CommandError, Result, Workspace};
use crate::search::register_title_matching;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ResourceFilter {
    page: i64,
    page_size: i64,
    keyword: String,
    kind: String,
    category: String,
    tag: String,
    wb_db: String,
    favorite_only: bool,
}

const WHERE: &str = "WHERE (?1 = '' OR title_matches(name, ?1)) AND (?2 = '' OR kind = ?2)
    AND (?3 = '' OR category = ?3) AND (?4 = '' OR tags LIKE '%' || ?4 || '%')
    AND (?5 = '' OR wb_db = ?5) AND (NOT ?6 OR is_favorite = 1)";

fn list(conn: &Connection, filter: ResourceFilter) -> Result<Value> {
    register_title_matching(conn)?;
    let page = filter.page.max(1);
    let page_size = filter.page_size.clamp(1, 200);
    let offset = (page - 1).saturating_mul(page_size);
    let keyword = filter.keyword.trim();
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM resources {WHERE}"),
        params![
            keyword,
            filter.kind,
            filter.category,
            filter.tag,
            filter.wb_db,
            filter.favorite_only
        ],
        |row| row.get(0),
    )?;
    let items = query_rows(
        conn,
        &format!(
            "SELECT id, name, kind, path, url, version, size_mb, category, tags,
         is_favorite, wb_db, created_at, updated_at, revision FROM resources {WHERE}
         ORDER BY is_favorite DESC, updated_at DESC, id DESC LIMIT ?7 OFFSET ?8"
        ),
        params![
            keyword,
            filter.kind,
            filter.category,
            filter.tag,
            filter.wb_db,
            filter.favorite_only,
            page_size,
            offset
        ],
    )?;
    let mut statement = conn.prepare(
        "SELECT DISTINCT category FROM resources WHERE category != '' ORDER BY category",
    )?;
    let categories = statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let pages = total.div_euclid(page_size) + i64::from(total % page_size != 0);
    Ok(
        json!({ "total": total, "items": items, "page": page, "page_size": page_size, "pages": pages,
        "has_next": page < pages, "has_previous": page > 1 && pages > 0, "categories": categories }),
    )
}

fn detail(conn: &Connection, id: i64) -> Result<Value> {
    query_rows(conn, "SELECT * FROM resources WHERE id = ?1", [id])?
        .pop()
        .ok_or_else(|| CommandError::new(404, "Resource not found"))
}

#[derive(Deserialize)]
pub struct ResourceInput {
    name: Option<String>,
    kind: Option<String>,
    path: Option<String>,
    url: Option<String>,
    version: Option<String>,
    size_mb: Option<f64>,
    category: Option<String>,
    tags: Option<String>,
    notes: Option<String>,
    wb_db: Option<String>,
    is_favorite: Option<i64>,
}

fn create(conn: &Connection, input: ResourceInput) -> Result<Value> {
    let name = input
        .name
        .ok_or_else(|| CommandError::new(422, "资源名称必填"))?;
    conn.execute(
        "INSERT INTO resources (name, kind, path, url, version, size_mb, category, tags, notes, wb_db)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
        params![name, input.kind.as_deref().unwrap_or("安装包"), input.path.unwrap_or_default(),
            input.url.unwrap_or_default(), input.version.unwrap_or_default(), input.size_mb.unwrap_or_default(),
            input.category.unwrap_or_default(), input.tags.unwrap_or_default(), input.notes.unwrap_or_default(),
            input.wb_db.as_deref().unwrap_or("通用")],
    )?;
    detail(conn, conn.last_insert_rowid())
}

fn expect_revision(revision: i64) -> Result<()> {
    if revision < 1 {
        return Err(CommandError::new(
            400,
            "If-Match must contain a positive revision",
        ));
    }
    Ok(())
}

fn require_changed(conn: &Connection, id: i64, changed: usize) -> Result<()> {
    if changed == 1 {
        return Ok(());
    }
    let exists = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM resources WHERE id = ?1)",
        [id],
        |row| row.get::<_, bool>(0),
    )?;
    if exists {
        Err(CommandError::new(
            409,
            "Record was changed by another client",
        ))
    } else {
        Err(CommandError::new(404, "Record not found"))
    }
}

fn update(conn: &Connection, id: i64, revision: i64, input: ResourceInput) -> Result<Value> {
    expect_revision(revision)?;
    let edits = [
        ("name", input.name.map(SqlValue::Text)),
        ("kind", input.kind.map(SqlValue::Text)),
        ("path", input.path.map(SqlValue::Text)),
        ("url", input.url.map(SqlValue::Text)),
        ("version", input.version.map(SqlValue::Text)),
        ("size_mb", input.size_mb.map(SqlValue::Real)),
        ("category", input.category.map(SqlValue::Text)),
        ("tags", input.tags.map(SqlValue::Text)),
        ("notes", input.notes.map(SqlValue::Text)),
        ("wb_db", input.wb_db.map(SqlValue::Text)),
        ("is_favorite", input.is_favorite.map(SqlValue::Integer)),
    ];
    let (columns, values): (Vec<_>, Vec<_>) = edits
        .into_iter()
        .filter_map(|(column, value)| value.map(|value| (format!("{column} = ?"), value)))
        .unzip();
    if !columns.is_empty() {
        let changed = conn.execute(
            &format!(
                "UPDATE resources SET {}, updated_at = CURRENT_TIMESTAMP, revision = revision + 1
                 WHERE id = ? AND revision = ?",
                columns.join(", ")
            ),
            params_from_iter(
                values
                    .into_iter()
                    .chain([SqlValue::Integer(id), SqlValue::Integer(revision)]),
            ),
        )?;
        require_changed(conn, id, changed)?;
    }
    detail(conn, id)
}

#[tauri::command]
pub async fn resources_list(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    filter: ResourceFilter,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| list(conn, filter)).await
}

#[tauri::command]
pub async fn resources_facets(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> Result<Value> {
    desktop_db::read(window, &workspace, |conn| {
        let items = query_rows(
            conn,
            "SELECT wb_db, kind, COUNT(*) AS count FROM resources GROUP BY wb_db, kind",
            [],
        )?;
        let total: i64 = items.iter().filter_map(|row| row["count"].as_i64()).sum();
        Ok(json!({ "total": total, "items": items }))
    })
    .await
}

#[tauri::command]
pub async fn resources_detail(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| detail(conn, id)).await
}

#[tauri::command]
pub async fn resources_create(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    input: ResourceInput,
    csrf_token: String,
) -> Result<Value> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "post",
        "resources",
        None,
        move |conn| create(conn, input),
    )
    .await
}

#[tauri::command]
pub async fn resources_update(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
    revision: i64,
    input: ResourceInput,
    csrf_token: String,
) -> Result<Value> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "put",
        "resources",
        Some(id),
        move |conn| update(conn, id, revision, input),
    )
    .await
}

#[tauri::command]
pub async fn resources_delete(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
    revision: i64,
    csrf_token: String,
) -> Result<()> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "delete",
        "resources",
        Some(id),
        move |conn| {
            expect_revision(revision)?;
            let changed = conn.execute(
                "DELETE FROM resources WHERE id = ?1 AND revision = ?2",
                params![id, revision],
            )?;
            require_changed(conn, id, changed)
        },
    )
    .await
}
