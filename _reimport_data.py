"""
重新导入脚本库、知识库、安装包数据
从 D:/Database 和 D:/Note/Typora 扫描并按数据库类型分类导入
"""
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

# 设置 UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = r"D:\coding\workspace\server\workspace.db"
DATABASE_ROOT = r"D:\Database"
TYPORA_ROOT = r"D:\Note\Typora"

# 数据库类型映射（文件夹名 -> 标准数据库类型）
DB_TYPE_MAPPING = {
    'mysql': 'MySQL',
    'oracle': 'Oracle',
    'postgresql': 'PostgreSQL',
    'sql server': 'SQL Server',
    'sqlserver': 'SQL Server',
    'redis': 'Redis',
    'mongodb': '其他',
    'linux': 'Linux',
    'windows': '其他',
    'sql': '通用',
    '监控': '其他',
    '其他': '其他',
    '企业规范与预案': '其他',
    '镜像': '其他',
    '数据库巡检脚本': '通用',
}

# 安装包扩展名
INSTALLER_EXTENSIONS = {'.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.rpm', '.deb', '.msi', '.exe', '.jar', '.war'}

# 脚本扩展名
SCRIPT_EXTENSIONS = {'.sql', '.sh', '.bat', '.ps1', '.py'}

# 文档扩展名
DOC_EXTENSIONS = {'.md', '.txt', '.doc', '.docx', '.pdf', '.pptx', '.xlsx', '.xls', '.html'}

def get_db_type_from_path(path_str):
    """从文件路径推断数据库类型"""
    path_lower = path_str.lower()
    for folder, db_type in DB_TYPE_MAPPING.items():
        if folder.lower() in path_lower:
            return db_type
    return '通用'

def get_file_size_mb(file_path):
    """获取文件大小（MB）"""
    try:
        size = os.path.getsize(file_path)
        return round(size / (1024 * 1024), 2)
    except:
        return 0

def extract_version(filename):
    """从文件名提取版本号"""
    import re
    # 匹配常见版本号格式
    patterns = [
        r'[\-_]v?(\d+\.\d+[\.\d]*)',  # -v5.7.38 或 _5.7.38
        r'(\d+\.\d+\.\d+)',  # 5.7.38
        r'(\d+\.\d+)',  # 5.7
    ]
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1)
    return ''

def read_file_content(file_path, max_size=1024*100):  # 最大100KB
    """读取文件内容（用于脚本和markdown）"""
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {'.md', '.txt', '.sql', '.sh', '.bat', '.py'}:
            size = os.path.getsize(file_path)
            if size > max_size:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(max_size)
                    return content + '\n\n... [内容过长已截断] ...'
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
        return ''
    except Exception as e:
        return f'[读取失败: {str(e)}]'

def scan_directory(root_path):
    """扫描目录，分类文件"""
    results = {'scripts': [], 'articles': [], 'resources': []}

    for dirpath, dirnames, filenames in os.walk(root_path):
        # 跳过隐藏目录和临时目录
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in {'img', 'images', '__pycache__'}]

        for filename in filenames:
            if filename.startswith('.') or filename.startswith('~'):
                continue

            file_path = os.path.join(dirpath, filename)
            ext = os.path.splitext(filename)[1].lower()
            rel_path = os.path.relpath(file_path, root_path)

            # 分类
            if ext in SCRIPT_EXTENSIONS:
                results['scripts'].append({
                    'title': filename,
                    'file_path': file_path,
                    'db_type': get_db_type_from_path(rel_path),
                    'content': read_file_content(file_path),
                    'description': f'来自 {rel_path}',
                    'tags': '',
                })
            elif ext in INSTALLER_EXTENSIONS:
                results['resources'].append({
                    'name': filename,
                    'path': file_path,
                    'kind': '安装包',
                    'version': extract_version(filename),
                    'size_mb': get_file_size_mb(file_path),
                    'category': get_db_type_from_path(rel_path),
                    'tags': '',
                    'notes': f'来自 {rel_path}',
                })
            elif ext in DOC_EXTENSIONS:
                results['articles'].append({
                    'title': filename,
                    'file_path': file_path,
                    'wb_db': get_db_type_from_path(rel_path),
                    'content': read_file_content(file_path),
                    'summary': f'来自 {rel_path}',
                    'category': '技术文档',
                    'tags': '',
                })

    return results

