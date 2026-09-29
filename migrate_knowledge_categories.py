#!/usr/bin/env python3
"""
知识库分类迁移脚本
将旧分类映射到新分类体系，并根据文档内容自动分配新增类型
"""
import requests
import json

API = "http://localhost:8686"

# 旧分类到新分类的映射
CATEGORY_MAP = {
    '运维规范': '巡检规范',
    '学习记录': '学习笔记',
}

# 根据关键词自动分配新增类型
KEYWORD_TYPE_MAP = {
    '备份恢复': ['备份', '恢复', 'RMAN', 'xtrabackup', 'mydumper', 'mysqldump', 'PITR', '归档'],
    '安装部署': ['安装', '部署', '一键安装', '静默安装', '部署脚本'],
    '安全加固': ['安全', '加固', '安测', 'Wallet', '加密', '权限'],
}

def classify_article(article):
    """根据标题和摘要智能分类"""
    text = (article.get('title', '') + ' ' + article.get('summary', '')).lower()

    for new_type, keywords in KEYWORD_TYPE_MAP.items():
        for kw in keywords:
            if kw.lower() in text:
                return new_type

    return None

def main():
    print("正在连接服务器...")
    try:
        response = requests.get(f"{API}/api/articles/?page_size=1000", timeout=5)
        response.raise_for_status()
        articles = response.json().get("items", [])
    except Exception as e:
        print(f"❌ 无法连接服务器: {e}")
        print("请确保 server/main.py 已启动 (python server/main.py)")
        return

    print(f"✓ 找到 {len(articles)} 篇文档\n")

    updated = 0
    skipped = 0

    for article in articles:
        article_id = article['id']
        old_cat = article.get('category', '')
        title = article.get('title', '')

        # 1. 先尝试映射旧分类
        if old_cat in CATEGORY_MAP:
            new_cat = CATEGORY_MAP[old_cat]
            print(f"  [{article_id}] {title}")
            print(f"    {old_cat} → {new_cat}")

            try:
                r = requests.put(f"{API}/api/articles/{article_id}", json={"category": new_cat})
                r.raise_for_status()
                updated += 1
            except Exception as e:
                print(f"    ❌ 更新失败: {e}")
            continue

        # 2. 尝试智能分类（仅对未分类或旧分类）
        if old_cat in ['学习记录', '运维规范', ''] or old_cat not in [
            '排障手册', '备份恢复', '安装部署', '架构设计',
            '性能调优', '安全加固', '迁移方案', '巡检规范', '学习笔记'
        ]:
            new_cat = classify_article(article)
            if new_cat:
                print(f"  [{article_id}] {title}")
                print(f"    {old_cat or '未分类'} → {new_cat} (自动识别)")

                try:
                    r = requests.put(f"{API}/api/articles/{article_id}", json={"category": new_cat})
                    r.raise_for_status()
                    updated += 1
                except Exception as e:
                    print(f"    ❌ 更新失败: {e}")
                continue

        skipped += 1

    print(f"\n{'='*50}")
    print(f"✓ 已更新: {updated} 篇")
    print(f"○ 已跳过: {skipped} 篇 (分类无需变更)")
    print(f"{'='*50}")

    if updated > 0:
        print("\n建议: 刷新前端页面查看新的三级导航效果")

if __name__ == '__main__':
    main()
