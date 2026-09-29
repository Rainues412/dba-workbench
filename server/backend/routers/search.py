"""Search API - Global search across all modules."""
from fastapi import APIRouter
from backend.database import get_db_ctx

router = APIRouter()


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符，避免用户输入中的 %/_ 被误解析。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/")
def global_search(q: str = "", limit: int = 10):
    """Search across scripts, articles, tasks, customers, resources, passwords."""
    if not q.strip():
        return {"scripts": [], "articles": [], "tasks": [], "customers": [], "resources": [], "passwords": []}

    limit = max(1, min(limit, 100))

    with get_db_ctx() as conn:
        kw = f"%{_escape_like(q)}%"

        # Scripts: search title, description, and content
        scripts = [dict(r) for r in conn.execute(
            "SELECT id, title, description, db_type, tags FROM scripts "
            "WHERE title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (kw, kw, kw, limit),
        ).fetchall()]

        # Articles: search title, summary, and content
        articles = [dict(r) for r in conn.execute(
            "SELECT id, title, summary, category, tags FROM articles "
            "WHERE title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (kw, kw, kw, limit),
        ).fetchall()]

        # Tasks
        tasks = [dict(r) for r in conn.execute(
            "SELECT id, title, status, priority, due_date FROM tasks "
            "WHERE title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (kw, kw, limit),
        ).fetchall()]

        # Customers
        customers = [dict(r) for r in conn.execute(
            "SELECT id, name, project_name, group_name, status FROM customers "
            "WHERE name LIKE ? ESCAPE '\\' OR project_name LIKE ? ESCAPE '\\' OR group_name LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (kw, kw, kw, limit),
        ).fetchall()]

        # Resources (toolbox)
        resources = [dict(r) for r in conn.execute(
            "SELECT id, name, kind, path, url, category FROM resources "
            "WHERE name LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\' OR url LIKE ? ESCAPE '\\' OR notes LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (kw, kw, kw, kw, kw, limit),
        ).fetchall()]

        # Passwords (names/urls only - never passwords)
        passwords = [dict(r) for r in conn.execute(
            "SELECT id, site_name, site_url, username, category FROM passwords "
            "WHERE site_name LIKE ? ESCAPE '\\' OR site_url LIKE ? ESCAPE '\\' OR username LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (kw, kw, kw, limit),
        ).fetchall()]

    return {"scripts": scripts, "articles": articles, "tasks": tasks,
            "customers": customers, "resources": resources, "passwords": passwords}
