#!/usr/bin/env python3
# 批量导入 D:/Database 和 D:/Note/Typora 中的文档到知识库
# 按目录结构自动分类：数据库类型 + 9 类文档类型
import requests
import json
import os
import re
import sys

API = "http://localhost:8686"
SOURCES = {
    "typora": r"D:\Note\Typora",
    "database": r"D:\Database",
}

# ── 支持的文件扩展名 ────────────────────────────────────
DOC_EXTS = {".md", ".pdf", ".doc", ".docx", ".txt"}
SKIP_DIRS = {"img", ".obsidian", "themes"}

# ── 数据库类型映射（目录名 → 标准名）────────────────────
DB_MAP = {
    "mysql": "MySQL", "MySQL": "MySQL",
    "oracle": "Oracle", "Oracle": "Oracle",
    "postgresql": "PostgreSQL", "PostgreSQL": "PostgreSQL",
    "sql server": "SQL Server", "SQL Server": "SQL Server",
    "sqlserver": "SQL Server",
    "linux": "Linux", "Linux": "Linux",
    "redis": "Redis", "Redis": "Redis",
    "mongodb": "MongoDB", "Mongodb": "MongoDB", "mongodb": "MongoDB",
    "sql": "其他", "SQL": "其他",
    "windows": "Linux", "Windows": "Linux",
    "监控": "其他",
    "其他": "其他",
    "镜像": "Linux",
}

# ── 路径关键词 → 文档类型 ────────────────────────────────
# 优先级从高到低，先匹配先命中
CATEGORY_RULES = [
    # 排障手册
    (r"故障处理手册|故障处理|故障排查|troubleshoot|常见问题|错误码", "排障手册"),
    # 备份恢复
    (r"备份恢复|备份与迁移|rman|mydumper|xtrabackup|mysqldump|mysqlpump|mysqlbackup|备份脚本|备份策略|恢复|flashback|binlog.*恢复|时间点恢复|可传输表空间|导入导出|expdp|数据迁移", "备份恢复"),
    # 安装部署
    (r"安装|部署|静默|一键安装|rac.*安装|补丁|打补丁|升级|卸载", "安装部署"),
    # 架构设计
    (r"集群|mgr|mha|innodb.?cluster|dg搭建|dg.*搭建|ogg.*搭建|ogg\d|高可用|主从|复制|复制与高可用|alwayson|架构|灾备| Patroni", "架构设计"),
    # 性能调优
    (r"awr|调优|优化|性能|慢查询|内存排查|内存分配|buffer|cpu|统计信息|内存使用高|OOM|sysbench", "性能调优"),
    # 安全加固
    (r"安全|加固|安测|wallet|权限|密码复杂度|登录失败|ssl|审计|三权|终端管理|连接超时", "安全加固"),
    # 迁移方案
    (r"迁移|11g迁移|升级.*方案|升级手册|字符集改造|字符集转换|回滚", "迁移方案"),
    # 巡检规范
    (r"巡检|规范|预案|应急预案|开发规范|运维规范|运维报告", "巡检规范"),
    # 学习笔记（兜底）
    (r"学习|ocp|题库|新员工培训|进阶篇|基础篇|运维篇|实战45讲|体系架构|体系结构|是怎样运行|读书笔记|材料文档", "学习笔记"),
]

# ── 按目录名直接映射分类的快捷规则 ───────────────────────
DIR_CATEGORY_MAP = {
    "MySQL故障处理手册": "排障手册",
    "故障处理": "排障手册",
    "常见问题": "排障手册",
    "备份恢复": "备份恢复",
    "备份与迁移": "备份恢复",
    "备份": "备份恢复",
    "rman": "备份恢复",
    "xtrabackup安装包": "备份恢复",
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
    "补充": "安全加固",
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
    "配置文件": "安装部署",
    "参数文件": "安装部署",
    "对象": "学习笔记",
    "用户与锁": "排障手册",
    "表空间": "排障手册",
    "asm扩容": "排障手册",
    "故障恢复": "排障手册",
    "日志排查": "排障手册",
    "dd": "排障手册",
}


def detect_db_type(relpath):
    """从相对路径推断数据库类型"""
    parts = relpath.replace("\\", "/").split("/")
    # 第一级目录通常是数据库类型
    top = parts[0] if parts else ""
    # 精确匹配
    if top in DB_MAP:
        return DB_MAP[top]
    # 大小写不敏感匹配
    top_lower = top.lower()
    for k, v in DB_MAP.items():
        if k.lower() == top_lower:
            return v
    return "其他"


def detect_category(relpath, filename):
    """从相对路径和文件名推断文档类型"""
    parts = relpath.replace("\\", "/").split("/")
    # 先看目录名直接映射
    for part in parts[1:]:  # 跳过第一级（数据库类型）
        if part in DIR_CATEGORY_MAP:
            return DIR_CATEGORY_MAP[part]
    # 用正则规则匹配完整路径+文件名
    full = relpath + "/" + filename
    for pattern, cat in CATEGORY_RULES:
        if re.search(pattern, full, re.IGNORECASE):
            return cat
    return "学习笔记"  # 兜底


def clean_name(filename):
    """清理文件名作为文档标题"""
    name = os.path.splitext(filename)[0]
    # 去掉常见的前缀编号如 "1.1 ", "13.2 "
    name = re.sub(r"^\d+(\.\d+)*\s*", "", name)
    # 去掉 ~$ 临时文件标记
    name = name.replace("~$", "")
    return name.strip()


