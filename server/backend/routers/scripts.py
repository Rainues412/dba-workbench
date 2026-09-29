"""Scripts API - CRUD operations for the script library."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db_ctx, validate_page

router = APIRouter()


class ScriptCreate(BaseModel):
    title: str
    description: str = ""
    db_type: str = "通用"
    tags: str = ""
    content: str = ""
    file_path: str = ""
    wb_type: str = "其他"


class ScriptUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    db_type: Optional[str] = None
    tags: Optional[str] = None
    content: Optional[str] = None
    file_path: Optional[str] = None
    wb_type: Optional[str] = None
    is_favorite: Optional[int] = None


@router.get("/")
def list_scripts(
    keyword: str = "",
    db_type: str = "",
    wb_type: str = "",
    tag: str = "",
    favorite_only: int = 0,
    page: int = 1,
    page_size: int = 20,
):
    """List scripts with filtering and pagination."""
    with get_db_ctx() as conn:
        conditions = []
        params = []

        if keyword:
            conditions.append("(title LIKE ? OR description LIKE ? OR content LIKE ?)")
            params.extend([f"%{keyword}%"] * 3)
        if db_type:
            conditions.append("db_type = ?")
            params.append(db_type)
        if wb_type:
            conditions.append("wb_type = ?")
            params.append(wb_type)
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if favorite_only:
            conditions.append("is_favorite = 1")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM scripts {where}", params).fetchone()[0]

        offset, ps = validate_page(page, page_size)
        # 列表接口排除content字段，避免大文本导致JSON序列化问题
        rows = conn.execute(
            f"""SELECT id, title, description, db_type, wb_type, tags, file_path,
                       is_favorite, created_at, updated_at, version
                FROM scripts {where}
                ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
            params + [ps, offset],
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows], "page": page, "page_size": ps}


@router.post("/")
def create_script(data: ScriptCreate):
    """Create a new script."""
    with get_db_ctx() as conn:
        c = conn.execute(
            "INSERT INTO scripts (title, description, db_type, tags, content, file_path, wb_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.title, data.description, data.db_type, data.tags, data.content, data.file_path, data.wb_type),
        )
        conn.commit()
        script_id = c.lastrowid
        row = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        return dict(row)


@router.get("/{script_id}")
def get_script(script_id: int):
    """Get a single script with version history."""
    with get_db_ctx() as conn:
        row = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Script not found")
        versions = conn.execute(
            "SELECT version, created_at FROM script_versions WHERE script_id = ? ORDER BY version DESC",
            (script_id,),
        ).fetchall()
        result = dict(row)
        result["versions"] = [dict(v) for v in versions]
        return result


@router.put("/{script_id}")
def update_script(script_id: int, data: ScriptUpdate):
    """Update a script. Saves previous content as a version."""
    with get_db_ctx() as conn:
        old = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        if not old:
            raise HTTPException(404, "Script not found")

        updates = []
        params = []

        # Save version if content changed, bump version in same UPDATE
        if data.content is not None and data.content != old["content"]:
            conn.execute(
                "INSERT INTO script_versions (script_id, content, version) VALUES (?, ?, ?)",
                (script_id, old["content"], old["version"]),
            )
            updates.append("version = ?")
            params.append(old["version"] + 1)

        for field in ["title", "description", "db_type", "tags", "content", "file_path", "wb_type", "is_favorite"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(script_id)
            conn.execute(f"UPDATE scripts SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        row = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        return dict(row)


@router.delete("/{script_id}")
def delete_script(script_id: int):
    """Delete a script."""
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)).fetchone():
            raise HTTPException(404, "Script not found")
        conn.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
        conn.commit()
        return {"ok": True}


@router.post("/{script_id}/toggle-favorite")
def toggle_favorite(script_id: int):
    """Toggle favorite status."""
    with get_db_ctx() as conn:
        row = conn.execute("SELECT is_favorite FROM scripts WHERE id = ?", (script_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Script not found")
        new_val = 0 if row["is_favorite"] else 1
        conn.execute("UPDATE scripts SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_val, script_id))
        conn.commit()
        return {"is_favorite": new_val}
