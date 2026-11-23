use rusqlite::{params, Connection, OptionalExtension, Row};
use serde::{Deserialize, Serialize};
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, CommandError, Result, Workspace};
use crate::search::register_title_matching;

const ARCHIVED: &str = "CASE WHEN t.status = '已完成' AND julianday(t.completed_at) <= julianday('now', '-15 days') THEN 1 ELSE 0 END";
const OVERDUE: &str = "t.status != '已完成' AND date(t.due_date) < date('now', 'localtime')";
const TASK_COLUMNS: &str = "t.id, t.title, t.description, t.status, t.priority, t.due_date,
    t.customer_id, t.created_at, t.updated_at, t.completed_at, t.revision";
const TASK_ORDER: &str = "is_overdue DESC,
    CASE WHEN t.status = '已完成' THEN 1 ELSE 0 END,
    CASE WHEN t.status != '已完成' THEN CASE t.priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 ELSE 4 END END,
    CASE t.status WHEN '进行中' THEN 0 WHEN '待处理' THEN 1 WHEN '已完成' THEN 2 ELSE 3 END,
    CASE WHEN t.status = '已完成' THEN julianday(t.created_at) END DESC,
    CASE WHEN t.status != '已完成' THEN date(t.due_date) END ASC NULLS LAST, t.id DESC";

#[derive(Serialize)]
pub struct Task {
    id: i64,
    title: String,
    description: Option<String>,
    status: Option<String>,
    priority: Option<String>,
    due_date: Option<String>,
    customer_id: Option<i64>,
    created_at: Option<String>,
    updated_at: Option<String>,
    completed_at: Option<String>,
    revision: i64,
    customer_name: Option<String>,
    is_archived: i64,
    is_overdue: i64,
}

fn task_row(row: &Row<'_>) -> rusqlite::Result<Task> {
    Ok(Task {
        id: row.get("id")?,
        title: row.get("title")?,
        description: row.get("description")?,
        status: row.get("status")?,
        priority: row.get("priority")?,
        due_date: row.get("due_date")?,
        customer_id: row.get("customer_id")?,
        created_at: row.get("created_at")?,
        updated_at: row.get("updated_at")?,
        completed_at: row.get("completed_at")?,
        revision: row.get("revision")?,
        customer_name: row.get("customer_name")?,
        is_archived: row.get("is_archived")?,
        is_overdue: row.get("is_overdue")?,
    })
}

fn task_select() -> String {
    format!(
        "SELECT {TASK_COLUMNS}, c.name AS customer_name, {ARCHIVED} AS is_archived,
        CASE WHEN {OVERDUE} THEN 1 ELSE 0 END AS is_overdue
        FROM tasks t LEFT JOIN customers c ON t.customer_id = c.id"
    )
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskFilter {
    page: i64,
    page_size: i64,
    keyword: String,
    status: String,
    priority: String,
    overdue: bool,
    archived: bool,
}

#[derive(Serialize)]
pub struct TaskPage {
    total: i64,
    items: Vec<Task>,
    page: i64,
    page_size: i64,
    pages: i64,
    has_next: bool,
    has_previous: bool,
}

fn list(conn: &Connection, filter: TaskFilter) -> Result<TaskPage> {
    register_title_matching(conn)?;
    let page = filter.page.max(1);
    let page_size = filter.page_size.clamp(1, 200);
    let offset = (page - 1).saturating_mul(page_size);
    let keyword = filter.keyword.trim();
    let conditions = format!(
        "WHERE ({ARCHIVED}) = ?1 AND (?2 = '' OR t.status = ?2)
        AND (?3 = '' OR t.priority = ?3) AND (NOT ?4 OR ({OVERDUE}))
        AND (?5 = '' OR title_matches(t.title, ?5))"
    );
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM tasks t {conditions}"),
        params![
            filter.archived,
            filter.status,
            filter.priority,
            filter.overdue,
            keyword
        ],
        |row| row.get(0),
    )?;
    let mut statement = conn.prepare(&format!(
        "{} {conditions} ORDER BY {TASK_ORDER} LIMIT ?6 OFFSET ?7",
        task_select()
    ))?;
    let items = statement
        .query_map(
            params![
                filter.archived,
                filter.status,
                filter.priority,
                filter.overdue,
                keyword,
                page_size,
                offset
            ],
            task_row,
        )?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let pages = total.div_euclid(page_size) + i64::from(total % page_size != 0);
    Ok(TaskPage {
        total,
        items,
        page,
        page_size,
        pages,
        has_next: page < pages,
        has_previous: page > 1 && pages > 0,
    })
}

