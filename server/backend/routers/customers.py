"""Customers API - customers, contacts (project owners), communication logs."""
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db_ctx, validate_page

router = APIRouter()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CustomerCreate(BaseModel):
    name: str
    project_name: str = ""
    group_name: str = ""
    status: str = "活跃"
    notes: str = ""
    wb_person: str = ""
    wb_contact: str = ""


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    project_name: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    wb_person: Optional[str] = None
    wb_contact: Optional[str] = None


class ContactCreate(BaseModel):
    name: str
    role: str = ""
    phone: str = ""
    wechat: str = ""
    notes: str = ""


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    wechat: Optional[str] = None
    notes: Optional[str] = None


class CommCreate(BaseModel):
    date: str
    content: str
    follow_up: str = ""


@router.get("/")
def list_customers(keyword: str = "", status: str = "", page: int = 1, page_size: int = 50):
    with get_db_ctx() as conn:
        conditions, params = [], []
        if keyword:
            conditions.append("(c.name LIKE ? OR c.project_name LIKE ? OR c.group_name LIKE ? OR c.notes LIKE ?)")
            params.extend([f"%{keyword}%"] * 4)
        if status:
            conditions.append("c.status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM customers c {where}", params).fetchone()[0]
        offset, ps = validate_page(page, page_size)
        rows = conn.execute(
            f"""SELECT c.*,
                       (SELECT COUNT(*) FROM contacts ct WHERE ct.customer_id = c.id) AS contact_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.customer_id = c.id AND t.status != '已完成') AS open_task_count
                FROM customers c {where}
                ORDER BY c.updated_at DESC
                LIMIT ? OFFSET ?""",
            params + [ps, offset],
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows], "page": page, "page_size": ps}


@router.post("/")
def create_customer(data: CustomerCreate):
    with get_db_ctx() as conn:
        c = conn.execute(
            "INSERT INTO customers (name, project_name, group_name, status, notes, wb_person, wb_contact) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.name, data.project_name, data.group_name, data.status, data.notes, data.wb_person, data.wb_contact),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (c.lastrowid,)).fetchone()
        return dict(row)


@router.get("/{cid}")
def get_customer(cid: int):
    with get_db_ctx() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "Customer not found")
        contacts = [dict(r) for r in conn.execute(
            "SELECT * FROM contacts WHERE customer_id = ? ORDER BY id", (cid,)).fetchall()]
        comms = [dict(r) for r in conn.execute(
            "SELECT * FROM communications WHERE customer_id = ? ORDER BY date DESC, id DESC LIMIT 50", (cid,)).fetchall()]
        tasks = [dict(r) for r in conn.execute(
            """SELECT id, title, status, priority, due_date,
                      CASE WHEN status != '已完成' AND due_date IS NOT NULL AND due_date < date('now')
                      THEN 1 ELSE 0 END AS is_overdue
               FROM tasks WHERE customer_id = ? ORDER BY status != '已完成' DESC, due_date ASC""",
            (cid,)).fetchall()]
        result = dict(row)
        result["contacts"] = contacts
        result["communications"] = comms
        result["tasks"] = tasks
        return result


@router.put("/{cid}")
def update_customer(cid: int, data: CustomerUpdate):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM customers WHERE id = ?", (cid,)).fetchone():
            raise HTTPException(404, "Customer not found")
        updates, params = [], []
        for field in ["name", "project_name", "group_name", "status", "notes", "wb_person", "wb_contact"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(cid)
            conn.execute(f"UPDATE customers SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        return dict(row)


@router.delete("/{cid}")
def delete_customer(cid: int):
    """Delete a customer and all related contacts/communications (cascade)."""
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM customers WHERE id = ?", (cid,)).fetchone():
            raise HTTPException(404, "Customer not found")
        # 显式清理子表，确保 FK 完整性（PRAGMA foreign_keys 已开启，CASCADE 也会生效）
        conn.execute("DELETE FROM communications WHERE customer_id = ?", (cid,))
        conn.execute("DELETE FROM contacts WHERE customer_id = ?", (cid,))
        conn.execute("UPDATE tasks SET customer_id = NULL WHERE customer_id = ?", (cid,))
        conn.execute("DELETE FROM customers WHERE id = ?", (cid,))
        conn.commit()
        return {"ok": True}


# ── Contacts ──

@router.post("/{cid}/contacts")
def add_contact(cid: int, data: ContactCreate):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM customers WHERE id = ?", (cid,)).fetchone():
            raise HTTPException(404, "Customer not found")
        c = conn.execute(
            "INSERT INTO contacts (customer_id, name, role, phone, wechat, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, data.name, data.role, data.phone, data.wechat, data.notes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (c.lastrowid,)).fetchone()
        return dict(row)


@router.put("/contacts/{contact_id}")
def update_contact(contact_id: int, data: ContactUpdate):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone():
            raise HTTPException(404, "Contact not found")
        updates, params = [], []
        for field in ["name", "role", "phone", "wechat", "notes"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if updates:
            params.append(contact_id)
            conn.execute(f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return dict(row)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone():
            raise HTTPException(404, "Contact not found")
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        return {"ok": True}


# ── Communications ──

@router.post("/{cid}/communications")
def add_comm(cid: int, data: CommCreate):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM customers WHERE id = ?", (cid,)).fetchone():
            raise HTTPException(404, "Customer not found")
        if not _DATE_RE.match(data.date):
            raise HTTPException(400, "日期格式须为 YYYY-MM-DD")
        c = conn.execute(
            "INSERT INTO communications (customer_id, date, content, follow_up) VALUES (?, ?, ?, ?)",
            (cid, data.date, data.content, data.follow_up),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM communications WHERE id = ?", (c.lastrowid,)).fetchone()
        return dict(row)


@router.delete("/communications/{comm_id}")
def delete_comm(comm_id: int):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM communications WHERE id = ?", (comm_id,)).fetchone():
            raise HTTPException(404, "Communication record not found")
        conn.execute("DELETE FROM communications WHERE id = ?", (comm_id,))
        conn.commit()
        return {"ok": True}
