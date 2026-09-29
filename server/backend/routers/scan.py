"""Scan API - discover local files and index them into the workspace.

Scans configured directories, classifies files by extension, and proposes
new entries for resources (installers) / articles (docs) / scripts.
Existing entries are matched by absolute path and never duplicated.
Files are NEVER moved or modified - only indexed.
"""
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db_ctx

logger = logging.getLogger(__name__)
router = APIRouter()

# Extension → module classification
INSTALLER_EXTS = {".msi", ".exe", ".bin", ".zip", ".7z", ".rar", ".iso", ".tar", ".gz", ".rpm", ".deb", ".dmg", ".apk"}
DOC_EXTS = {".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".html", ".htm"}
SCRIPT_EXTS = {".sh", ".py", ".ps1", ".bat", ".cmd", ".sql"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".obsidian", "$RECYCLE.BIN",
             "System Volume Information", "AppData", ".venv", "venv", ".idea", ".vscode"}
MAX_DEPTH = 6
MAX_SCRIPT_READ = 512 * 1024  # 512KB limit for inline script content


def classify(ext: str) -> str:
    ext = ext.lower()
    if ext in INSTALLER_EXTS:
        return "resource"
    if ext in DOC_EXTS:
        return "article"
    if ext in SCRIPT_EXTS:
        return "script"
    return ""


def guess_script_type(path: Path) -> str:
    """Guess database type from filename keywords (order matters: more specific first)."""
    name = path.name.lower()
    # 更精确的匹配，避免 "ora" 匹配到 "storage" 等词
    rules = [
        (["mysql", "mariadb"], "MySQL"),
        (["oracle", "rac", "asm_"], "Oracle"),
        (["sqlserver", "mssql", "sql_server"], "SQL Server"),
        (["redis"], "Redis"),
        (["postgres", "pgsql", "postgresql"], "PostgreSQL"),
    ]
    for keywords, db_type in rules:
        for kw in keywords:
            if kw in name:
                return db_type
    return "通用"


class ScanDirCreate(BaseModel):
    path: str


class ScanRequest(BaseModel):
    paths: Optional[list[str]] = None  # scan specific dirs; default = all enabled scan_dirs


def _existing_paths(conn) -> set:
    """All absolute paths already indexed (lowercased for comparison)."""
    paths = set()
    for table, col in [("resources", "path"), ("articles", "file_path"), ("scripts", "file_path")]:
        try:
            for (p,) in conn.execute(f"SELECT {col} FROM {table} WHERE {col} != ''").fetchall():
                paths.add(os.path.normpath(p).lower())
        except Exception as e:
            logger.warning("Failed to load existing paths from %s: %s", table, e)
    return paths


def _walk(base: Path):
    """Yield files under base up to MAX_DEPTH, skipping noisy dirs."""
    base_depth = len(base.parts)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        if len(Path(root).parts) - base_depth >= MAX_DEPTH:
            dirs[:] = []
        for f in files:
            if f.startswith("~$") or f == "desktop.ini":
                continue
            yield Path(root) / f


def scan_dir(base: Path, known: set) -> list:
    """Return proposed entries (dicts) for un-indexed files in base."""
    proposals = []
    if not base.exists():
        return proposals
    for fp in _walk(base):
        ext = fp.suffix.lower()
        kind = classify(ext)
        if not kind:
            continue
        norm = os.path.normpath(str(fp)).lower()
        if norm in known:
            continue
        known.add(norm)
        try:
            size_mb = round(fp.stat().st_size / (1024 * 1024), 2)
        except OSError:
            size_mb = 0
        entry = {
            "kind": kind,
            "name": fp.stem,
            "path": str(fp),
            "size_mb": size_mb,
            "selected": True,
        }
        if kind == "resource":
            entry["res_kind"] = "安装包" if ext in (".msi", ".exe", ".bin", ".iso", ".rpm", ".deb", ".apk", ".dmg") else "其他"
        elif kind == "script":
            entry["db_type"] = guess_script_type(fp)
        proposals.append(entry)
    return proposals


# ── Scan directory management ──

@router.get("/dirs")
def list_scan_dirs():
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM scan_dirs ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/dirs")
def add_scan_dir(data: ScanDirCreate):
    p = data.path.strip().strip('"')
    if not p:
        raise HTTPException(400, "路径为空")
    if not Path(p).exists():
        raise HTTPException(404, f"目录不存在: {p}")
    with get_db_ctx() as conn:
        # 检查是否已存在
        if conn.execute("SELECT id FROM scan_dirs WHERE path = ?", (p,)).fetchone():
            raise HTTPException(409, "该目录已在扫描列表中")
        try:
            conn.execute("INSERT INTO scan_dirs (path) VALUES (?)", (p,))
            conn.commit()
        except Exception as e:
            logger.warning("Failed to add scan dir: %s", e)
            raise HTTPException(500, f"添加失败: {e}")
        row = conn.execute("SELECT * FROM scan_dirs WHERE path = ?", (p,)).fetchone()
        return dict(row)


@router.delete("/dirs/{did}")
def delete_scan_dir(did: int):
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM scan_dirs WHERE id = ?", (did,)).fetchone():
            raise HTTPException(404, "Scan dir not found")
        conn.execute("DELETE FROM scan_dirs WHERE id = ?", (did,))
        conn.commit()
        return {"ok": True}


# ── Scan ──

@router.post("/run")
def run_scan(req: ScanRequest):
    """Scan directories and return proposed new entries (nothing is written yet)."""
    with get_db_ctx() as conn:
        if req.paths:
            dirs = req.paths
        else:
            dirs = [r["path"] for r in conn.execute(
                "SELECT path FROM scan_dirs WHERE enabled = 1").fetchall()]
        known = _existing_paths(conn)

    proposals = []
    for d in dirs:
        proposals.extend(scan_dir(Path(d), known))
    return {"scanned_dirs": dirs, "proposed": len(proposals), "items": proposals}


class CommitItem(BaseModel):
    kind: str            # resource | article | script
    name: str
    path: str
    size_mb: float = 0
    res_kind: str = "其他"
    db_type: str = "通用"
    notes: str = ""


class CommitRequest(BaseModel):
    items: list[CommitItem]


@router.post("/commit")
def commit_scan(req: CommitRequest):
    """Write selected proposals into their tables (idempotent by path)."""
    # 预加载已知路径，避免逐条查询（TOCTOU 风险由客户端保证仅提交 /run 返回的项目）
    with get_db_ctx() as conn:
        known_paths = set()
        for table, col in [("resources", "path"), ("articles", "file_path"), ("scripts", "file_path")]:
            for (p,) in conn.execute(f"SELECT {col} FROM {table} WHERE {col} != ''").fetchall():
                known_paths.add(os.path.normpath(p).lower())

        counts = {"resource": 0, "article": 0, "script": 0, "skipped": 0}
        for it in req.items:
            norm = os.path.normpath(it.path).lower()
            if norm in known_paths:
                counts["skipped"] += 1
                continue

            if it.kind == "resource":
                conn.execute(
                    "INSERT INTO resources (name, kind, path, size_mb, category, notes) VALUES (?, ?, ?, ?, ?, ?)",
                    (it.name, it.res_kind, it.path, it.size_mb, "扫描入库", it.notes),
                )
                counts["resource"] += 1
            elif it.kind == "article":
                conn.execute(
                    "INSERT INTO articles (title, summary, content, category, file_path) VALUES (?, ?, ?, ?, ?)",
                    (it.name, "", "", "文档索引", it.path),
                )
                counts["article"] += 1
            elif it.kind == "script":
                # 仅读取小型文本脚本内容
                content = ""
                try:
                    p = Path(it.path)
                    if p.suffix.lower() in (".sh", ".py", ".ps1", ".bat", ".cmd", ".sql") and p.stat().st_size < MAX_SCRIPT_READ:
                        content = p.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    logger.warning("Failed to read script %s: %s", it.path, e)
                conn.execute(
                    "INSERT INTO scripts (title, description, db_type, content, file_path) VALUES (?, ?, ?, ?, ?)",
                    (it.name, "扫描入库", it.db_type, content, it.path),
                )
                counts["script"] += 1

            known_paths.add(norm)

        conn.commit()
        return {"ok": True, "imported": counts}
