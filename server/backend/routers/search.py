"""Search API - Global search across all modules."""
from fastapi import APIRouter
from backend.database import get_db

router = APIRouter()


@router.get("/")
def global_search(q: str = "", limit: int = 10):
    """Search across scripts, articles, tasks, customers, resources, passwords."""
    if not q.strip():
        return {"scripts": [], "articles": [], "tasks": [], "customers": [], "resources": [], "passwords": []}

    conn = get_db()
    kw = f"%{q}%"

    # Scripts: search title, description, and content
    scripts = [dict(r) for r in conn.execute(
        "SELECT id, title, description, db_type, tags FROM scripts "
        "WHERE title LIKE ? OR description LIKE ? OR content LIKE ? "
        "ORDER BY updated_at DESC LIMIT ?",
        (kw, kw, kw, limit),
    ).fetchall()]

    # Articles: search title, summary, and content
    articles = [dict(r) for r in conn.execute(
        "SELECT id, title, summary, category, tags FROM articles "
        "WHERE title LIKE ? OR summary LIKE ? OR content LIKE ? "
        "ORDER BY updated_at DESC LIMIT ?",
        (kw, kw, kw, limit),
    ).fetchall()]

    # Tasks
    tasks = [dict(r) for r in conn.execute(
        "SELECT id, title, status, priority, due_date FROM tasks "
        "WHERE title LIKE ? OR description LIKE ? "
        "ORDER BY updated_at DESC LIMIT ?",
        (kw, kw, limit),
    ).fetchall()]

    # Customers
    customers = [dict(r) for r in conn.execute(
        "SELECT id, name, project_name, group_name, status FROM customers "
        "WHERE name LIKE ? OR project_name LIKE ? OR group_name LIKE ? "
        "ORDER BY updated_at DESC LIMIT ?",
        (kw, kw, kw, limit),
    ).fetchall()]

    # Resources (toolbox)
    resources = [dict(r) for r in conn.execute(
        "SELECT id, name, kind, path, url, category FROM resources "
        "WHERE name LIKE ? OR path LIKE ? OR url LIKE ? OR notes LIKE ? OR tags LIKE ? "
        "ORDER BY updated_at DESC LIMIT ?",
        (kw, kw, kw, kw, kw, limit),
    ).fetchall()]

    # Passwords (names/urls only - never passwords)
    passwords = [dict(r) for r in conn.execute(
        "SELECT id, site_name, site_url, username, category FROM passwords "
        "WHERE site_name LIKE ? OR site_url LIKE ? OR username LIKE ? "
        "ORDER BY updated_at DESC LIMIT ?",
        (kw, kw, kw, limit),
    ).fetchall()]

    conn.close()
    return {"scripts": scripts, "articles": articles, "tasks": tasks,
            "customers": customers, "resources": resources, "passwords": passwords}
