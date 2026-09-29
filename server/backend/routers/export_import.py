"""Export/Import API - Data backup and restore."""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend.database import get_db_ctx

logger = logging.getLogger(__name__)
router = APIRouter()


class ImportData(BaseModel):
    data: dict


@router.get("/all")
def export_all():
    """Export all data as JSON."""
    with get_db_ctx() as conn:
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "version": "0.2",
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
    return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=dba_workspace_backup.json"})


# 列定义：每张表需要导出的列，以及哪些是外键需要重映射
_TABLE_COLS = {
    "customers":       {"cols": ["name", "project_name", "group_name", "status", "notes"], "fk": {}},
    "scripts":         {"cols": ["title", "description", "db_type", "tags", "content", "file_path", "is_favorite", "version"], "fk": {}},
    "articles":        {"cols": ["title", "summary", "content", "category", "tags", "file_path", "is_favorite", "is_pinned"], "fk": {}},
    "tasks":           {"cols": ["title", "description", "status", "priority", "due_date"], "fk": {"customer_id": "customers"}},
    "contacts":        {"cols": ["name", "role", "phone", "wechat", "notes"], "fk": {"customer_id": "customers"}},
    "communications":  {"cols": ["date", "content", "follow_up"], "fk": {"customer_id": "customers"}},
    "script_versions": {"cols": ["content", "version"], "fk": {"script_id": "scripts"}},
    "resources":       {"cols": ["name", "kind", "path", "url", "version", "size_mb", "category", "tags", "notes", "is_favorite"], "fk": {}},
    "passwords":       {"cols": ["site_name", "site_url", "username", "password_enc", "category", "notes", "is_favorite"], "fk": {}},
}

# 导入顺序：父表在前，子表在后
_TABLE_ORDER = ["customers", "scripts", "articles", "tasks", "contacts", "communications",
                "script_versions", "resources", "passwords"]


def _coerce(value, col_name):
    """将 JSON 中的值转换为适合 SQLite 的类型。"""
    if value is None:
        return None
    # 数值列
    if col_name in ("size_mb",):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    if col_name in ("version", "is_favorite", "is_pinned"):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    if col_name.endswith("_id"):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    return value


@router.post("/import")
def import_data(payload: ImportData):
    """Import data from a JSON backup with id remapping and error reporting."""
    data = payload.data
    counts = {}
    errors = []
    # 记录 old_id -> new_id 的映射，用于外键重映射
    id_maps = {}  # table_name -> {old_id: new_id}

    with get_db_ctx() as conn:
        for table in _TABLE_ORDER:
            rows = data.get(table, [])
            if not rows:
                continue

            meta = _TABLE_COLS.get(table, {})
            cols = meta["cols"]
            fk_map = meta.get("fk", {})
            # 外键列需要加到插入列中
            fk_cols = list(fk_map.keys())
            all_cols = cols + fk_cols
            id_maps[table] = {}

            placeholders = ", ".join(["?"] * len(all_cols))
            col_names = ", ".join(all_cols)
            inserted = 0

            for row in rows:
                old_id = row.get("id")
                # 构造值列表
                values = []
                for c in cols:
                    values.append(_coerce(row.get(c), c))
                # 外键列：用 id_map 重映射
                for fk_col in fk_cols:
                    ref_table = fk_map[fk_col]
                    ref_old_id = row.get(fk_col)
                    if ref_old_id is not None and ref_table in id_maps:
                        new_fk_id = id_maps[ref_table].get(ref_old_id)
                        values.append(new_fk_id)
                    else:
                        values.append(_coerce(ref_old_id, fk_col))

                try:
                    cur = conn.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)
                    new_id = cur.lastrowid
                    if old_id is not None:
                        id_maps[table][old_id] = new_id
                    inserted += 1
                except Exception as e:
                    errors.append({"table": table, "row_id": old_id, "error": str(e)})
                    logger.warning("Import row failed: table=%s id=%s error=%s", table, old_id, e)

            conn.commit()
            counts[table] = inserted

        # Rebuild FTS
        try:
            conn.execute("INSERT INTO scripts_fts(scripts_fts) VALUES('rebuild')")
            conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
            conn.commit()
        except Exception as e:
            logger.warning("FTS rebuild failed: %s", e)
            errors.append({"table": "_fts", "error": str(e)})

    return {"ok": True, "imported": counts, "errors": errors}
