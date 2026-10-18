"""Small helpers for HTTP optimistic concurrency control."""

from fastapi import HTTPException


def expected_revision(if_match: str | None) -> int:
    """Parse a strong integer ETag used by update and delete operations."""
    if if_match is None:
        raise HTTPException(428, "If-Match revision is required")
    value = if_match.strip().strip('"')
    if not value.isdigit() or int(value) < 1:
        raise HTTPException(400, "If-Match must contain a positive revision")
    return int(value)


def raise_write_conflict(conn, table: str, record_id: int) -> None:
    if conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)).fetchone():
        raise HTTPException(409, "Record was changed by another client")
    raise HTTPException(404, "Record not found")
