use rusqlite::{params, params_from_iter, types::Value as SqlValue, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::{State, WebviewWindow};

use crate::desktop_db::{self, expected_revision, query_rows, CommandError, Result, Workspace};
use crate::search::{register_title_matching, title_matches};

pub const PROJECT_ROWS: &str = "json_each(CASE WHEN c.project_profile IS NULL
    THEN json_array(json_object('name', c.project_name))
    ELSE json_extract(c.project_profile, '$.projects') END) AS project";
pub const PROJECT_NAME: &str = "json_extract(project.value, '$.name')";

#[derive(Default, Deserialize, Serialize)]
#[serde(default)]
struct Chat {
    name: String,
    platform: String,
}

#[derive(Deserialize, Serialize)]
struct Owner {
    name: String,
    #[serde(default)]
    label: String,
}

#[derive(Deserialize, Serialize)]
struct Project {
    name: String,
    #[serde(default)]
    chat: Chat,
    #[serde(default)]
    owners: Vec<Owner>,
}

#[derive(Default, Deserialize, Serialize)]
#[serde(default)]
struct Profile {
    chat: Chat,
    owners: Vec<Owner>,
    projects: Vec<Project>,
}

fn project_profile(record: &Value) -> Result<Profile> {
    if let Some(stored) = record["project_profile"].as_str() {
        return serde_json::from_str(stored)
            .map_err(|_| CommandError::new(500, "客户项目资料格式无效。"));
    }
    let text = |key| record[key].as_str().unwrap_or_default().to_owned();
    let name = text("project_name");
    let person = text("wb_person");
    let chat = Chat {
        name: text("group_name"),
        platform: text("wb_contact"),
    };
    let owners = if person.trim().is_empty() {
        vec![]
    } else {
        vec![Owner {
            name: person,
            label: String::new(),
        }]
    };
    if name.trim().is_empty() {
        Ok(Profile {
            chat,
            owners,
            projects: vec![],
        })
    } else {
        Ok(Profile {
            projects: vec![Project { name, chat, owners }],
            ..Profile::default()
        })
    }
}

fn project_record(mut record: Value, keyword: &str) -> Result<Value> {
    let profile = project_profile(&record)?;
    if !keyword.is_empty() {
        let matches: Vec<&str> = profile
            .projects
            .iter()
            .filter(|project| title_matches(&project.name, keyword))
            .map(|project| project.name.as_str())
            .collect();
        record["matched_projects"] = json!(matches);
    }
    record["project_profile"] = json!(profile);
    Ok(record)
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Filter {
    page: i64,
    page_size: i64,
    keyword: String,
    status: String,
    locate_id: Option<i64>,
}

fn list(conn: &Connection, filter: Filter) -> Result<Value> {
    register_title_matching(conn)?;
    let keyword = filter.keyword.trim();
    let conditions = format!(
        "WHERE (?1 = '' OR title_matches(c.name, ?1) OR EXISTS (
        SELECT 1 FROM {PROJECT_ROWS} WHERE title_matches({PROJECT_NAME}, ?1)
    )) AND (?2 = '' OR c.status = ?2)"
    );
    let order = "c.name COLLATE NOCASE ASC, c.id DESC";
    let page_size = filter.page_size.clamp(1, 200);
    let mut page = filter.page.max(1);
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM customers c {conditions}"),
        params![keyword, filter.status],
        |row| row.get(0),
    )?;
    if let Some(id) = filter.locate_id {
        let position: Option<i64> = conn.query_row(&format!("SELECT position FROM (
            SELECT c.id, ROW_NUMBER() OVER (ORDER BY {order}) AS position FROM customers c {conditions}
        ) WHERE id = ?3"), params![keyword, filter.status, id], |row| row.get(0)).optional()?;
        if let Some(position) = position {
            page = (position - 1) / page_size + 1;
        }
    }
    let items = query_rows(
        conn,
        &format!(
            "SELECT c.id, c.name, c.project_name, c.group_name, c.status,
        c.wb_person, c.wb_contact, c.created_at, c.updated_at, c.revision, c.project_profile
        FROM customers c {conditions} ORDER BY {order} LIMIT ?3 OFFSET ?4"
        ),
        params![
            keyword,
            filter.status,
            page_size,
            (page - 1).saturating_mul(page_size)
        ],
    )?
    .into_iter()
    .map(|item| project_record(item, keyword))
    .collect::<Result<Vec<_>>>()?;
    let pages = total.div_euclid(page_size) + i64::from(total % page_size != 0);
    Ok(
        json!({ "total": total, "items": items, "page": page, "page_size": page_size, "pages": pages,
        "has_previous": page > 1 && pages > 0, "has_next": page < pages }),
    )
}

fn record(conn: &Connection, id: i64) -> Result<Value> {
    query_rows(conn, "SELECT * FROM customers WHERE id = ?1", [id])?
        .pop()
        .ok_or_else(|| CommandError::new(404, "Customer not found"))
}

#[derive(Deserialize)]
pub struct Input {
    name: Option<String>,
    project_name: Option<String>,
    group_name: Option<String>,
    status: Option<String>,
    notes: Option<String>,
    wb_person: Option<String>,
    wb_contact: Option<String>,
    project_profile: Option<Profile>,
}

