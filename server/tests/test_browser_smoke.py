from __future__ import annotations

import sqlite3

import httpx
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright


OWNER = {"username": "browser-owner", "password": "test-only-browser-passphrase"}


def _api_client(base_url: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=base_url, timeout=5)
    setup = client.post("/api/auth/setup", json=OWNER)
    setup.raise_for_status()
    return client, setup.json()["csrf_token"]


def _login(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.get_by_label("用户名").fill(OWNER["username"])
    page.get_by_label("登录密码").fill(OWNER["password"])
    page.get_by_role("button", name="登录", exact=True).click()
    page.get_by_role("heading", name="今天的工作台").wait_for()


def _edge(playwright):
    try:
        return playwright.chromium.launch(channel="msedge", headless=True)
    except PlaywrightError as error:
        pytest.skip(f"Microsoft Edge is unavailable: {error}")


@pytest.mark.browser
def test_edge_setup_crud_and_vault_starts_locked(live_server: str) -> None:
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            page.goto(live_server, wait_until="networkidle")
            assert page.title() == "DBA 工作台"
            page.get_by_label("用户名").fill(OWNER["username"])
            page.get_by_label("登录密码").fill(OWNER["password"])
            page.get_by_label("确认密码").fill(OWNER["password"])
            page.get_by_role("button", name="创建并登录").click()
            page.get_by_role("heading", name="今天的工作台").wait_for()

            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
            page.get_by_role("button", name="新增").click()
            page.get_by_label("名称").fill("Browser smoke script")
            page.get_by_label("数据库").fill("Oracle")
            page.get_by_label("脚本正文").fill("select 1 from dual;")
            page.get_by_role("dialog").get_by_role("button", name="保存").click()
            page.get_by_text("Browser smoke script", exact=True).wait_for()
            page.get_by_role("button", name="查看/编辑").click()
            assert page.get_by_label("脚本正文").input_value() == "select 1 from dual;"
            page.get_by_label("名称").fill("Browser smoke script edited")
            page.get_by_role("dialog").get_by_role("button", name="保存").click()
            page.get_by_text("Browser smoke script edited", exact=True).wait_for()

            page.get_by_role("link", name="密码保险箱").click()
            page.get_by_role("heading", name="创建新保险箱").wait_for()
            assert page.get_by_text("默认 PIN", exact=False).count() == 0
            assert page.locator('input[name="master_password"]').get_attribute("type") == "password"
            page.get_by_placeholder("登录密码").fill(OWNER["password"])
            page.get_by_role("button", name="验证 5 分钟").click()
            page.get_by_text("已验证", exact=True).wait_for()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-vault-master")
            page.get_by_label("确认主密码").fill("test-only-vault-master")
            page.get_by_role("button", name="创建保险箱").click()
            page.get_by_role("heading", name="请备份管理员恢复密钥").wait_for(timeout=20_000)
            page.get_by_role("button", name="新增条目").click()
            page.get_by_role("dialog").get_by_label("系统/网站").fill("test-service")
            page.get_by_role("dialog").get_by_label("账号").fill("test-user")
            page.get_by_role("dialog").get_by_label("密码").fill("test-only-vault-secret")
            page.get_by_role("dialog").get_by_role("button", name="保存").click()
            page.get_by_role("heading", name="test-service").wait_for()
            assert "test-only-vault-secret" not in page.locator("body").inner_text()

            page.reload(wait_until="networkidle")
            page.get_by_role("heading", name="保险箱已锁定").wait_for()
            assert "test-only-vault-secret" not in page.locator("body").inner_text()
        finally:
            browser.close()


@pytest.mark.browser
def test_user_content_is_rendered_as_text_in_react_ui(live_server: str) -> None:
    payload = '<img src=x onerror="window.__xssFired=1">'
    client, csrf = _api_client(live_server)
    try:
        response = client.post(
            "/api/scripts/",
            headers={"X-CSRF-Token": csrf},
            json={
                "title": payload,
                "description": payload,
                "db_type": "Oracle",
                "wb_type": "巡检",
                "content": "test-only-content",
            },
        )
        response.raise_for_status()
    finally:
        client.close()

    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.add_init_script("window.__xssFired = 0")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
            page.get_by_text(payload, exact=True).wait_for()
            assert page.locator('img[src="x"]').count() == 0
            assert page.evaluate("window.__xssFired") == 0
        finally:
            browser.close()


@pytest.mark.browser
def test_navigation_remains_keyboard_usable_at_narrow_200_percent_view(live_server: str) -> None:
    client, _ = _api_client(live_server)
    client.close()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 375, "height": 800})
            _login(page, live_server)
            page.evaluate("document.documentElement.style.fontSize = '200%'")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
            )
            scripts_link = page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库")
            scripts_link.focus()
            assert scripts_link.evaluate("element => element === document.activeElement")
            page.keyboard.press("Enter")
            page.get_by_role("heading", name="脚本库", exact=True).wait_for()
            assert page.get_by_role("button", name="新增").is_visible()
        finally:
            browser.close()


@pytest.mark.browser
def test_edge_can_page_to_and_edit_records_after_200(live_server: str, isolated_app) -> None:
    client, _ = _api_client(live_server)
    client.close()
    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.executemany(
            """INSERT INTO scripts (title, content, db_type, wb_type)
               VALUES (?, ?, 'Oracle', '巡检')""",
            [(f"Browser paged {index:03d}", f"body {index:03d}") for index in range(205)],
        )

    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
            for _ in range(10):
                next_button = page.get_by_role("button", name="下一页")
                if next_button.is_disabled():
                    break
                next_button.click()
                page.wait_for_load_state("networkidle")
            page.get_by_text("第 11 / 11 页", exact=True).wait_for()
            page.get_by_role("button", name="查看/编辑").first.click()
            body = page.get_by_label("脚本正文").input_value()
            assert body.startswith("body ")
            page.get_by_label("名称").fill("Edited beyond row 200")
            with page.expect_response(
                lambda response: response.request.method == "PUT" and "/api/scripts/" in response.url
            ) as update:
                page.get_by_role("dialog").get_by_role("button", name="保存").click()
            assert update.value.status == 200
            page.get_by_placeholder("搜索脚本库").fill("Edited beyond row 200")
            page.get_by_text("Edited beyond row 200", exact=True).wait_for()
        finally:
            browser.close()
