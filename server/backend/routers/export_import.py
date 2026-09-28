"""Export/Import API - Data backup and restore."""
import json
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend.database import get_db

router = APIRouter()


class ImportData(BaseModel):
    data: dict


@router.get("/all")
def export_all():
    """Export all data as JSON."""
    conn = get_db()
    data = {
        "exported_at": datetime.now().isoformat(),
        "version": "0.1",
        "scripts": [dict(r) for r in conn.execute("SELECT * FROM scripts ORDER BY id").fetchall()],
        "script_versions": [dict(r) for r in conn.execute("SELECT * FROM script_versions ORDER BY id").fetchall()],
        "articles": [dict(r) for r in conn.execute("SELECT * FROM articles ORDER BY id").fetchall()],
        "tasks": [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()],
        "customers": [dict(r) for r in conn.execute("SELECT * FROM customers ORDER BY id").fetchall()],
        "contacts": [dict(r) for r in conn.execute("SELECT * FROM contacts ORDER BY id").fetchall()],
        "communications": [dict(r) for r in conn.execute("SELECT * FROM communications ORDER BY id").fetchall()],
        "resources": [dict(r) for r in conn.execute("SELECT * FROM resources ORDER BY id").fetchall()],
        # passwords export keeps ciphertext only; key file must be copied separately
        "passwords": [dict(r) for r in conn.execute("SELECT * FROM passwords ORDER BY id").fetchall()],
    }
    conn.close()
    return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=dba_workspace_backup.json"})


@router.post("/import")
def import_data(payload: ImportData):
    """Import data from a JSON backup (merge or replace)."""
    conn = get_db()
    data = payload.data
    counts = {}

    # Order matters: customers before contacts/communications, scripts before versions
    table_order = ["customers", "scripts", "articles", "tasks", "contacts", "communications",
                   "script_versions", "resources", "passwords"]
    table_columns = {
        "scripts": ["title", "description", "db_type", "tags", "content", "file_path", "is_favorite", "version"],
        "script_versions": ["script_id", "content", "version"],
        "articles": ["title", "summary", "content", "category", "tags", "file_path", "is_favorite", "is_pinned"],
        "tasks": ["title", "description", "status", "priority", "due_date", "customer_id"],
        "customers": ["name", "project_name", "group_name", "status", "notes"],
        "contacts": ["customer_id", "name", "role", "phone", "wechat", "notes"],
        "communications": ["customer_id", "date", "content", "follow_up"],
        "resources": ["name", "kind", "path", "url", "version", "size_mb", "category", "tags", "notes", "is_favorite"],
        # ciphertext passthrough - only decryptable with the same .workspace_secret key
        "passwords": ["site_name", "site_url", "username", "password_enc", "category", "notes", "is_favorite"],
    }

    for table in table_order:
        rows = data.get(table, [])
        if not rows:
            continue
        cols = table_columns.get(table, [])
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        inserted = 0
        for row in rows:
            values = [row.get(c, "") for c in cols]
            try:
                conn.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)
                inserted += 1
            except Exception:
                pass
        conn.commit()
        counts[table] = inserted

    # Rebuild FTS
    try:
        conn.execute("INSERT INTO scripts_fts(scripts_fts) VALUES('rebuild')")
        conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        pass

    conn.close()
    return {"ok": True, "imported": counts}