fn profile_json(profile: Option<Profile>) -> Result<Option<String>> {
    let Some(profile) = profile else {
        return Ok(None);
    };
    if profile
        .projects
        .iter()
        .any(|project| project.name.trim().is_empty())
        || profile
            .owners
            .iter()
            .chain(profile.projects.iter().flat_map(|project| &project.owners))
            .any(|owner| owner.name.trim().is_empty())
    {
        return Err(CommandError::new(422, "项目及负责人的名称不能为空。"));
    }
    let value = serde_json::to_string(&profile)
        .map_err(|_| CommandError::new(500, "客户项目资料格式无效。"))?;
    Ok(Some(value))
}

fn ensure_name(conn: &Connection, id: i64, name: &str) -> Result<()> {
    if name.trim().is_empty() {
        return Err(CommandError::new(400, "请填写客户名"));
    }
    let used = conn.query_row("SELECT EXISTS(SELECT 1 FROM customers WHERE id != ?1 AND TRIM(name) = TRIM(?2) COLLATE NOCASE)",
        params![id, name], |row| row.get::<_, bool>(0))?;
    if used {
        return Err(CommandError::new(409, "该客户已存在，请在原客户下新增项目"));
    }
    Ok(())
}

fn create(conn: &Connection, input: Input) -> Result<Value> {
    let name = input
        .name
        .ok_or_else(|| CommandError::new(422, "客户名必填"))?;
    let profile = profile_json(input.project_profile)?;
    if profile.is_some() {
        ensure_name(conn, 0, &name)?;
    }
    conn.execute("INSERT INTO customers (name, project_name, group_name, status, notes, wb_person, wb_contact, project_profile)
                  VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![name, input.project_name.unwrap_or_default(), input.group_name.unwrap_or_default(),
            input.status.as_deref().unwrap_or("活跃"), input.notes.unwrap_or_default(),
            input.wb_person.unwrap_or_default(), input.wb_contact.unwrap_or_default(), profile])?;
    project_record(record(conn, conn.last_insert_rowid())?, "")
}

fn update(conn: &Connection, id: i64, revision: i64, input: Input) -> Result<Value> {
    expected_revision(revision)?;
    let old = record(conn, id)?;
    let profile = profile_json(input.project_profile)?;
    if let Some(name) = input
        .name
        .as_deref()
        .filter(|name| profile.is_some() && old["name"].as_str() != Some(name))
    {
        check_revision(&old, revision)?;
        ensure_name(conn, id, name)?;
    }
    let edits = [
        ("name", input.name),
        ("project_name", input.project_name),
        ("group_name", input.group_name),
        ("status", input.status),
        ("notes", input.notes),
        ("wb_person", input.wb_person),
        ("wb_contact", input.wb_contact),
        ("project_profile", profile),
    ];
    let (fields, values): (Vec<_>, Vec<_>) = edits
        .iter()
        .filter_map(|(field, value)| {
            value
                .as_ref()
                .map(|value| (format!("{field} = ?"), SqlValue::Text(value.clone())))
        })
        .unzip();
    if fields.is_empty() {
        return project_record(old, "");
    }
    check_revision(&old, revision)?;
    conn.execute(
        &format!(
            "UPDATE customers SET {}, updated_at = CURRENT_TIMESTAMP, revision = revision + 1
        WHERE id = ? AND revision = ?",
            fields.join(", ")
        ),
        params_from_iter(
            values
                .into_iter()
                .chain([SqlValue::Integer(id), SqlValue::Integer(revision)]),
        ),
    )?;
    project_record(record(conn, id)?, "")
}

fn check_revision(item: &Value, revision: i64) -> Result<()> {
    if item["revision"].as_i64() != Some(revision) {
        return Err(CommandError::new(
            409,
            "Record was changed by another client",
        ));
    }
    Ok(())
}

#[tauri::command]
pub async fn customers_list(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    filter: Filter,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| list(conn, filter)).await
}

#[tauri::command]
pub async fn customers_detail(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
) -> Result<Value> {
    desktop_db::read(window, &workspace, move |conn| {
        let mut item = project_record(record(conn, id)?, "")?;
        item["contacts"] = json!(query_rows(
            conn,
            "SELECT * FROM contacts WHERE customer_id = ?1 ORDER BY id",
            [id]
        )?);
        Ok(item)
    })
    .await
}

#[tauri::command]
pub async fn customers_create(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    input: Input,
    csrf_token: String,
) -> Result<Value> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "post",
        "customers",
        None,
        move |conn| create(conn, input),
    )
    .await
}

#[tauri::command]
pub async fn customers_update(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
    id: i64,
    revision: i64,
    input: Input,
    csrf_token: String,
) -> Result<Value> {
    desktop_db::write(
        window,
        &workspace,
        csrf_token,
        "put",
        "customers",
        Some(id),
        move |conn| update(conn, id, revision, input),
    )
    .await
}

#[tauri::command]
pub async fn customers_delete(
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
        "customers",
        Some(id),
        move |conn| {
            expected_revision(revision)?;
            check_revision(&record(conn, id)?, revision)?;
            conn.execute("DELETE FROM communications WHERE customer_id = ?1", [id])?;
            conn.execute("DELETE FROM contacts WHERE customer_id = ?1", [id])?;
            conn.execute(
                "UPDATE tasks SET customer_id = NULL WHERE customer_id = ?1",
                [id],
            )?;
            conn.execute(
                "DELETE FROM customers WHERE id = ?1 AND revision = ?2",
                params![id, revision],
            )?;
            Ok(())
        },
    )
    .await
}
