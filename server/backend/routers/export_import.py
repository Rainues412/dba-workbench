"""Export/Import API - Data backup and restore."""
import logging
import sqlite3
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
        }
    return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=dba_workspace_backup.json"})


# Import business columns; identities/revisions are regenerated for appended rows.
_TABLE_COLS = {
    "customers":       {"cols": ["name", "project_name", "group_name", "status", "notes", "wb_person", "wb_contact", "created_at", "updated_at"], "fk": {}},
    "scripts":         {"cols": ["title", "description", "db_type", "tags", "content", "file_path", "is_favorite", "version", "wb_type", "created_at", "updated_at"], "fk": {}},
    "articles":        {"cols": ["title", "summary", "content", "category", "tags", "file_path", "is_favorite", "is_pinned", "wb_db", "view_count", "created_at", "updated_at"], "fk": {}},
    "tasks":           {"cols": ["title", "description", "status", "priority", "due_date", "is_overdue", "completed_at", "created_at", "updated_at"], "fk": {"customer_id": "customers"}},
    "contacts":        {"cols": ["name", "role", "phone", "wechat", "notes"], "fk": {"customer_id": "customers"}},
    "communications":  {"cols": ["date", "content", "follow_up", "created_at"], "fk": {"customer_id": "customers"}},
    "script_versions": {"cols": ["content", "version", "created_at"], "fk": {"script_id": "scripts"}},
    "resources":       {"cols": ["name", "kind", "path", "url", "version", "size_mb", "category", "tags", "notes", "is_favorite", "wb_db", "created_at", "updated_at"], "fk": {}},
}

# 导入顺序：父表在前，子表在后
_TABLE_ORDER = ["customers", "scripts", "articles", "tasks", "contacts", "communications",
                "script_versions", "resources"]


def _coerce(value, col_name, table):
    """将 JSON 中的值转换为适合 SQLite 的类型。"""
    if value is None:
        return None
    # 数值列
    if col_name == "size_mb":
        return float(value)
    # Resource versions are free-form strings, unlike script version numbers.
    if col_name in ("is_favorite", "is_pinned", "view_count", "is_overdue") or (col_name == "version" and table != "resources"):
        return int(value)
    return value


@router.post("/import")
def import_data(payload: ImportData):
    """Append a complete backup atomically; IDs/revisions are newly assigned."""
    data = payload.data
    counts = {}
    # 记录 old_id -> new_id 的映射，用于外键重映射
    id_maps = {}  # table_name -> {old_id: new_id}

    table, row_index, old_id = "backup", None, None
    with get_db_ctx() as conn:
        try:
            if not any(name in data for name in _TABLE_ORDER):
                raise ValueError("没有可识别的普通模块数据表")
            # One transaction for the entire file, never a partially restored backup.
            with conn:
                for table in _TABLE_ORDER:
                    rows = data.get(table, [])
                    row_index, old_id = None, None
                    if not isinstance(rows, list):
                        raise ValueError("数据表必须是数组")
                    meta = _TABLE_COLS[table]
                    id_maps[table] = {}
                    counts[table] = 0
                    for row_index, row in enumerate(rows, 1):
                        if not isinstance(row, dict):
                            raise ValueError("记录必须是对象")
                        old_id = row.get("id")
                        if old_id is not None:
                            if not isinstance(old_id, (str, int)) or isinstance(old_id, bool):
                                raise ValueError("记录 ID 格式无效")
                            if str(old_id) in id_maps[table]:
                                raise ValueError("备份中存在重复 ID")
                        # Omit absent fields so legacy backups receive schema defaults.
                        cols = [col for col in meta["cols"] if col in row]
                        values = [_coerce(row[col], col, table) for col in cols]
                        for fk_col, ref_table in meta["fk"].items():
                            if fk_col not in row:
                                continue
                            ref_id = row[fk_col]
                            new_id = None
                            if ref_id is not None:
                                new_id = id_maps[ref_table].get(str(ref_id))
                                if new_id is None:
                                    raise ValueError(f"{fk_col} 引用的父记录不在备份中")
                            cols.append(fk_col)
                            values.append(new_id)
                        if not cols:
                            raise ValueError("记录没有可导入字段")
                        marks = ", ".join("?" for _ in cols)
                        cur = conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})", values)
                        if table == "tasks":
                            conn.execute("UPDATE tasks SET completed_at = CURRENT_TIMESTAMP WHERE id = ? AND status = '已完成' AND (completed_at IS NULL OR julianday(completed_at) IS NULL)", (cur.lastrowid,))
                        if old_id is not None:
                            id_maps[table][str(old_id)] = cur.lastrowid
                        counts[table] += 1
        except (ValueError, TypeError, OverflowError, sqlite3.Error) as exc:
            logger.warning("Backup import rolled back: table=%s row=%s error=%s", table, row_index, exc)
            message = f"导入失败，未写入任何记录：{table} 第 {row_index or '-'} 条：{exc}"
            return JSONResponse(status_code=400, content={
                "ok": False, "mode": "append", "imported": {},
                "errors": [{"table": table, "row": row_index, "row_id": old_id, "error": str(exc)}],
                "error": {"code": "IMPORT_FAILED", "message": message},
            })

    return {"ok": True, "mode": "append", "imported": counts, "errors": []}