def clear_data(conn):
    """清空现有数据"""
    c = conn.cursor()
    c.execute('DELETE FROM scripts')
    c.execute('DELETE FROM script_versions')
    c.execute('DELETE FROM articles')
    c.execute('DELETE FROM resources')
    conn.commit()
    print("✓ 已清空现有数据")

def import_data(conn):
    """导入新数据"""
    c = conn.cursor()
    now = datetime.now().isoformat()

    # 扫描两个目录
    print(f"\n扫描 {DATABASE_ROOT}...")
    db_results = scan_directory(DATABASE_ROOT)
    print(f"  脚本: {len(db_results['scripts'])}")
    print(f"  文档: {len(db_results['articles'])}")
    print(f"  安装包: {len(db_results['resources'])}")

    print(f"\n扫描 {TYPORA_ROOT}...")
    typora_results = scan_directory(TYPORA_ROOT)
    print(f"  脚本: {len(typora_results['scripts'])}")
    print(f"  文档: {len(typora_results['articles'])}")
    print(f"  安装包: {len(typora_results['resources'])}")

    # 合并结果
    all_scripts = db_results['scripts'] + typora_results['scripts']
    all_articles = db_results['articles'] + typora_results['articles']
    all_resources = db_results['resources'] + typora_results['resources']

    # 导入脚本
    print(f"\n导入脚本 ({len(all_scripts)} 个)...")
    for s in all_scripts:
        c.execute('''
            INSERT INTO scripts (title, description, db_type, tags, content, file_path, wb_type, created_at, updated_at, version, is_favorite)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
        ''', (s['title'], s['description'], s['db_type'], s['tags'], s['content'], s['file_path'], s['db_type'], now, now))

    # 导入文档
    print(f"导入文档 ({len(all_articles)} 个)...")
    for a in all_articles:
        c.execute('''
            INSERT INTO articles (title, summary, content, category, tags, file_path, wb_db, created_at, updated_at, is_favorite, is_pinned, view_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
        ''', (a['title'], a['summary'], a['content'], a['category'], a['tags'], a['file_path'], a['wb_db'], now, now))

    # 导入安装包
    print(f"导入安装包 ({len(all_resources)} 个)...")
    for r in all_resources:
        c.execute('''
            INSERT INTO resources (name, kind, path, url, version, size_mb, category, tags, notes, is_favorite, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        ''', (r['name'], r['kind'], r['path'], '', r['version'], r['size_mb'], r['category'], r['tags'], r['notes'], now, now))

    conn.commit()
    print("\n✓ 导入完成")

    # 统计
    print("\n=== 导入统计 ===")
    print(f"脚本总数: {c.execute('SELECT COUNT(*) FROM scripts').fetchone()[0]}")
    print(f"文档总数: {c.execute('SELECT COUNT(*) FROM articles').fetchone()[0]}")
    print(f"安装包总数: {c.execute('SELECT COUNT(*) FROM resources').fetchone()[0]}")

    print("\n=== 按数据库类型分类 ===")
    print("\n脚本库:")
    for row in c.execute('SELECT wb_type, COUNT(*) FROM scripts GROUP BY wb_type ORDER BY COUNT(*) DESC'):
        print(f"  {row[0]}: {row[1]}")

    print("\n知识库:")
    for row in c.execute('SELECT wb_db, COUNT(*) FROM articles GROUP BY wb_db ORDER BY COUNT(*) DESC'):
        print(f"  {row[0]}: {row[1]}")

    print("\n安装包:")
    for row in c.execute('SELECT category, COUNT(*) FROM resources GROUP BY category ORDER BY COUNT(*) DESC'):
        print(f"  {row[0]}: {row[1]}")

def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        clear_data(conn)
        import_data(conn)
        print("\n✓ 所有操作完成")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
