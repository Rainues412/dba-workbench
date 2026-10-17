"""Scan API - discover local files and index them into the workspace.

Scans configured directories, classifies files by extension, and proposes
new entries for resources (installers) / articles (docs) / scripts.
Existing entries are matched by absolute path and never duplicated.
Files are NEVER moved or modified - only indexed.
"""
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.database import get_db_ctx
from backend.local_capabilities import (
    audit_local_action,
    require_local_action,
    resolve_allowed_path,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Extension → module classification
INSTALLER_EXTS = {".msi", ".exe", ".bin", ".zip", ".7z", ".rar", ".iso", ".tar", ".gz", ".rpm", ".deb", ".dmg", ".apk"}
DOC_EXTS = {".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".html", ".htm"}
SCRIPT_EXTS = {".sh", ".py", ".ps1", ".bat", ".cmd", ".sql"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".obsidian", "$RECYCLE.BIN",
             "System Volume Information", "AppData", ".venv", "venv", ".idea", ".vscode", "img"}
MAX_DEPTH = 6
MAX_SCRIPT_READ = 512 * 1024  # 512KB limit for inline script content

# Database type mapping
DB_MAP = {
    "mysql": "MySQL", "mariadb": "MySQL",
    "oracle": "Oracle", "rac": "Oracle", "asm": "Oracle",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "pgsql": "PostgreSQL",
    "sqlserver": "SQL Server", "mssql": "SQL Server", "sql_server": "SQL Server",
    "linux": "Linux",
    "redis": "Redis",
    "mongodb": "MongoDB", "mongo": "MongoDB",
}

# Document category rules (priority order)
CATEGORY_RULES = [
    (r"故障处理|故障排查|troubleshoot|常见问题|错误码|crash|死锁|锁阻塞|阻塞", "排障手册"),
    (r"备份恢复|备份与迁移|rman|mydumper|xtrabackup|mysqldump|mysqlpump|备份脚本|恢复|flashback|binlog.*恢复|expdp", "备份恢复"),
    (r"安装|部署|静默|一键安装|补丁|打补丁|升级|卸载|配置", "安装部署"),
    (r"集群|mgr|mha|innodb.?cluster|dg搭建|ogg.*搭建|高可用|主从|复制|alwayson|架构|灾备", "架构设计"),
    (r"awr|调优|优化|性能|慢查询|内存排查|内存分配|buffer|cpu|统计信息|oom|sysbench", "性能调优"),
    (r"安全|加固|安测|wallet|权限|密码复杂度|登录失败|ssl|审计|三权", "安全加固"),
    (r"迁移|11g迁移|升级.*方案|字符集改造|字符集转换|回滚", "迁移方案"),
    (r"巡检|规范|预案|应急预案|开发规范|运维规范|运维报告", "巡检规范"),
    (r"学习|ocp|题库|新员工培训|进阶篇|基础篇|运维篇|实战45讲|体系架构|体系结构|材料文档", "学习笔记"),
]

# Directory name to category mapping
DIR_CATEGORY_MAP = {
    "MySQL故障处理手册": "排障手册",
    "故障处理": "排障手册",
    "常见问题": "排障手册",
    "备份恢复": "备份恢复",
    "备份与迁移": "备份恢复",
    "备份": "备份恢复",
    "rman": "备份恢复",
    "mydumper": "备份恢复",
    "mysqldump": "备份恢复",
    "mysqlpump": "备份恢复",
    "mysqlbackup": "备份恢复",
    "导入导出": "备份恢复",
    "安装": "安装部署",
    "安装与配置": "安装部署",
    "安装包": "安装部署",
    "补丁": "安装部署",
    "补充文档": "安装部署",
    "集群": "架构设计",
    "innodb cluster": "架构设计",
    "mgr": "架构设计",
    "mha": "架构设计",
    "普通主从": "架构设计",
    "复制与高可用": "架构设计",
    "dg": "架构设计",
    "ogg": "架构设计",
    "优化": "性能调优",
    "awr分析": "性能调优",
    "内存分配机制": "性能调优",
    "内存cpu": "性能调优",
    "监控与排查": "性能调优",
    "安全与权限": "安全加固",
    "安全加固": "安全加固",
    "安测": "安全加固",
    "升级": "迁移方案",
    "升级mysql5.7": "迁移方案",
    "回滚": "迁移方案",
    "11g迁移至19c": "迁移方案",
    "运维": "迁移方案",
    "巡检报告": "巡检规范",
    "巡检脚本": "巡检规范",
    "数据库巡检脚本": "巡检规范",
    "企业规范与预案": "巡检规范",
    "脚本": "巡检规范",
    "学习": "学习笔记",
    "体系架构学习笔记": "学习笔记",
    "体系结构": "学习笔记",
    "资料-MySQL数据库": "学习笔记",
    "MySQL 新员工培训": "学习笔记",
    "进阶篇": "学习笔记",
    "文档": "学习笔记",
    "MYSQL实战45讲PDF": "学习笔记",
    "mysql材料文档": "学习笔记",
    "对象": "学习笔记",
    "用户与锁": "排障手册",
    "表空间": "排障手册",
    "asm扩容": "排障手册",
    "故障恢复": "排障手册",
}


def classify(ext: str) -> str:
    ext = ext.lower()
    if ext in INSTALLER_EXTS:
        return "resource"
    if ext in DOC_EXTS:
        return "article"
    if ext in SCRIPT_EXTS:
        return "script"
    return ""


def detect_db_type(path: Path) -> str:
    """Detect database type from path components."""
    parts = [p.lower() for p in path.parts]
    for part in parts:
        for key, db_type in DB_MAP.items():
            if key in part:
                return db_type
    return "其他"


def detect_category(path: Path) -> str:
    """Detect document category from path components."""
    # Check directory names first
    for part in path.parts:
        if part in DIR_CATEGORY_MAP:
            return DIR_CATEGORY_MAP[part]

    # Check full path against keyword rules
    full_path = str(path).lower()
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, full_path, re.IGNORECASE):
            return category

    return "学习笔记"  # Default fallback


def extract_tags(path: Path, db_type: str, category: str) -> list:
    """Extract relevant tags from path and filename."""
    tags = [db_type]
    name_lower = path.name.lower()

    keywords = {
        "rac": "RAC", "dg": "DG", "ogg": "OGG", "awr": "AWR",
        "mgr": "MGR", "mha": "MHA", "redis": "Redis",
        "innodb": "InnoDB", "cluster": "Cluster",
        "主从": "主从", "备份": "备份", "恢复": "恢复",
        "迁移": "迁移", "升级": "升级", "安装": "安装",
        "安全": "安全", "巡检": "巡检", "优化": "优化",
        "故障": "故障", "crash": "Crash", "死锁": "死锁",
        "锁阻塞": "锁阻塞", "cpu": "CPU", "内存": "内存",
        "慢查询": "慢查询", "复制": "复制", "延迟": "延迟",
    }

    for kw, tag in keywords.items():
        if kw in name_lower and tag not in tags:
            tags.append(tag)

    return tags[:5]


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
        if fp.is_symlink():
            continue
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

        # Detect database type and category for all file types
        db_type = detect_db_type(fp)

        entry = {
            "kind": kind,
            "name": fp.stem,
            "path": str(fp),
            "size_mb": size_mb,
            "selected": True,
            "db_type": db_type,
        }

        if kind == "resource":
            entry["res_kind"] = "安装包" if ext in (".msi", ".exe", ".bin", ".iso", ".rpm", ".deb", ".apk", ".dmg") else "其他"
        elif kind == "script":
            # For scripts, also check filename keywords for more precise classification
            script_db = guess_script_type(fp)
            if script_db != "通用":
                entry["db_type"] = script_db
        elif kind == "article":
            # Detect category for documents
            entry["category"] = detect_category(fp)
            entry["tags"] = extract_tags(fp, db_type, entry["category"])

        proposals.append(entry)
    return proposals


# ── Scan directory management ──

@router.get("/dirs")
def list_scan_dirs():
    require_local_action("scan")
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM scan_dirs ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/dirs")
def add_scan_dir(data: ScanDirCreate):
    require_local_action("scan")
    try:
        path = resolve_allowed_path(data.path, expect="directory")
    except HTTPException:
        audit_local_action("scan", "denied_path")
        raise
    p = str(path)
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
        audit_local_action("scan", "directory_added", path)
        return dict(row)


@router.delete("/dirs/{did}")
def delete_scan_dir(did: int):
    require_local_action("scan")
    with get_db_ctx() as conn:
        if not conn.execute("SELECT id FROM scan_dirs WHERE id = ?", (did,)).fetchone():
            raise HTTPException(404, "Scan dir not found")
        conn.execute("DELETE FROM scan_dirs WHERE id = ?", (did,))
        conn.commit()
        audit_local_action("scan", "directory_removed")
        return {"ok": True}


# ── Scan ──

@router.post("/run")
def run_scan(req: ScanRequest):
    """Scan directories and return proposed new entries (nothing is written yet)."""
    require_local_action("scan")
    with get_db_ctx() as conn:
        if req.paths:
            dirs = req.paths
        else:
            dirs = [r["path"] for r in conn.execute(
                "SELECT path FROM scan_dirs WHERE enabled = 1").fetchall()]
        known = _existing_paths(conn)

    allowed_dirs = []
    for directory in dirs:
        try:
            allowed_dirs.append(resolve_allowed_path(directory, expect="directory"))
        except HTTPException:
            audit_local_action("scan", "denied_path")
            raise

    proposals = []
    for directory in allowed_dirs:
        proposals.extend(scan_dir(directory, known))
    audit_local_action("scan", "completed")
    return {
        "scanned_dirs": [str(directory) for directory in allowed_dirs],
        "proposed": len(proposals),
        "items": proposals,
    }


class CommitItem(BaseModel):
    kind: str            # resource | article | script
    name: str
    path: str
    size_mb: float = 0
    res_kind: str = "其他"
    db_type: str = "通用"
    category: str = "学习笔记"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class CommitRequest(BaseModel):
    items: list[CommitItem]


@router.post("/commit")
def commit_scan(req: CommitRequest):
    """Write selected proposals into their tables (idempotent by path)."""
    require_local_action("scan")
    checked_items = []
    for item in req.items:
        try:
            path = resolve_allowed_path(item.path, expect="file")
        except HTTPException:
            audit_local_action("scan", "denied_path")
            raise
        detected_kind = classify(path.suffix)
        if detected_kind != item.kind:
            audit_local_action("scan", "denied_kind", path)
            raise HTTPException(400, "文件类型与导入类型不匹配")
        checked_items.append((item, path))

    # 预加载已知路径；客户端回传的每个文件已在上方重新执行边界和类型校验。
    with get_db_ctx() as conn:
        known_paths = set()
        for table, col in [("resources", "path"), ("articles", "file_path"), ("scripts", "file_path")]:
            for (p,) in conn.execute(f"SELECT {col} FROM {table} WHERE {col} != ''").fetchall():
                known_paths.add(os.path.normpath(p).lower())

        counts = {"resource": 0, "article": 0, "script": 0, "skipped": 0}
        for it, path in checked_items:
            normalized_path = str(path)
            norm = os.path.normpath(normalized_path).lower()
            if norm in known_paths:
                counts["skipped"] += 1
                continue

            if it.kind == "resource":
                tags_str = ",".join(it.tags) if it.tags else ""
                conn.execute(
                    "INSERT INTO resources (name, kind, path, size_mb, category, notes, wb_db, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (it.name, it.res_kind, normalized_path, it.size_mb, "扫描入库", it.notes, it.db_type, tags_str),
                )
                counts["resource"] += 1
            elif it.kind == "article":
                # Use detected category and tags, convert tags list to comma-separated string
                tags_str = ",".join(it.tags) if it.tags else ""
                conn.execute(
                    "INSERT INTO articles (title, summary, content, category, file_path, wb_db, tags) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (it.name, "", "", it.category, normalized_path, it.db_type, tags_str),
                )
                counts["article"] += 1
            elif it.kind == "script":
                # 仅读取小型文本脚本内容
                content = ""
                try:
                    p = path
                    if p.suffix.lower() in (".sh", ".py", ".ps1", ".bat", ".cmd", ".sql") and p.stat().st_size < MAX_SCRIPT_READ:
                        content = p.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    logger.warning("Failed to read an allowed script: %s", e)
                conn.execute(
                    "INSERT INTO scripts (title, description, db_type, content, file_path) VALUES (?, ?, ?, ?, ?)",
                    (it.name, "扫描入库", it.db_type, content, normalized_path),
                )
                counts["script"] += 1

            known_paths.add(norm)

        conn.commit()
        audit_local_action("scan", "committed")
        return {"ok": True, "imported": counts}
