"""Tasks API - CRUD operations for the task list."""
import hashlib
import json
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.database import get_db_ctx, page_response, validate_page
from backend.concurrency import expected_revision, raise_write_conflict

router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "中"
    due_date: Optional[str] = None
    customer_id: Optional[int] = None
    status: str = "待处理"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    customer_id: Optional[int] = None


class LegacyArchiveEntry(BaseModel):
    id: str | int | None = None
    title: str = Field(min_length=1, max_length=1000)
    notes: str = ""
    priority: str = "P1"
    deadline: str | None = None
    completedAt: str | None = None


class LegacyArchiveImport(BaseModel):
    items: list[LegacyArchiveEntry] = Field(min_length=1, max_length=200)


@router.post("/legacy-archive")
def import_legacy_archive(payload: LegacyArchiveImport):
    """Explicit, additive archive migration; never clears browser source data."""
    imported = skipped = 0
    with get_db_ctx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for entry in payload.items:
            key = hashlib.sha256(json.dumps(entry.model_dump(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if conn.execute("SELECT 1 FROM legacy_task_imports WHERE source_key = ?", (key,)).fetchone():
                skipped += 1
                continue
            try:
                due = datetime.strptime(entry.deadline, "%Y-%m-%d").date().isoformat() if entry.deadline else None
                completed = datetime.fromisoformat(entry.completedAt.replace("Z", "+00:00")).isoformat() if entry.completedAt else None
            except ValueError:
                raise HTTPException(422, "旧归档日期格式无效，未导入任何记录")
            priority = {"P0": "高", "P1": "中", "P2": "低", "高": "高", "中": "中", "低": "低"}.get(entry.priority)
            if priority is None:
                raise HTTPException(422, "旧归档优先级无效，未导入任何记录")
            row = conn.execute(
                "INSERT INTO tasks(title, description, priority, due_date, status, completed_at) VALUES (?, ?, ?, ?, '已完成', ?)",
                (entry.title, entry.notes, priority, due, completed),
            )
            conn.execute("INSERT INTO legacy_task_imports(source_key, task_id) VALUES (?, ?)", (key, row.lastrowid))
            imported += 1
        conn.commit()
    return {"ok": True, "imported": imported, "skipped": skipped}


_TASK_SELECT = """
    SELECT t.*, c.name AS customer_name,
           CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
           THEN 1 ELSE 0 END AS is_overdue
    FROM tasks t LEFT JOIN customers c ON t.customer_id = c.id
"""


@router.get("/")
def list_tasks(
    status: str = "",
    priority: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
):
    """List tasks with filtering and pagination."""
    with get_db_ctx() as conn:
        conditions = []
        params = []

        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if priority:
            conditions.append("t.priority = ?")
            params.append(priority)
        if keyword.strip():
            conditions.append("title_matches(t.title, ?) = 1")
            params.append(keyword.strip())

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM tasks t {where}", params).fetchone()[0]

        offset, ps = validate_page(page, page_size)
        rows = conn.execute(
            f"""{_TASK_SELECT}
            {where}
            ORDER BY
                CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
                     THEN 0 ELSE 1 END,
                CASE t.status WHEN '进行中' THEN 0 WHEN '待处理' THEN 1 WHEN '已完成' THEN 2 END,
                CASE t.priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 END,
                t.due_date ASC NULLS LAST, t.id DESC
            LIMIT ? OFFSET ?""",
            params + [ps, offset],
        ).fetchall()
        return page_response(total, rows, page, ps)


@router.post("/")
def create_task(data: TaskCreate):
    """Create a new task."""
    with get_db_ctx() as conn:
        # 验证 customer_id 存在性
        if data.customer_id is not None:
            if not conn.execute("SELECT id FROM customers WHERE id = ?", (data.customer_id,)).fetchone():
                raise HTTPException(400, f"客户不存在: {data.customer_id}")
        c = conn.execute(
            "INSERT INTO tasks (title, description, priority, due_date, customer_id, status) VALUES (?, ?, ?, ?, ?, ?)",
            (data.title, data.description, data.priority, data.due_date, data.customer_id, data.status),
        )
        conn.commit()
        task_id = c.lastrowid
        row = conn.execute(f"{_TASK_SELECT} WHERE t.id = ?", (task_id,)).fetchone()
        return dict(row)


@router.get("/{task_id}")
def get_task(task_id: int):
    """Get a single task."""
    with get_db_ctx() as conn:
        row = conn.execute(f"{_TASK_SELECT} WHERE t.id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        return dict(row)


@router.put("/{task_id}")
def update_task(task_id: int, data: TaskUpdate, if_match: str | None = Header(None)):
    """Update a task."""
    with get_db_ctx() as conn:
        expected = expected_revision(if_match)

        # 验证 customer_id 存在性
        if data.customer_id is not None:
            if not conn.execute("SELECT id FROM customers WHERE id = ?", (data.customer_id,)).fetchone():
                raise HTTPException(400, f"客户不存在: {data.customer_id}")

        updates = []
        params = []
        for field in ["title", "description", "status", "priority", "due_date", "customer_id"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
                # 状态变为已完成时记录 completed_at
                if field == "status" and val == "已完成":
                    updates.append("completed_at = datetime('now')")
                # 状态从已完成变为其他时清除 completed_at
                if field == "status" and val != "已完成":
                    updates.append("completed_at = NULL")

        if updates:
            updates.extend(["updated_at = CURRENT_TIMESTAMP", "revision = revision + 1"])
            params.extend([task_id, expected])
            changed = conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ? AND revision = ?",
                params,
            )
            if changed.rowcount != 1:
                raise_write_conflict(conn, "tasks", task_id)
            conn.commit()

        row = conn.execute(f"{_TASK_SELECT} WHERE t.id = ?", (task_id,)).fetchone()
        return dict(row)


@router.delete("/{task_id}")
def delete_task(task_id: int, if_match: str | None = Header(None)):
    """Delete a task."""
    with get_db_ctx() as conn:
        expected = expected_revision(if_match)
        changed = conn.execute(
            "DELETE FROM tasks WHERE id = ? AND revision = ?", (task_id, expected)
        )
        if changed.rowcount != 1:
            raise_write_conflict(conn, "tasks", task_id)
        conn.commit()
        return {"ok": True}


@router.post("/{task_id}/toggle-status")
def toggle_status(task_id: int, if_match: str | None = Header(None)):
    """Cycle task status: 待处理 → 进行中 → 已完成 → 待处理."""
    with get_db_ctx() as conn:
        expected = expected_revision(if_match)
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")

        cycle = {"待处理": "进行中", "进行中": "已完成", "已完成": "待处理"}
        new_status = cycle.get(row["status"], "待处理")
        # 用静态 SQL + CASE 避免 f-string 拼接
        changed = conn.execute(
            """UPDATE tasks SET status = ?,
                      completed_at = CASE WHEN ? = '已完成' THEN datetime('now') ELSE NULL END,
                      updated_at = CURRENT_TIMESTAMP, revision = revision + 1
               WHERE id = ? AND revision = ?""",
            (new_status, new_status, task_id, expected),
        )
        if changed.rowcount != 1:
            raise_write_conflict(conn, "tasks", task_id)
        conn.commit()
        return {"status": new_status, "revision": expected + 1}
