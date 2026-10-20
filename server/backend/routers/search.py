"""Search API - Global search across all modules."""
from fastapi import APIRouter
from backend.database import get_db_ctx

router = APIRouter()


@router.get("/")
def global_search(q: str = "", limit: int = 10):
    """Search non-secret modules; vault search is performed client-side after unlock."""
    if not q.strip():
        return {"scripts": [], "articles": [], "tasks": [], "customers": [], "resources": [], "passwords": []}

    # limit=0 is used by the inline search dropdown to return every local match.
    limit = -1 if limit == 0 else max(1, min(limit, 100))

    with get_db_ctx() as conn:
        query = q.strip()

        # Search each module's primary display title only.
        scripts = [dict(r) for r in conn.execute(
            "SELECT id, title, description, db_type, tags FROM scripts WHERE title_matches(title, ?) = 1 "
            "ORDER BY updated_at DESC LIMIT ?",
            (query, limit),
        ).fetchall()]

        articles = [dict(r) for r in conn.execute(
            "SELECT id, title, summary, category, tags FROM articles WHERE title_matches(title, ?) = 1 "
            "ORDER BY updated_at DESC LIMIT ?",
            (query, limit),
        ).fetchall()]

        # Customers
        customers = [dict(r) for r in conn.execute(
            "SELECT id, name, project_name, group_name, status FROM customers WHERE title_matches(name, ?) = 1 "
            "ORDER BY updated_at DESC LIMIT ?",
            (query, limit),
        ).fetchall()]

        # Resources (toolbox)
        resources = [dict(r) for r in conn.execute(
            "SELECT id, name, kind, path, url, category FROM resources WHERE title_matches(name, ?) = 1 "
            "ORDER BY updated_at DESC LIMIT ?",
            (query, limit),
        ).fetchall()]

    return {"scripts": scripts, "articles": articles, "tasks": [],
            "customers": customers, "resources": resources, "passwords": []}