fn detail(conn: &Connection, id: i64) -> Result<Task> {
    conn.query_row(
        &format!("{} WHERE t.id = ?1", task_select()),
        [id],
        task_row,
    )
    .optional()?
    .ok_or_else(|| CommandError::new(404, "Task not found"))
}

#[derive(Default, Deserialize)]
pub struct TaskInput {
    title: Option<String>,
    description: Option<String>,
    status: Option<String>,
    priority: Option<String>,
    due_date: Option<String>,
    customer_id: Option<i64>,
}

fn validate_customer(conn: &Connection, id: Option<i64>) -> Result<()> {
    if let Some(id) = id {
        let exists = conn.query_row(
            "SELECT EXISTS(SELECT 1 FROM customers WHERE id = ?1)",
            [id],
            |row| row.get::<_, bool>(0),
        )?;
        if !exists {
            return Err(CommandError::new(400, format!("客户不存在: {id}")));
        }
    }
    Ok(())
}

fn create(conn: &Connection, input: TaskInput) -> Result<Task> {
    let title = input
        .title
        .ok_or_else(|| CommandError::new(422, "任务名称必填"))?;
    validate_customer(conn, input.customer_id)?;
    conn.execute(
        "INSERT INTO tasks (title, description, status, priority, due_date, customer_id, completed_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, CASE WHEN ?3 = '已完成' THEN CURRENT_TIMESTAMP END)",
        params![title, input.description.unwrap_or_default(), input.status.as_deref().unwrap_or("待处理"),
            input.priority.as_deref().unwrap_or("中"), input.due_date, input.customer_id],
    )?;
    detail(conn, conn.last_insert_rowid())
}

fn expected_revision(revision: i64) -> Result<()> {
    if revision < 1 {
        return Err(CommandError::new(
            400,
            "If-Match must contain a positive revision",
        ));
    }
    Ok(())
}

fn check_changed(conn: &Connection, id: i64, changed: usize) -> Result<()> {
    if changed == 1 {
        return Ok(());
    }
    let exists = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM tasks WHERE id = ?1)",
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

fn update(conn: &Connection, id: i64, revision: i64, input: TaskInput) -> Result<Task> {
    expected_revision(revision)?;
    validate_customer(conn, input.customer_id)?;
    // The HTTP API treats null fields as omitted for existing records.
    if input.title.is_none()
        && input.description.is_none()
        && input.status.is_none()
        && input.priority.is_none()
        && input.due_date.is_none()
        && input.customer_id.is_none()
    {
        return detail(conn, id);
    }
    let changed = conn.execute(
        "UPDATE tasks SET title = COALESCE(?3, title), description = COALESCE(?4, description),
         status = COALESCE(?5, status), priority = COALESCE(?6, priority),
         due_date = COALESCE(?7, due_date), customer_id = COALESCE(?8, customer_id),
         completed_at = CASE WHEN ?5 IS NULL THEN completed_at
                             WHEN ?5 != '已完成' THEN NULL
                             WHEN status = '已完成' THEN COALESCE(completed_at, CURRENT_TIMESTAMP)
                             ELSE CURRENT_TIMESTAMP END,
         updated_at = CURRENT_TIMESTAMP, revision = revision + 1 WHERE id = ?1 AND revision = ?2",
        params![
            id,
            revision,
            input.title,
            input.description,
            input.status,
            input.priority,
            input.due_date,
            input.customer_id
        ],
    )?;
    check_changed(conn, id, changed)?;
    detail(conn, id)
}

#[tauri::command]
pub async fn tasks_list(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    filter: TaskFilter,
) -> Result<TaskPage> {
    desktop_db::read(window, &workspace, move |conn| list(conn, filter)).await
}

#[tauri::command]
pub async fn tasks_detail(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
) -> Result<Task> {
    desktop_db::read(window, &workspace, move |conn| detail(conn, id)).await
}

#[tauri::command]
pub async fn tasks_create(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    input: TaskInput,
    csrf_token: String,
) -> Result<Task> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "post",
        "tasks",
        None,
        move |conn| create(conn, input),
    )
    .await
}

#[tauri::command]
pub async fn tasks_update(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
    revision: i64,
    input: TaskInput,
    csrf_token: String,
) -> Result<Task> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "put",
        "tasks",
        Some(id),
        move |conn| update(conn, id, revision, input),
    )
    .await
}

#[tauri::command]
pub async fn tasks_delete(
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
        "tasks",
        Some(id),
        move |conn| {
            expected_revision(revision)?;
            let changed = conn.execute(
                "DELETE FROM tasks WHERE id = ?1 AND revision = ?2",
                params![id, revision],
            )?;
            check_changed(conn, id, changed)
        },
    )
    .await
}
