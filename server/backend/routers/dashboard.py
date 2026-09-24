"""Dashboard API - statistics and overview."""
from fastapi import APIRouter
from backend.database import get_db

router = APIRouter()


@router.get("/stats")
def get_stats():
    """Get counts for all modules."""
    conn = get_db()
    stats = {
        "script_count": conn.execute("SELECT COUNT(*) FROM scripts").fetchone()[0],
        "article_count": conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "task_total": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        "task_pending": conn.execute("SELECT COUNT(*) FROM tasks WHERE status != '已完成'").fetchone()[0],
        "task_overdue": conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != '已完成' AND due_date < date('now') AND due_date IS NOT NULL"
        ).fetchone()[0],
        "customer_count": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "resource_count": conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        "password_count": conn.execute("SELECT COUNT(*) FROM passwords").fetchone()[0],
    }
    conn.close()
    return stats


@router.get("/recent-tasks")
def get_recent_tasks():
    """Get pending/in-progress tasks, overdue first."""
    conn = get_db()
    rows = conn.execute("""
        SELECT *, CASE WHEN status != '已完成' AND due_date IS NOT NULL AND due_date < date('now')
                  THEN 1 ELSE 0 END AS is_overdue
        FROM tasks WHERE status != '已完成'
        ORDER BY is_overdue DESC,
                 CASE priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 END,
                 due_date ASC NULLS LAST
        LIMIT 10
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/favorite-scripts")
def get_favorite_scripts():
    """Get favorited scripts."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, db_type, tags FROM scripts WHERE is_favorite = 1 ORDER BY updated_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/recent-articles")
def get_recent_articles():
    """Get recently updated articles."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, category, updated_at FROM articles ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
