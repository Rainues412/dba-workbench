"""Dashboard API - statistics and overview."""
from pathlib import Path

from fastapi import APIRouter
from backend.database import get_db_ctx

router = APIRouter()

_QUERY_DIR = Path(__file__).resolve().parents[1] / "queries" / "dashboard"
_STATS_SQL = (_QUERY_DIR / "stats.sql").read_text(encoding="utf-8")
_RECENT_TASKS_SQL = (_QUERY_DIR / "recent_tasks.sql").read_text(encoding="utf-8")
_DATABASE_DISTRIBUTION_SQL = (_QUERY_DIR / "database_distribution.sql").read_text(encoding="utf-8")


@router.get("/stats")
def get_stats():
    """Get counts for all modules (single query with subselects)."""
    with get_db_ctx() as conn:
        row = conn.execute(_STATS_SQL).fetchone()
        return dict(row)


@router.get("/recent-tasks")
def get_recent_tasks():
    """Get unfinished tasks by overdue, priority, status, then deadline."""
    with get_db_ctx() as conn:
        rows = conn.execute(_RECENT_TASKS_SQL).fetchall()
        return [dict(r) for r in rows]


@router.get("/database-distribution")
def get_database_distribution():
    """Count scripts and articles using the database groups from the legacy dashboard."""
    with get_db_ctx() as conn:
        rows = conn.execute(_DATABASE_DISTRIBUTION_SQL).fetchall()
        return [dict(row) for row in rows]
