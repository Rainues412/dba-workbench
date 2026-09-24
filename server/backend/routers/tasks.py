"""Tasks API - CRUD operations for the task list."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db

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


@router.get("/")
def list_tasks(
    status: str = "",
    priority: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
):
    """List tasks with filtering and pagination."""
    conn = get_db()
    conditions = []
    params = []

    if status:
        conditions.append("t.status = ?")
        params.append(status)
    if priority:
        conditions.append("t.priority = ?")
        params.append(priority)
    if keyword:
        conditions.append("(t.title LIKE ? OR t.description LIKE ?)")
        params.extend([f"%{keyword}%"] * 2)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    total = conn.execute(f"SELECT COUNT(*) FROM tasks t {where}", params).fetchone()[0]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""SELECT t.*, c.name AS customer_name,
                   CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
                   THEN 1 ELSE 0 END AS is_overdue
            FROM tasks t
            LEFT JOIN customers c ON t.customer_id = c.id
            {where}
            ORDER BY
                CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
                     THEN 0 ELSE 1 END,
                CASE t.status WHEN '进行中' THEN 0 WHEN '待处理' THEN 1 WHEN '已完成' THEN 2 END,
                CASE t.priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 END,
                t.due_date ASC NULLS LAST
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    conn.close()
    return {"total": total, "items": [dict(r) for r in rows], "page": page, "page_size": page_size}


@router.post("/")
def create_task(data: TaskCreate):
    """Create a new task."""
    conn = get_db()
    c = conn.execute(
        "INSERT INTO tasks (title, description, priority, due_date, customer_id, status) VALUES (?, ?, ?, ?, ?, ?)",
        (data.title, data.description, data.priority, data.due_date, data.customer_id, data.status),
    )
    conn.commit()
    task_id = c.lastrowid
    row = conn.execute("""
        SELECT t.*, c.name AS customer_name,
               CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
               THEN 1 ELSE 0 END AS is_overdue
        FROM tasks t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.id = ?
    """, (task_id,)).fetchone()
    conn.close()
    return dict(row)


@router.get("/{task_id}")
def get_task(task_id: int):
    """Get a single task."""
    conn = get_db()
    row = conn.execute("""
        SELECT t.*, c.name AS customer_name,
               CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
               THEN 1 ELSE 0 END AS is_overdue
        FROM tasks t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.id = ?
    """, (task_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Task not found")
    conn.close()
    return dict(row)


@router.put("/{task_id}")
def update_task(task_id: int, data: TaskUpdate):
    """Update a task."""
    conn = get_db()
    if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Task not found")

    updates = []
    params = []
    for field in ["title", "description", "status", "priority", "due_date", "customer_id"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = ?")
            params.append(val)
            # Auto-set completed_at when status changes to 已完成
            if field == "status" and val == "已完成":
                updates.append("completed_at = datetime('now')")

    if updates:
        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    row = conn.execute("""
        SELECT t.*, c.name AS customer_name,
               CASE WHEN t.status != '已完成' AND t.due_date IS NOT NULL AND t.due_date < date('now')
               THEN 1 ELSE 0 END AS is_overdue
        FROM tasks t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.id = ?
    """, (task_id,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("/{task_id}")
def delete_task(task_id: int):
    """Delete a task."""
    conn = get_db()
    if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Task not found")
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/{task_id}/toggle-status")
def toggle_status(task_id: int):
    """Cycle task status: 待处理 → 进行中 → 已完成 → 待处理."""
    conn = get_db()
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Task not found")

    cycle = {"待处理": "进行中", "进行中": "已完成", "已完成": "待处理"}
    new_status = cycle.get(row["status"], "待处理")
    completed_at = "datetime('now')" if new_status == "已完成" else "NULL"
    conn.execute(
        f"UPDATE tasks SET status = ?, completed_at = {completed_at} WHERE id = ?",
        (new_status, task_id),
    )
    conn.commit()
    conn.close()
    return {"status": new_status}
