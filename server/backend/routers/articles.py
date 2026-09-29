"""Articles API - CRUD operations for the knowledge base."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db_ctx, validate_page

router = APIRouter()


class ArticleCreate(BaseModel):
    title: str
    summary: str = ""
    content: str = ""
    category: str = "学习记录"
    tags: str = ""
    file_path: str = ""
    wb_db: str = "通用"


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    file_path: Optional[str] = None
    wb_db: Optional[str] = None
    is_favorite: Optional[int] = None
    is_pinned: Optional[int] = None


@router.get("/")
def list_articles(
    keyword: str = "",
    category: str = "",
    tag: str = "",
    wb_db: str = "",
    favorite_only: int = 0,
    page: int = 1,
    page_size: int = 20,
):
    """List articles with filtering and pagination."""
    with get_db_ctx() as conn:
        conditions = []
        params = []

        if keyword:
            conditions.append("(title LIKE ? OR summary LIKE ? OR content LIKE ?)")
            params.extend([f"%{keyword}%"] * 3)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if wb_db:
            conditions.append("wb_db = ?")
            params.append(wb_db)
        if favorite_only:
            conditions.append("is_favorite = 1")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM articles {where}", params).fetchone()[0]

        offset, ps = validate_page(page, page_size)
        rows = conn.execute(
            f"""SELECT id, title, summary, category, tags, file_path, wb_db, is_favorite, is_pinned,
                       view_count, created_at, updated_at
                FROM articles {where}
                ORDER BY is_pinned DESC, updated_at DESC LIMIT ? OFFSET ?""",
            params + [ps, offset],
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows], "page": page, "page_size": ps}


@router.post("/")
def create_article(data: ArticleCreate):
    """Create a new article."""
    with get_db_ctx() as conn:
        c = conn.execute(
            "INSERT INTO articles (title, summary, content, category, tags, file_path, wb_db) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data.title, data.summary, data.content, data.category, data.tags, data.file_path, data.wb_db),
        )
        conn.commit()
        article_id = c.lastrowid
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row)


@router.get("/{article_id}")
def get_article(article_id: int):
    """Get a single article and increment view count."""
    with get_db_ctx() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Article not found")
        # 先确认存在再递增浏览数，避免对不存在的记录执行写操作
        conn.execute("UPDATE articles SET view_count = view_count + 1 WHERE id = ?", (article_id,))
        conn.commit()
        result = dict(row)
        result["view_count"] = row["view_count"] + 1  # 返回递增后的值
        return result


@router.put("/{article_id}")
def update_article(article_id: int, data: ArticleUpdate):
    """Update an article."""
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone():
            raise HTTPException(404, "Article not found")

        updates = []
        params = []
        for field in ["title", "summary", "content", "category", "tags", "file_path", "wb_db", "is_favorite", "is_pinned"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(article_id)
            conn.execute(f"UPDATE articles SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row)


@router.delete("/{article_id}")
def delete_article(article_id: int):
    """Delete an article."""
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone():
            raise HTTPException(404, "Article not found")
        conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        conn.commit()
        return {"ok": True}


@router.post("/{article_id}/toggle-favorite")
def toggle_favorite(article_id: int):
    """Toggle favorite status."""
    with get_db_ctx() as conn:
        row = conn.execute("SELECT is_favorite FROM articles WHERE id = ?", (article_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Article not found")
        new_val = 0 if row["is_favorite"] else 1
        conn.execute("UPDATE articles SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_val, article_id))
        conn.commit()
        return {"is_favorite": new_val}
