"""Customers API for customer and project profiles."""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db_ctx, page_response, validate_page
from backend.concurrency import expected_revision, raise_write_conflict
from backend.customer_projects import CUSTOMER_PROJECT_NAME, CUSTOMER_PROJECT_ROWS, ProjectProfile, customer_record
from backend.search_utils import title_matches

router = APIRouter()

class CustomerCreate(BaseModel):
    name: str
    project_name: str = ""
    group_name: str = ""
    status: str = "活跃"
    notes: str = ""
    wb_person: str = ""
    wb_contact: str = ""
    project_profile: ProjectProfile | None = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    project_name: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    wb_person: Optional[str] = None
    wb_contact: Optional[str] = None
    project_profile: ProjectProfile | None = None


def ensure_customer_name_available(conn, name: str, current_id: int = 0) -> None:
    if not name.strip():
        raise HTTPException(400, "请填写客户名")
    if conn.execute(
        "SELECT 1 FROM customers WHERE id != ? AND TRIM(name) = TRIM(?) COLLATE NOCASE",
        (current_id, name),
    ).fetchone():
        raise HTTPException(409, "该客户已存在，请在原客户下新增项目")


@router.get("/")
def list_customers(keyword: str = "", status: str = "", page: int = 1, page_size: int = 50, locate_id: int | None = None):
    with get_db_ctx() as conn:
        conditions, params = [], {}
        keyword = keyword.strip()
        if keyword:
            conditions.append(f"""(title_matches(c.name, :keyword) = 1 OR EXISTS (
                SELECT 1 FROM {CUSTOMER_PROJECT_ROWS}
                WHERE title_matches({CUSTOMER_PROJECT_NAME}, :keyword) = 1
            ))""")
            params["keyword"] = keyword
        if status:
            conditions.append("c.status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM customers c {where}", params).fetchone()[0]
        offset, ps = validate_page(page, page_size)
        order_by = "c.name COLLATE NOCASE ASC, c.id DESC"
        if locate_id is not None:
            position = conn.execute(
                f"""SELECT position FROM (
                    SELECT c.id, ROW_NUMBER() OVER (ORDER BY {order_by}) AS position
                    FROM customers c {where}
                ) WHERE id = :locate_id""",
                {**params, "locate_id": locate_id},
            ).fetchone()
            if position:
                page = (position[0] - 1) // ps + 1
                offset = (page - 1) * ps
        rows = conn.execute(
            f"""SELECT c.id, c.name, c.project_name, c.group_name, c.status,
                       c.wb_person, c.wb_contact, c.created_at, c.updated_at, c.revision, c.project_profile
                FROM customers c {where}
                ORDER BY {order_by}
                LIMIT :page_size OFFSET :offset""",
            {**params, "page_size": ps, "offset": offset},
        ).fetchall()
        records = [customer_record(row) for row in rows]
        if keyword:
            for record in records:
                record["matched_projects"] = [
                    project["name"] for project in record["project_profile"]["projects"]
                    if title_matches(project["name"], keyword)
                ]
        return page_response(total, records, page, ps)


@router.post("/")
def create_customer(data: CustomerCreate):
    with get_db_ctx() as conn:
        if data.project_profile is not None:
            conn.execute("BEGIN IMMEDIATE")
            ensure_customer_name_available(conn, data.name)
        c = conn.execute(
            """INSERT INTO customers (name, project_name, group_name, status, notes, wb_person, wb_contact, project_profile)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data.name, data.project_name, data.group_name, data.status, data.notes, data.wb_person, data.wb_contact,
             data.project_profile.model_dump_json() if data.project_profile is not None else None),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (c.lastrowid,)).fetchone()
        return customer_record(row)


@router.get("/{cid}")
def get_customer(cid: int):
    with get_db_ctx() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "Customer not found")
        contacts = [dict(r) for r in conn.execute(
            "SELECT * FROM contacts WHERE customer_id = ? ORDER BY id", (cid,)).fetchall()]
        result = customer_record(row)
        result["contacts"] = contacts
        return result


@router.put("/{cid}")
def update_customer(cid: int, data: CustomerUpdate, if_match: str | None = Header(None)):
    with get_db_ctx() as conn:
        expected = expected_revision(if_match)
        if data.project_profile is not None and data.name is not None:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT name, revision FROM customers WHERE id = ?", (cid,)).fetchone()
            if current is None or current["revision"] != expected:
                raise_write_conflict(conn, "customers", cid)
            if current["name"] != data.name:
                ensure_customer_name_available(conn, data.name, cid)
        updates, params = [], []
        for field in ["name", "project_name", "group_name", "status", "notes", "wb_person", "wb_contact"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if data.project_profile is not None:
            updates.append("project_profile = ?")
            params.append(data.project_profile.model_dump_json())
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            updates.append("revision = revision + 1")
            params.extend([cid, expected])
            changed = conn.execute(
                f"UPDATE customers SET {', '.join(updates)} WHERE id = ? AND revision = ?",
                params,
            )
            if changed.rowcount != 1:
                raise_write_conflict(conn, "customers", cid)
            conn.commit()
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "Customer not found")
        return customer_record(row)


@router.delete("/{cid}")
def delete_customer(cid: int, if_match: str | None = Header(None)):
    """Delete a customer and all related contacts/communications (cascade)."""
    with get_db_ctx() as conn:
        expected = expected_revision(if_match)
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT revision FROM customers WHERE id = ?", (cid,)).fetchone()
        if not current:
            raise HTTPException(404, "Customer not found")
        if current["revision"] != expected:
            raise HTTPException(409, "Record was changed by another client")
        # 显式清理子表，确保 FK 完整性（PRAGMA foreign_keys 已开启，CASCADE 也会生效）
        conn.execute("DELETE FROM communications WHERE customer_id = ?", (cid,))
        conn.execute("DELETE FROM contacts WHERE customer_id = ?", (cid,))
        conn.execute("UPDATE tasks SET customer_id = NULL WHERE customer_id = ?", (cid,))
        conn.execute("DELETE FROM customers WHERE id = ? AND revision = ?", (cid, expected))
        conn.commit()
        return {"ok": True}
