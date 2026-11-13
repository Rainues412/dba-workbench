"""Search API - Global search across all modules."""
from fastapi import APIRouter
from backend.customer_projects import CUSTOMER_PROJECT_NAME, CUSTOMER_PROJECT_ROWS
from backend.database import get_db_ctx

router = APIRouter()


@router.get("/")
def global_search(q: str = "", limit: int = 10):
    """Search non-secret modules; vault search is performed client-side after unlock."""
    if not q.strip():
        return {"scripts": [], "articles": [], "tasks": [], "customers": [], "customer_projects": [], "resources": [], "passwords": []}

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
        customer_projects = [dict(r) for r in conn.execute(
            f"""SELECT DISTINCT c.id, c.name AS customer_name, {CUSTOMER_PROJECT_NAME} AS title
                FROM customers c, {CUSTOMER_PROJECT_ROWS}
                WHERE title_matches({CUSTOMER_PROJECT_NAME}, ?) = 1
                ORDER BY c.updated_at DESC, c.id DESC, title COLLATE NOCASE
                LIMIT ?""",
            (query, limit),
        ).fetchall()]

        # Resources (toolbox)
        resources = [dict(r) for r in conn.execute(
            "SELECT id, name, kind, path, url, category FROM resources WHERE title_matches(name, ?) = 1 "
            "ORDER BY updated_at DESC LIMIT ?",
            (query, limit),
        ).fetchall()]

    return {"scripts": scripts, "articles": articles, "tasks": [],
            "customers": customers, "customer_projects": customer_projects,
            "resources": resources, "passwords": []}
