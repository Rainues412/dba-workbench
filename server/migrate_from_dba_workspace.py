"""One-off migration: dba-workspace (FastAPI 版) SQLite -> workspace server SQLite.

Usage:  python migrate_from_dba_workspace.py [source_db_path]
Default source: D:/coding/dba-workspace/workspace.db

Mapping:
  scripts   -> scripts   (title/description/db_type/tags/content/file_path, wb_type='其他')
  articles  -> articles  (title/summary/category/tags/file_path, wb_db='通用')
  resources -> resources (as-is)
  tasks     -> tasks     (priority 高/中/低 -> P0/P1/P2 由前端映射层处理，这里原样存)
  customers -> customers (as-is)
  contacts / communications / passwords: 源库为空，跳过

Idempotent: 以 file_path / title 去重，重复运行不会重复插入。
"""
import sqlite3
import sys
from pathlib import Path

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/coding/dba-workspace/workspace.db")
DST = Path(__file__).parent / "workspace.db"

if not SRC.exists():
    sys.exit(f"源库不存在: {SRC}")
if not DST.exists():
    sys.exit(f"目标库不存在，请先启动一次 server/main.py 初始化: {DST}")

src = sqlite3.connect(str(SRC))
src.row_factory = sqlite3.Row
dst = sqlite3.connect(str(DST))

counts = {}

# ── scripts ──
rows = src.execute("SELECT title, description, db_type, tags, content, file_path FROM scripts").fetchall()
n = 0
for r in rows:
    if r["file_path"] and dst.execute(
            "SELECT 1 FROM scripts WHERE file_path = ?", (r["file_path"],)).fetchone():
        continue
    if not r["file_path"] and dst.execute(
            "SELECT 1 FROM scripts WHERE title = ? AND file_path = ''", (r["title"],)).fetchone():
        continue
    dst.execute(
        "INSERT INTO scripts (title, description, db_type, tags, content, file_path, wb_type) "
        "VALUES (?, ?, ?, ?, ?, ?, '其他')",
        (r["title"], r["description"], r["db_type"], r["tags"], r["content"], r["file_path"]))
    n += 1
counts["scripts"] = n

# ── articles -> knowledge ──
rows = src.execute("SELECT title, summary, content, category, tags, file_path FROM articles").fetchall()
n = 0
for r in rows:
    if r["file_path"] and dst.execute(
            "SELECT 1 FROM articles WHERE file_path = ?", (r["file_path"],)).fetchone():
        continue
    if not r["file_path"] and dst.execute(
            "SELECT 1 FROM articles WHERE title = ? AND file_path = ''", (r["title"],)).fetchone():
        continue
    dst.execute(
        "INSERT INTO articles (title, summary, content, category, tags, file_path, wb_db) "
        "VALUES (?, ?, ?, ?, ?, ?, '通用')",
        (r["title"], r["summary"], r["content"], r["category"], r["tags"], r["file_path"]))
    n += 1
counts["articles"] = n

# ── resources -> installers ──
rows = src.execute(
    "SELECT name, kind, path, url, version, size_mb, category, tags, notes FROM resources").fetchall()
n = 0
for r in rows:
    if r["path"] and dst.execute(
            "SELECT 1 FROM resources WHERE path = ?", (r["path"],)).fetchone():
        continue
    dst.execute(
        "INSERT INTO resources (name, kind, path, url, version, size_mb, category, tags, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (r["name"], r["kind"], r["path"], r["url"], r["version"], r["size_mb"],
         r["category"], r["tags"], r["notes"]))
    n += 1
counts["resources"] = n

# ── tasks ──
rows = src.execute(
    "SELECT title, description, status, priority, due_date FROM tasks").fetchall()
n = 0
for r in rows:
    if dst.execute("SELECT 1 FROM tasks WHERE title = ?", (r["title"],)).fetchone():
        continue
    dst.execute(
        "INSERT INTO tasks (title, description, status, priority, due_date) VALUES (?, ?, ?, ?, ?)",
        (r["title"], r["description"], r["status"], r["priority"], r["due_date"]))
    n += 1
counts["tasks"] = n

# ── customers ──
rows = src.execute(
    "SELECT name, project_name, group_name, status, notes FROM customers").fetchall()
n = 0
for r in rows:
    if dst.execute("SELECT 1 FROM customers WHERE name = ?", (r["name"],)).fetchone():
        continue
    dst.execute(
        "INSERT INTO customers (name, project_name, group_name, status, notes) VALUES (?, ?, ?, ?, ?)",
        (r["name"], r["project_name"], r["group_name"], r["status"], r["notes"]))
    n += 1
counts["customers"] = n

# ── scan_dirs ──
rows = src.execute("SELECT path FROM scan_dirs").fetchall()
n = 0
for r in rows:
    if dst.execute("SELECT 1 FROM scan_dirs WHERE path = ?", (r["path"],)).fetchone():
        continue
    dst.execute("INSERT INTO scan_dirs (path) VALUES (?)", (r["path"],))
    n += 1
counts["scan_dirs"] = n

dst.commit()
for t in ["scripts", "articles", "resources", "tasks", "customers"]:
    print(f"  {t}: 目标库现有 {dst.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} 条 (本次新增 {counts.get(t, 0)})")
print(f"  scan_dirs: 新增 {counts['scan_dirs']}")
src.close()
dst.close()
print("迁移完成")
