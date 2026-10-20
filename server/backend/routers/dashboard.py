"""Dashboard API - statistics and overview."""
from fastapi import APIRouter
from backend.database import get_db_ctx

router = APIRouter()


@router.get("/stats")
def get_stats():
    """Get counts for all modules (single query with subselects)."""
    with get_db_ctx() as conn:
        row = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM scripts) AS script_count,
                (SELECT COUNT(*) FROM articles) AS article_count,
                (SELECT COUNT(*) FROM tasks) AS task_total,
                (SELECT COUNT(*) FROM tasks WHERE status != '已完成') AS task_pending,
                (SELECT COUNT(*) FROM tasks WHERE status != '已完成' AND due_date IS NOT NULL AND due_date < date('now', 'localtime')) AS task_overdue,
                (SELECT COUNT(*) FROM customers) AS customer_count,
                (SELECT COUNT(*) FROM resources) AS resource_count,
                (SELECT COUNT(*) FROM vault_items) AS password_count
        """).fetchone()
        return dict(row)


@router.get("/recent-tasks")
def get_recent_tasks():
    """Get pending/in-progress tasks, overdue first."""
    with get_db_ctx() as conn:
        rows = conn.execute("""
            SELECT id, title, priority, status, due_date, revision,
                   CASE WHEN status != '已完成' AND due_date IS NOT NULL AND due_date < date('now', 'localtime')
                      THEN 1 ELSE 0 END AS is_overdue
            FROM tasks WHERE status != '已完成'
            ORDER BY is_overdue DESC,
                     CASE priority WHEN '高' THEN 1 WHEN '中' THEN 2 WHEN '低' THEN 3 END,
                     due_date ASC NULLS LAST
        """).fetchall()
        return [dict(r) for r in rows]


@router.get("/database-distribution")
def get_database_distribution():
    """Count scripts and articles using the database groups from the legacy dashboard."""
    with get_db_ctx() as conn:
        rows = conn.execute("""
            WITH database_types(name, sort_order) AS (
                VALUES
                    ('Oracle', 1),
                    ('MySQL', 2),
                    ('PostgreSQL', 3),
                    ('SQL Server', 4),
                    ('Linux', 5),
                    ('Redis', 6),
                    ('其他', 7)
            ),
            database_counts AS (
                SELECT
                    CASE
                        WHEN db_type IN ('Oracle', 'MySQL', 'PostgreSQL', 'SQL Server', 'Linux', 'Redis')
                        THEN db_type ELSE '其他'
                    END AS name,
                    COUNT(*) AS item_count
                FROM scripts
                GROUP BY name
                UNION ALL
                SELECT
                    CASE
                        WHEN wb_db IN ('Oracle', 'MySQL', 'PostgreSQL', 'SQL Server', 'Linux', 'Redis')
                        THEN wb_db ELSE '其他'
                    END AS name,
                    COUNT(*) AS item_count
                FROM articles
                GROUP BY name
            )
            SELECT database_types.name, COALESCE(SUM(database_counts.item_count), 0) AS count
            FROM database_types
            LEFT JOIN database_counts ON database_counts.name = database_types.name
            GROUP BY database_types.name, database_types.sort_order
            ORDER BY database_types.sort_order
        """).fetchall()
        return [dict(row) for row in rows]


@router.get("/favorite-scripts")
def get_favorite_scripts():
    """Get favorited scripts."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, title, db_type, tags FROM scripts WHERE is_favorite = 1 ORDER BY updated_at DESC LIMIT 10"
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/recent-articles")
def get_recent_articles():
    """Get recently updated articles."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, title, category, updated_at FROM articles ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        return [dict(r) for r in rows]
