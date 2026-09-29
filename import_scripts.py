#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入脚本到DBA工作台脚本库
分类: Oracle巡检/备份/部署, MySQL巡检, SQL Server巡检
"""

import requests
import json
import os

API_BASE = "http://localhost:8686"

# 脚本数据定义
SCRIPTS_TO_IMPORT = [
    # Oracle 巡检脚本
    {
        "title": "Oracle 10g 健康检查脚本",
        "description": "Oracle 10g数据库全面健康检查,包含实例状态、表空间、用户、性能指标等关键检查项",
        "db_type": "Oracle",
        "wb_type": "巡检",
        "tags": "巡检,Oracle,健康检查,10g",
        "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_10g.sql",
        "content": ""
    },
    {
        "title": "Oracle 11g 健康检查脚本",
        "description": "Oracle 11g数据库全面健康检查,支持ASM、RAC环境,包含详细的性能分析和优化建议",
        "db_type": "Oracle",
        "wb_type": "巡检",
        "tags": "巡检,Oracle,健康检查,11g,ASM,RAC",
        "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_11g.sql",
        "content": ""
    },
    {
        "title": "Oracle 11g 简化版健康检查脚本",
        "description": "Oracle 11g数据库快速健康检查,适用于日常巡检,输出简洁的检查报告",
        "db_type": "Oracle",
        "wb_type": "巡检",
        "tags": "巡检,Oracle,健康检查,11g,简化版",
        "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_11g_simple.sql",
        "content": ""
    },
    {
        "title": "Oracle 12c 健康检查脚本",
        "description": "Oracle 12c数据库全面健康检查,支持多租户架构(CDB/PDB),包含容器数据库检查",
        "db_type": "Oracle",
        "wb_type": "巡检",
        "tags": "巡检,Oracle,健康检查,12c,CDB,PDB",
        "file_path": "D:/Database/数据库巡检脚本/DB_Oracle_HC_12c.sql",
        "content": ""
    },
    {
        "title": "Oracle 11g 数据库检查脚本",
        "description": "Oracle 11g数据库专项检查,聚焦核心指标和常见问题诊断",
        "db_type": "Oracle",
        "wb_type": "巡检",
        "tags": "巡检,Oracle,健康检查,11g,诊断",
        "file_path": "D:/Database/数据库巡检脚本/dbcheck11g.sql",
        "content": ""
    },
    {
        "title": "Oracle DG 检查脚本",
        "description": "Oracle Data Guard环境检查,验证主备库同步状态、日志应用情况、角色切换准备情况",
        "db_type": "Oracle",
        "wb_type": "巡检",
        "tags": "巡检,Oracle,DG,DataGuard,主备同步",
        "file_path": "D:/Database/oracle/dg/检查脚本/dgsql.txt",
        "content": ""
    },

    # Oracle 备份脚本
    {
        "title": "Windows RMAN 自动备份脚本 0",
        "description": "Windows环境下的Oracle RMAN自动备份脚本,支持定时执行、日志记录,适用于生产环境备份自动化",
        "db_type": "Oracle",
        "wb_type": "备份",
        "tags": "备份,Oracle,RMAN,Windows,自动化",
        "file_path": "D:/Database/oracle/rman/windows rman自动备份部署/rmanbackup0.bat",
        "content": ""
    },
    {
        "title": "Windows RMAN 自动备份脚本 1",
        "description": "Windows环境下的Oracle RMAN增量备份脚本,配合rmanbackup0.bat实现完整备份策略",
        "db_type": "Oracle",
        "wb_type": "备份",
        "tags": "备份,Oracle,RMAN,Windows,增量备份",
        "file_path": "D:/Database/oracle/rman/windows rman自动备份部署/rmanbackup1.bat",
        "content": ""
    },

    # Oracle 部署脚本
    {
        "title": "Oracle Wallet 配置向导脚本",
        "description": "一键配置Oracle Wallet,自动设置sqlnet.ora、初始化钱包、管理凭证,支持新建和修改凭证模式",
        "db_type": "Oracle",
        "wb_type": "部署",
        "tags": "部署,Oracle,Wallet,安全,凭证管理",
        "file_path": "D:/Database/oracle/脚本/Wallet/setup_wallet.sh",
        "content": ""
    },

    # MySQL 巡检脚本
    {
        "title": "MySQL 健康检查报告脚本",
        "description": "MySQL数据库全面健康检查,生成HTML格式巡检报告,包含实例状态、性能指标、慢查询分析、表空间使用率等",
        "db_type": "MySQL",
        "wb_type": "巡检",
        "tags": "巡检,MySQL,健康检查,HTML报告,性能分析",
        "file_path": "D:/Database/数据库巡检脚本/DB_MySQL_HC.sql",
        "content": ""
    },

    # SQL Server 巡检脚本
    {
        "title": "SQL Server 2005+ 健康检查脚本",
        "description": "SQL Server 2005及以上版本健康检查,包含数据库状态、性能计数器、等待统计、索引碎片分析",
        "db_type": "SQL Server",
        "wb_type": "巡检",
        "tags": "巡检,SQLServer,健康检查,2005,性能分析",
        "file_path": "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2005up.sql",
        "content": ""
    },
    {
        "title": "SQL Server 2008R2+ 健康检查脚本",
        "description": "SQL Server 2008R2及以上版本健康检查,支持新特性检查,包含AlwaysOn、压缩、资源调控器等",
        "db_type": "SQL Server",
        "wb_type": "巡检",
        "tags": "巡检,SQLServer,健康检查,2008R2,AlwaysOn",
        "file_path": "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2008R2up.sql",
        "content": ""
    },
    {
        "title": "SQL Server 2008R2+ 健康检查脚本(无SA权限)",
        "description": "SQL Server 2008R2及以上版本健康检查,适用于无SA权限的环境,使用普通用户权限执行检查",
        "db_type": "SQL Server",
        "wb_type": "巡检",
        "tags": "巡检,SQLServer,健康检查,2008R2,权限受限",
        "file_path": "D:/Database/数据库巡检脚本/DB_SQLServer_HC_2008R2up-no_sa_privileges.sql",
        "content": ""
    }
]

def import_scripts():
    """导入脚本到DBA工作台"""
    print("=" * 60)
    print("开始导入脚本到DBA工作台")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for script in SCRIPTS_TO_IMPORT:
        try:
            # 检查文件是否存在
            if not os.path.exists(script["file_path"]):
                print(f"[FAIL] 文件不存在: {script['file_path']}")
                fail_count += 1
                continue

            # 读取文件内容
            fpath = script["file_path"]
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                content = ""
            script["content"] = content

            # 调用API创建脚本（确保UTF-8编码）
            response = requests.post(
                f"{API_BASE}/api/scripts",
                json=script,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )

            if response.status_code == 200:
                print(f"[OK] 导入成功: {script['title']}")
                success_count += 1
            else:
                print(f"[FAIL] 导入失败: {script['title']} - {response.text}")
                fail_count += 1

        except Exception as e:
            print(f"[FAIL] 导入异常: {script['title']} - {str(e)}")
            fail_count += 1

    print("=" * 60)
    print(f"导入完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    print("=" * 60)

if __name__ == "__main__":
    import_scripts()
