#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理并重新导入脚本（修复编码问题）
只导入文件路径，不导入文件内容
"""

import requests
import os

API_BASE = "http://localhost:8686"

def delete_all_scripts():
    """删除所有脚本"""
    print("=" * 60)
    print("删除所有脚本")
    print("=" * 60)

    # 获取所有脚本
    response = requests.get(f"{API_BASE}/api/scripts/?page_size=100")
    if response.status_code != 200:
        print(f"[FAIL] 获取脚本列表失败: {response.text}")
        return

    data = response.json()
    scripts = data.get('items', [])

    print(f"找到 {len(scripts)} 个脚本")

    # 逐个删除
    success = 0
    for script in scripts:
        script_id = script['id']
        try:
            resp = requests.delete(f"{API_BASE}/api/scripts/{script_id}")
            if resp.status_code == 200:
                success += 1
                print(f"[OK] 删除脚本 ID={script_id}: {script['title'][:30]}")
            else:
                print(f"[FAIL] 删除失败 ID={script_id}")
        except Exception as e:
            print(f"[FAIL] 删除异常 ID={script_id}: {e}")

    print(f"删除完成: {success}/{len(scripts)}")
    print("=" * 60)

def import_scripts():
    """导入脚本（只导入路径和元数据，不导入内容）"""
    print("=" * 60)
    print("导入脚本（只导入路径）")
    print("=" * 60)

    scripts_to_import = [
        # Oracle 巡检
        {
            "title": "Oracle 10g 健康检查脚本",
            "description": "Oracle 10g数据库全面健康检查",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "巡检,Oracle,健康检查,10g",
            "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_10g.sql",
            "content": ""
        },
        {
            "title": "Oracle 11g 健康检查脚本",
            "description": "Oracle 11g数据库全面健康检查（支持ASM/RAC）",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "巡检,Oracle,健康检查,11g,ASM,RAC",
            "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_11g.sql",
            "content": ""
        },
        {
            "title": "Oracle 11g 简化版健康检查脚本",
            "description": "Oracle 11g数据库快速健康检查",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "巡检,Oracle,健康检查,11g,简化版",
            "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_11g_simple.sql",
            "content": ""
        },
        {
            "title": "Oracle 12c 健康检查脚本",
            "description": "Oracle 12c数据库全面健康检查（支持CDB/PDB）",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "巡检,Oracle,健康检查,12c,CDB,PDB",
            "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_12c.sql",
            "content": ""
        },
        {
            "title": "Oracle DG 检查脚本",
            "description": "Oracle Data Guard环境检查",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "巡检,Oracle,DG,DataGuard",
            "file_path": "D:/Database/oracle/dg/检查脚本/dgsql.txt",
            "content": ""
        },
        {
            "title": "Oracle 11g 数据库检查脚本",
            "description": "Oracle 11g数据库专项检查",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "巡检,Oracle,健康检查,11g,诊断",
            "file_path": "D:/Database/数据库巡检脚本/dbcheck11g.sql",
            "content": ""
        },

        # Oracle 备份
        {
            "title": "Windows RMAN 自动备份脚本 0",
            "description": "Windows环境Oracle RMAN自动备份",
            "db_type": "Oracle",
            "wb_type": "备份",
            "tags": "备份,Oracle,RMAN,Windows",
            "file_path": "D:/Database/oracle/rman/windows rman自动备份部署/rmanbackup0.bat",
            "content": ""
        },
        {
            "title": "Windows RMAN 自动备份脚本 1",
            "description": "Windows环境Oracle RMAN增量备份",
            "db_type": "Oracle",
            "wb_type": "备份",
            "tags": "备份,Oracle,RMAN,Windows,增量",
            "file_path": "D:/Database/oracle/rman/windows rman自动备份部署/rmanbackup1.bat",
            "content": ""
        },

        # Oracle 部署
        {
            "title": "Oracle Wallet 配置向导脚本",
            "description": "一键配置Oracle Wallet",
            "db_type": "Oracle",
            "wb_type": "部署",
            "tags": "部署,Oracle,Wallet,安全",
            "file_path": "D:/Database/oracle/脚本/Wallet/setup_wallet.sh",
            "content": ""
        },

        # MySQL 巡检
        {
            "title": "MySQL 健康检查报告脚本",
            "description": "MySQL数据库全面健康检查（生成HTML报告）",
            "db_type": "MySQL",
            "wb_type": "巡检",
            "tags": "巡检,MySQL,健康检查,HTML报告",
            "file_path": "D:/Database/数据库巡检脚本/DB_MySQL_HC.sql",
            "content": ""
        },

        # SQL Server 巡检
        {
            "title": "SQL Server 2005+ 健康检查脚本",
            "description": "SQL Server 2005及以上版本健康检查",
            "db_type": "SQL Server",
            "wb_type": "巡检",
            "tags": "巡检,SQLServer,健康检查,2005",
            "file_path": "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2005up.sql",
            "content": ""
        },
        {
            "title": "SQL Server 2008R2+ 健康检查脚本",
            "description": "SQL Server 2008R2及以上版本健康检查",
            "db_type": "SQL Server",
            "wb_type": "巡检",
            "tags": "巡检,SQLServer,健康检查,2008R2,AlwaysOn",
            "file_path": "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2008R2up.sql",
            "content": ""
        },
        {
            "title": "SQL Server 2008R2+ 健康检查脚本(无SA权限)",
            "description": "SQL Server 2008R2健康检查（无SA权限版本）",
            "db_type": "SQL Server",
            "wb_type": "巡检",
            "tags": "巡检,SQLServer,健康检查,2008R2,权限受限",
            "file_path": "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2008R2up-no_sa_privileges.sql",
            "content": ""
        },
    ]

    success = 0
    fail = 0

    for script in scripts_to_import:
        # 检查文件是否存在
        if not os.path.exists(script["file_path"]):
            print(f"[SKIP] 文件不存在: {script['file_path']}")
            fail += 1
            continue

        try:
            # 使用UTF-8编码发送请求
            response = requests.post(
                f"{API_BASE}/api/scripts",
                json=script,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )

            if response.status_code == 200:
                result = response.json()
                print(f"[OK] 导入成功: {script['title']} (ID={result['id']})")
                print(f"     db_type={result['db_type']}, wb_type={result['wb_type']}")
                success += 1
            else:
                print(f"[FAIL] 导入失败: {script['title']}")
                print(f"       状态码: {response.status_code}")
                print(f"       响应: {response.text[:200]}")
                fail += 1
        except Exception as e:
            print(f"[FAIL] 导入异常: {script['title']}")
            print(f"       错误: {e}")
            fail += 1

    print("=" * 60)
    print(f"导入完成: 成功 {success}, 失败 {fail}")
    print("=" * 60)

def verify_import():
    """验证导入结果"""
    print("=" * 60)
    print("验证导入结果")
    print("=" * 60)

    response = requests.get(f"{API_BASE}/api/scripts/?page_size=20")
    if response.status_code != 200:
        print(f"[FAIL] 获取脚本列表失败")
        return

    data = response.json()
    scripts = data.get('items', [])

    print(f"总计 {len(scripts)} 个脚本:")
    print()

    for script in scripts:
        print(f"  ID={script['id']:3d}")
        print(f"    标题: {script['title']}")
        print(f"    数据库: {script['db_type']}")
        print(f"    类型: {script.get('wb_type', 'N/A')}")
        print(f"    路径: {script['file_path']}")
        print()

    print("=" * 60)

if __name__ == "__main__":
    import sys

    # 确保Python使用UTF-8
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # 执行流程
    delete_all_scripts()
    print()
    import_scripts()
    print()
    verify_import()
