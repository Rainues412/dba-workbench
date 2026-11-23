use rusqlite::{Connection, Result};
use serde::Serialize;
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, Workspace};

const STATS_SQL: &str = include_str!("../../server/backend/queries/dashboard/stats.sql");
const TASKS_SQL: &str = include_str!("../../server/backend/queries/dashboard/recent_tasks.sql");
const DISTRIBUTION_SQL: &str =
    include_str!("../../server/backend/queries/dashboard/database_distribution.sql");

#[derive(Serialize)]
pub struct Stats {
    script_count: u64,
    article_count: u64,
    task_total: u64,
    task_pending: u64,
    task_overdue: u64,
    customer_count: u64,
    resource_count: u64,
    password_count: u64,
}

#[derive(Serialize)]
pub struct RecentTask {
    id: i64,
    title: String,
    priority: Option<String>,
    status: String,
    due_date: Option<String>,
    revision: i64,
    is_overdue: i64,
}

#[derive(Serialize)]
pub struct DatabaseCount {
    name: String,
    count: u64,
}

fn read_stats(connection: &Connection) -> Result<Stats> {
    connection.query_row(STATS_SQL, [], |row| {
        Ok(Stats {
            script_count: row.get("script_count")?,
            article_count: row.get("article_count")?,
            task_total: row.get("task_total")?,
            task_pending: row.get("task_pending")?,
            task_overdue: row.get("task_overdue")?,
            customer_count: row.get("customer_count")?,
            resource_count: row.get("resource_count")?,
            password_count: row.get("password_count")?,
        })
    })
}

fn read_recent_tasks(connection: &Connection) -> Result<Vec<RecentTask>> {
    let mut statement = connection.prepare(TASKS_SQL)?;
    let rows = statement.query_map([], |row| {
        Ok(RecentTask {
            id: row.get("id")?,
            title: row.get("title")?,
            priority: row.get("priority")?,
            status: row.get("status")?,
            due_date: row.get("due_date")?,
            revision: row.get("revision")?,
            is_overdue: row.get("is_overdue")?,
        })
    })?;
    rows.collect()
}

fn read_distribution(connection: &Connection) -> Result<Vec<DatabaseCount>> {
    let mut statement = connection.prepare(DISTRIBUTION_SQL)?;
    let rows = statement.query_map([], |row| {
        Ok(DatabaseCount {
            name: row.get("name")?,
            count: row.get("count")?,
        })
    })?;
    rows.collect()
}

#[tauri::command]
pub async fn dashboard_stats(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> desktop_db::Result<Stats> {
    desktop_db::read(window, &workspace, |conn| Ok(read_stats(conn)?)).await
}

#[tauri::command]
pub async fn dashboard_recent_tasks(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> desktop_db::Result<Vec<RecentTask>> {
    desktop_db::read(window, &workspace, |conn| Ok(read_recent_tasks(conn)?)).await
}

#[tauri::command]
pub async fn dashboard_database_distribution(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> desktop_db::Result<Vec<DatabaseCount>> {
    desktop_db::read(window, &workspace, |conn| Ok(read_distribution(conn)?)).await
}