def is_skip_file(filename, filepath):
    """判断是否跳过此文件"""
    if filename.startswith("~$"):
        return True
    if filename.startswith("."):
        return True
    ext = os.path.splitext(filename)[1].lower()
    if ext not in DOC_EXTS:
        return True
    # 跳过太小的 txt 文件（可能是配置片段）
    if ext == ".txt":
        try:
            size = os.path.getsize(filepath)
            if size < 100:  # 小于 100 字节
                return True
        except OSError:
            return True
    return False


def extract_summary(filepath, ext):
    """尝试提取文档摘要"""
    if ext == ".md":
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = []
                for i, line in enumerate(f):
                    if i > 20:
                        break
                    line = line.strip()
                    # 跳过 YAML frontmatter
                    if i == 0 and line == "---":
                        continue
                    if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("```"):
                        lines.append(line)
                    if len(lines) >= 2:
                        break
                return " ".join(lines)[:200]
        except Exception:
            pass
    return ""


def extract_tags(relpath, filename, db_type, category):
    """从路径和文件名提取标签"""
    tags = [db_type]
    parts = relpath.replace("\\", "/").split("/")
    # 添加有意义的中间目录作为标签
    for part in parts[1:3]:
        if part and part not in tags and part not in SKIP_DIRS and len(part) < 20:
            tags.append(part)
    # 从文件名提取关键词
    name_lower = filename.lower()
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
    return tags[:5]  # 最多 5 个标签


def scan_directory(base_path, source_name):
    """扫描目录，收集文档列表"""
    articles = []
    for root, dirs, files in os.walk(base_path):
        # 过滤掉不需要的目录
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            fpath = os.path.join(root, fname)
            if is_skip_file(fname, fpath):
                continue
            relpath = os.path.relpath(root, base_path)
            if relpath == ".":
                relpath = ""
            ext = os.path.splitext(fname)[1].lower()
            # 跳过顶层 Untitled.md（通常是空文件）
            if fname == "Untitled.md" and not relpath:
                continue
            # 跳过 img 相关
            if "img" in relpath:
                continue
            db_type = detect_db_type(relpath)
            category = detect_category(relpath, fname)
            title = clean_name(fname)
            if not title:
                continue
            # 路径使用正斜杠存储
            full_path = os.path.normpath(fpath)
            summary = extract_summary(fpath, ext)
            if not summary:
                summary = f"{category} - {db_type}"
            tags = extract_tags(relpath, fname, db_type, category)
            articles.append({
                "title": title,
                "summary": summary,
                "content": "",
                "category": category,
                "tags": ",".join(tags),
                "file_path": full_path,
                "wb_db": db_type,
            })
    return articles


def check_existing(api_articles):
    """获取已有文档的路径集合，用于去重"""
    existing = set()
    for a in api_articles:
        fp = a.get("file_path", "")
        if fp:
            existing.add(os.path.normpath(fp))
    return existing


def main():
    print("=" * 60)
    print("  知识库批量导入工具")
    print("=" * 60)

    # 1. 检查服务器连接
    print("\n[1/4] 检查服务器连接...")
    try:
        r = requests.get(f"{API}/api/articles/?page_size=1", timeout=5)
        r.raise_for_status()
        existing_items = requests.get(f"{API}/api/articles/?page_size=1000", timeout=10).json().get("items", [])
    except Exception as e:
        print(f"  ❌ 无法连接服务器: {e}")
        print("  请确保 server/main.py 已启动")
        return
    existing_paths = check_existing(existing_items)
    print(f"  ✓ 服务器已连接，现有 {len(existing_items)} 篇文档")

    # 2. 扫描目录
    print("\n[2/4] 扫描文档目录...")
    all_articles = []
    for source_name, base_path in SOURCES.items():
        if not os.path.isdir(base_path):
            print(f"  ⚠ 目录不存在: {base_path}")
            continue
        articles = scan_directory(base_path, source_name)
        print(f"  ✓ {source_name} ({base_path}): 发现 {len(articles)} 个文档")
        all_articles.extend(articles)

    # 3. 去重
    new_articles = [a for a in all_articles if os.path.normpath(a["file_path"]) not in existing_paths]
    skipped = len(all_articles) - len(new_articles)
    print(f"\n[3/4] 去重检查...")
    print(f"  总计扫描: {len(all_articles)} 篇")
    print(f"  已有跳过: {skipped} 篇")
    print(f"  待导入:   {len(new_articles)} 篇")

    if not new_articles:
        print("\n  没有新文档需要导入。")
        return

    # 统计
    db_counts = {}
    cat_counts = {}
    for a in new_articles:
        db_counts[a["wb_db"]] = db_counts.get(a["wb_db"], 0) + 1
        cat_counts[a["category"]] = cat_counts.get(a["category"], 0) + 1

    print(f"\n  按数据库类型:")
    for db, cnt in sorted(db_counts.items(), key=lambda x: -x[1]):
        print(f"    {db}: {cnt} 篇")
    print(f"\n  按文档类型:")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt} 篇")

    # 4. 导入
    print(f"\n[4/4] 开始导入 {len(new_articles)} 篇文档...")
    success = 0
    failed = 0
    for i, article in enumerate(new_articles, 1):
        try:
            r = requests.post(f"{API}/api/articles/", json=article, timeout=10)
            r.raise_for_status()
            success += 1
            if i % 20 == 0 or i == len(new_articles):
                print(f"  进度: {i}/{len(new_articles)} (成功 {success}, 失败 {failed})")
        except Exception as e:
            failed += 1
            print(f"  ❌ 导入失败 [{article['title']}]: {e}")

    print(f"\n{'=' * 60}")
    print(f"  ✓ 导入完成: 成功 {success} 篇, 失败 {failed} 篇")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
