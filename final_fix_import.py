"""
彻底清理脚本表并使用正确的UTF-8编码重新导入
"""
import sqlite3
import os
import sys

# 强制Python使用UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "D:/coding/workspace/server/workspace.db"

def clear_scripts_table():
    """清空脚本表"""
    print("=" * 60)
    print("清空脚本表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 删除所有脚本
    cursor.execute("DELETE FROM scripts")
    cursor.execute("DELETE FROM script_versions")

    conn.commit()
    conn.close()

    print("脚本表已清空")
    print("=" * 60)

def import_scripts_with_correct_encoding():
    """使用正确的UTF-8编码导入脚本"""
    print("=" * 60)
    print("导入脚本（UTF-8编码）")
    print("=" * 60)

    scripts_to_import = [
        # Oracle 巡检
        ("Oracle 10g 健康检查脚本", "Oracle 10g数据库全面健康检查", "Oracle", "巡检",
         "巡检,Oracle,健康检查,10g", "D:/Database/数据库巡检脚本/DB_Oracle_HC_10g.sql"),
        ("Oracle 11g 健康检查脚本", "Oracle 11g数据库全面健康检查（支持ASM/RAC）", "Oracle", "巡检",
         "巡检,Oracle,健康检查,11g,ASM,RAC", "D:/Database/数据库巡检脚本/DB_Oracle_HC_11g.sql"),
        ("Oracle 11g 简化版健康检查脚本", "Oracle 11g数据库快速健康检查", "Oracle", "巡检",
         "巡检,Oracle,健康检查,11g,简化版", "D:/Database/数据库巡检脚本/DB_Oracle_HC_11g_simple.sql"),
        ("Oracle 12c 健康检查脚本", "Oracle 12c数据库全面健康检查（支持CDB/PDB）", "Oracle", "巡检",
         "巡检,Oracle,健康检查,12c,CDB,PDB", "D:/Database/数据库巡检脚本/DB_Oracle_HC_12c.sql"),
        ("Oracle DG 检查脚本", "Oracle Data Guard环境检查", "Oracle", "巡检",
         "巡检,Oracle,DG,DataGuard", "D:/Database/oracle/dg/检查脚本/dgsql.txt"),
        ("Oracle 11g 数据库检查脚本", "Oracle 11g数据库专项检查", "Oracle", "巡检",
         "巡检,Oracle,健康检查,11g,诊断", "D:/Database/数据库巡检脚本/dbcheck11g.sql"),

        # Oracle 备份
        ("Windows RMAN 自动备份脚本 0", "Windows环境Oracle RMAN自动备份", "Oracle", "备份",
         "备份,Oracle,RMAN,Windows", "D:/Database/oracle/rman/windows rman自动备份部署/rmanbackup0.bat"),
        ("Windows RMAN 自动备份脚本 1", "Windows环境Oracle RMAN增量备份", "Oracle", "备份",
         "备份,Oracle,RMAN,Windows,增量", "D:/Database/oracle/rman/windows rman自动备份部署/rmanbackup1.bat"),

        # Oracle 部署
        ("Oracle Wallet 配置向导脚本", "一键配置Oracle Wallet", "Oracle", "部署",
         "部署,Oracle,Wallet,安全", "D:/Database/oracle/脚本/Wallet/setup_wallet.sh"),

        # MySQL 巡检
        ("MySQL 健康检查报告脚本", "MySQL数据库全面健康检查（生成HTML报告）", "MySQL", "巡检",
         "巡检,MySQL,健康检查,HTML报告", "D:/Database/数据库巡检脚本/DB_MySQL_HC.sql"),

        # SQL Server 巡检
        ("SQL Server 2005+ 健康检查脚本", "SQL Server 2005及以上版本健康检查", "SQL Server", "巡检",
         "巡检,SQLServer,健康检查,2005", "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2005up.sql"),
        ("SQL Server 2008R2+ 健康检查脚本", "SQL Server 2008R2及以上版本健康检查", "SQL Server", "巡检",
         "巡检,SQLServer,健康检查,2008R2,AlwaysOn", "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2008R2up.sql"),
        ("SQL Server 2008R2+ 健康检查脚本(无SA权限)", "SQL Server 2008R2健康检查（无SA权限版本）", "SQL Server", "巡检",
         "巡检,SQLServer,健康检查,2008R2,权限受限", "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2008R2up-no_sa_privileges.sql"),
    ]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    success = 0
    for script in scripts_to_import:
        title, description, db_type, wb_type, tags, file_path = script

        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"[SKIP] 文件不存在: {file_path}")
            continue

        # 插入脚本（只存储路径，不存储内容）
        cursor.execute("""
            INSERT INTO scripts (title, description, db_type, tags, content, file_path, wb_type)
            VALUES (?, ?, ?, ?, '', ?, ?)
        """, (title, description, db_type, tags, file_path, wb_type))

        script_id = cursor.lastrowid
        print(f"[OK] 导入成功: {title} (ID={script_id})")
        print(f"     db_type={db_type}, wb_type={wb_type}")
        success += 1

    conn.commit()
    conn.close()

    print("=" * 60)
    print(f"导入完成: 成功 {success}/{len(scripts_to_import)}")
    print("=" * 60)

def verify_import():
    """验证导入结果"""
    print("=" * 60)
    print("验证导入结果")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, db_type, wb_type, tags, file_path FROM scripts ORDER BY id")
    rows = cursor.fetchall()

    print(f"总计 {len(rows)} 个脚本:")
    print()

    for row in rows:
        print(f"  ID={row['id']:3d}")
        print(f"    标题: {row['title']}")
        print(f"    数据库: {row['db_type']}")
        print(f"    类型: {row['wb_type']}")
        print(f"    标签: {row['tags']}")
        print(f"    路径: {row['file_path']}")
        print()

    conn.close()

    print("=" * 60)

if __name__ == "__main__":
    clear_scripts_table()
    print()
    import_scripts_with_correct_encoding()
    print()
    verify_import()
