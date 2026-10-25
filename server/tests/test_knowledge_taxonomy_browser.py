"""Validate the approved knowledge taxonomy against the actual production bundle."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


CATEGORIES = [
    "原理与SQL", "安装与升级", "日常管理", "备份与恢复", "高可用与同步", "故障排查", "性能优化",
    "安全与权限", "迁移与改造", "监控与巡检", "规范与应急", "工具与环境", "综合资料", "待确认",
]
OLD_CATEGORIES = ["技术文档", "排障手册", "安装部署", "备份恢复", "架构设计", "性能调优", "安全加固", "迁移方案", "巡检规范", "学习笔记", "学习记录"]


def test_new_articles_without_a_category_need_review(client):
    response = client.post("/api/articles/", json={"title": "未指定主题的新文档"})
    assert response.status_code == 200
    row = response.json()
    assert row["category"] == "待确认"
    assert client.get("/api/articles/", params={"category": "待确认"}).json()["total"] == 1


@pytest.mark.browser
def test_knowledge_topics_platforms_and_preview(live_server, tmp_path, monkeypatch):
    from backend import local_capabilities
    from backend.config import Settings

    # Preview only an explicitly allowed synthetic file, never the user's database or documents.
    source = tmp_path / "主题分类验证.md"
    source.write_text("# 主题阅读验证\n\n## 章节\n\n原文件预览保持正常。", encoding="utf-8")
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_MODE": "local", "DBA_OPEN_BROWSER": "false", "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "check,open,folder",
    }))
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    for category in CATEGORIES:
        platform = "Windows" if category == "工具与环境" else "MongoDB" if category == "高可用与同步" else "Oracle"
        client.post("/api/articles/", json={
            "title": f"{category}验证记录", "wb_db": platform, "category": category,
            "file_path": str(source), "tags": "自定义保留标签,操作手册",
        }, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            categories = page.get_by_role("group", name="文档分类", exact=True)
            expect(categories.get_by_role("button")).to_have_count(15)
            for category in CATEGORIES:
                expect(categories.get_by_role("button", name=category + " 1", exact=True)).to_be_visible()
            for category in OLD_CATEGORIES:
                expect(categories.get_by_role("button", name=category + " 0", exact=True)).to_have_count(0)

            _select_database(page, "Oracle")
            expect(categories.get_by_role("button")).to_have_count(13)
            expect(categories.get_by_role("button", name="高可用与同步 0", exact=True)).to_have_count(0)
            expect(categories.get_by_role("button", name="工具与环境 0", exact=True)).to_have_count(0)
            _select_database(page, "MongoDB")
            expect(categories.get_by_role("button")).to_have_count(2)
            categories.get_by_role("button", name="高可用与同步 1", exact=True).click()
            title = page.get_by_role("button", name="预览：高可用与同步验证记录", exact=True)
            expect(title).to_be_enabled()
            title.click()
            preview = page.get_by_role("complementary", name="记录预览")
            expect(preview.get_by_role("heading", name="高可用与同步验证记录", exact=True)).to_be_visible()
            expect(preview.locator(".library-markdown")).to_contain_text("原文件预览保持正常。")
            expect(preview.get_by_role("button", name="打开文档：高可用与同步验证记录", exact=True)).to_be_visible()
            expect(preview.get_by_role("button", name="打开所在文件夹：高可用与同步验证记录", exact=True)).to_be_visible()

            for theme, width in [("light", 1440), ("dark", 1440), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                _select_database(page, "Windows")
                categories.get_by_role("button", name="工具与环境 1", exact=True).click()
                expect(page.get_by_role("button", name="预览：工具与环境验证记录", exact=True)).to_be_visible()
                page.reload(wait_until="networkidle")
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                expect(page.locator("html")).to_have_attribute("data-theme", theme)
                expect(categories.get_by_role("button", name="工具与环境 1", exact=True)).to_have_attribute("aria-pressed", "true")
                expect(categories.get_by_role("button")).to_have_count(2)
                expect(page.get_by_role("combobox", name="筛选数据库")).to_have_attribute("title", "Windows（1）")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(tmp_path / f"knowledge-taxonomy-{theme}-{width}.png"), animations="disabled")
            page.set_viewport_size({"width": 1440, "height": 1000})
            _select_database(page, "Windows")
            expect(categories.get_by_role("button", name="安全与权限 0", exact=True)).to_have_count(0)
            page.get_by_role("button", name="新增", exact=True).click()
            editor = page.get_by_role("dialog")
            editor.get_by_label("标题", exact=True).fill("Windows安全分类首篇文章")
            editor.get_by_label("分类", exact=True).select_option("安全与权限")
            editor.get_by_role("button", name="保存", exact=True).click()
            # CrudPage invalidates facets on save; this must appear without reload or new configuration.
            expect(categories.get_by_role("button", name="安全与权限 1", exact=True)).to_be_visible()
            expect(categories.get_by_role("button")).to_have_count(3)
            categories.get_by_role("button", name="安全与权限 1", exact=True).click()
            record = page.locator(".library-record").filter(has_text="Windows安全分类首篇文章")
            record.get_by_label("更多操作：Windows安全分类首篇文章").click()
            page.once("dialog", lambda dialog: dialog.accept())
            record.get_by_role("button", name="删除记录", exact=True).click()
            # The last article was removed; the same topic must disappear automatically.
            expect(categories.get_by_role("button", name="安全与权限 1", exact=True)).to_have_count(0)
            expect(categories.get_by_role("button", name="安全与权限 0", exact=True)).to_have_count(0)
            expect(categories.get_by_role("button")).to_have_count(2)
            page.screenshot(path=str(tmp_path / "knowledge-category-after-last-delete.png"), animations="disabled")
            page.get_by_role("button", name="清除分类", exact=True).click()
            page.get_by_role("button", name="新增", exact=True).click()
            dialog = page.get_by_role("dialog")
            category = dialog.get_by_label("分类", exact=True)
            expect(category).to_have_value("待确认")
            assert category.locator("option").all_text_contents() == CATEGORIES
            page.screenshot(path=str(tmp_path / "knowledge-taxonomy-new-article.png"), animations="disabled")
        finally:
            browser.close()
            client.close()
