"""Resources API - toolbox: installers, software, local files, URLs (index only)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db_ctx, validate_page

router = APIRouter()

KINDS = ["安装包", "软件工具", "驱动/固件", "文档资料", "脚本工具", "网址", "其他"]


class ResourceCreate(BaseModel):
    name: str
    kind: str = "安装包"
    path: str = ""
    url: str = ""
    version: str = ""
    size_mb: float = 0
    category: str = ""
    tags: str = ""
    notes: str = ""


class ResourceUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    version: Optional[str] = None
    size_mb: Optional[float] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    is_favorite: Optional[int] = None


@router.get("/")
def list_resources(
    keyword: str = "",
    kind: str = "",
    category: str = "",
    tag: str = "",
    favorite_only: int = 0,
    page: int = 1,
    page_size: int = 50,
):
    with get_db_ctx() as conn:
        conditions, params = [], []
        if keyword:
            conditions.append("(name LIKE ? OR path LIKE ? OR url LIKE ? OR notes LIKE ? OR tags LIKE ?)")
            params.extend([f"%{keyword}%"] * 5)
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if favorite_only:
            conditions.append("is_favorite = 1")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM resources {where}", params).fetchone()[0]
        offset, ps = validate_page(page, page_size)
        rows = conn.execute(
            f"SELECT * FROM resources {where} ORDER BY is_favorite DESC, updated_at DESC LIMIT ? OFFSET ?",
            params + [ps, offset],
        ).fetchall()
        categories = [r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM resources WHERE category != '' ORDER BY category").fetchall()]
        return {"total": total, "items": [dict(r) for r in rows], "categories": categories,
                "page": page, "page_size": ps}


@router.post("/")
def create_resource(data: ResourceCreate):
    with get_db_ctx() as conn:
        c = conn.execute(
            """INSERT INTO resources (name, kind, path, url, version, size_mb, category, tags, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data.name, data.kind, data.path, data.url, data.version, data.size_mb,
             data.category, data.tags, data.notes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM resources WHERE id = ?", (c.lastrowid,)).fetchone()
        return dict(row)


@router.get("/kinds")
def get_kinds():
    return KINDS


@router.get("/{rid}")
def get_resource(rid: int):
    with get_db_ctx() as conn:
        row = conn.execute("SELECT * FROM resources WHERE id = ?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, "Resource not found")
        return dict(row)


@router.put("/{rid}")
def update_resource(rid: int, data: ResourceUpdate):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM resources WHERE id = ?", (rid,)).fetchone():
            raise HTTPException(404, "Resource not found")
        updates, params = [], []
        for field in ["name", "kind", "path", "url", "version", "size_mb", "category", "tags", "notes", "is_favorite"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(rid)
            conn.execute(f"UPDATE resources SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM resources WHERE id = ?", (rid,)).fetchone()
        return dict(row)


@router.delete("/{rid}")
def delete_resource(rid: int):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM resources WHERE id = ?", (rid,)).fetchone():
            raise HTTPException(404, "Resource not found")
        conn.execute("DELETE FROM resources WHERE id = ?", (rid,))
        conn.commit()
        return {"ok": True}


@router.post("/{rid}/toggle-favorite")
def toggle_favorite(rid: int):
    with get_db_ctx() as conn:
        row = conn.execute("SELECT is_favorite FROM resources WHERE id = ?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, "Resource not found")
        new_val = 0 if row["is_favorite"] else 1
        conn.execute("UPDATE resources SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_val, rid))
        conn.commit()
        return {"is_favorite": new_val}
