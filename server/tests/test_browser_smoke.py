from __future__ import annotations

import sqlite3
import re

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
            assert page.get_by_label("登录密码").get_attribute("minlength") == "9"
            page.get_by_label("确认密码").fill(OWNER["password"])
            page.get_by_role("button", name="创建并登录").click()
            page.get_by_role("heading", name="今天的工作台").wait_for()

            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
            page.get_by_role("button", name="新增").click()
            page.get_by_label("名称").fill("Browser smoke script")
            page.get_by_role("dialog").get_by_label("数据库", exact=True).fill("Oracle")
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
            assert page.locator('input[name="master_password"]').get_attribute("minlength") == "9"
            page.get_by_placeholder("登录密码").fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟").click()
            page.get_by_text("已验证", exact=True).wait_for()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-vault-master")
            page.get_by_label("确认主密码").fill("test-only-vault-master")
            page.get_by_role("button", name="创建保险箱").click()
            page.get_by_role("heading", name="请备份管理员恢复密钥").wait_for(timeout=20_000)
            page.get_by_role("button", name="新增条目").click()
            editor = page.get_by_role("dialog")
            assert editor.get_by_role("checkbox", name="收藏此条目").count() == 1
            assert editor.locator(".vault-switch-track").evaluate("element => getComputedStyle(element).borderRadius") == "999px"
            editor.get_by_label("名称或备注").fill("test-service")
            editor.get_by_label("账号名").fill("test-user")
            editor.get_by_label("密码").fill("test-only-vault-secret")
            editor.get_by_role("button", name="保存").click()
            page.get_by_role("heading", name="test-service").wait_for()
            assert "test-only-vault-secret" not in page.locator("body").inner_text()

            # Switching windows must not immediately discard the vault key.
            page.evaluate("""() => {
                Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'hidden'});
                document.dispatchEvent(new Event('visibilitychange'));
                Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'visible'});
                document.dispatchEvent(new Event('visibilitychange'));
                window.dispatchEvent(new Event('focus'));
            }""")
            page.get_by_role("button", name="新增条目", exact=True).wait_for()

            # Synthetic credentials only: exercise real browser encryption,
            # persisted-envelope readback and duplicate-safe retries.
            writes = []
            page.on("request", lambda request: writes.append(request.post_data or "")
                    if request.method == "POST" and request.url.endswith("/api/vault/items") else None)
            sample_csv = b'name,url,username,password\r\nCSV Example,https://csv.test,csv-user,test-only-csv-secret\r\nCSV Example,https://csv.test,csv-user,test-only-csv-secret\r\n'
            page.get_by_role("button", name="导入 Edge 密码", exact=True).click()
            page.get_by_label("选择 Edge CSV").set_input_files({"name": "sample.csv", "mimeType": "text/csv", "buffer": sample_csv})
            assert page.get_by_label("选择 Edge CSV").input_value().endswith("sample.csv")
            page.get_by_text("待导入 2 条", exact=False).wait_for()
            assert len(writes) == 0
            page.get_by_role("button", name="确认加密导入", exact=True).click()
            page.get_by_text("导入完成：新增 1 条，跳过重复 1 条", exact=False).wait_for()
            assert page.get_by_label("选择 Edge CSV").input_value() == ""
            assert len(writes) == 1
            assert "test-only-csv-secret" not in writes[0]
            assert "csv-user" not in writes[0]
            assert "ciphertext" in writes[0]
            page.get_by_role("button", name="关闭 Edge 导入", exact=True).click()
            page.get_by_role("heading", name="CSV Example", exact=True).wait_for()
            page.get_by_role("button", name="导入 Edge 密码", exact=True).click()
            page.get_by_label("选择 Edge CSV").set_input_files({"name": "sample.csv", "mimeType": "text/csv", "buffer": sample_csv})
            page.get_by_text("待导入 2 条", exact=False).wait_for()
            page.get_by_role("button", name="确认加密导入", exact=True).click()
            page.get_by_text("导入完成：新增 0 条，跳过重复 2 条", exact=False).wait_for()
            assert len(writes) == 1
            page.get_by_role("button", name="关闭 Edge 导入", exact=True).click()

            # Long imported labels must not widen grid tracks or push buttons
            # outside the card. All values below belong to the isolated test DB.
            page.get_by_role("heading", name="CSV Example", exact=True).locator("xpath=ancestor::article").get_by_role("button", name="编辑", exact=True).click()
            dialog = page.get_by_role("dialog")
            long_site = "long-service-" + "x" * 180
            long_category = "category" * 35
            dialog.get_by_label("名称或备注").fill(long_site)
            dialog.get_by_label("网址", exact=True).fill("https://example.test/" + "pathsegment/" * 30)
            dialog.get_by_label("账号名", exact=True).fill("u" * 180 + "@example.test")
            dialog.get_by_label("分类", exact=True).fill(long_category)
            dialog.get_by_label("密码", exact=True).fill("test-only-long-secret-" * 20)
            dialog.get_by_role("button", name="保存", exact=True).click()
            long_card = page.locator(".vault-card").filter(has=page.get_by_role("heading", name=long_site, exact=True))
            long_card.wait_for()
            assert long_card.locator("h3").inner_text() == long_site
            assert long_card.locator("dt").all_inner_texts() == ["网址", "账号名"]
            assert long_card.locator("dd").nth(0).inner_text().startswith("https://example.test/")
            assert long_card.locator("dd").nth(1).inner_text().endswith("@example.test")
            assert long_card.locator(".vault-card-badges").bounding_box()["x"] > long_card.locator(".vault-select").bounding_box()["x"]
            category_groups = page.get_by_role("group", name="保险箱分类分组", exact=True)
            assert category_groups.get_by_role("button", name="全部分类，2 条", exact=True).get_attribute("aria-pressed") == "true"
            long_category_button = category_groups.get_by_role("button", name=f"{long_category}，1 条", exact=True)
            assert long_category_button.get_attribute("title") == long_category
            long_category_button.click()
            assert page.locator(".vault-card").count() == 1
            category_groups.get_by_role("button", name="全部分类，2 条", exact=True).click()
            assert page.locator(".vault-card").count() == 2
            selection_style = long_card.get_by_role("checkbox", name=f"选择 {long_site}").evaluate("""element => {
                const style = getComputedStyle(element);
                return {appearance: style.appearance, minHeight: style.minHeight, boxShadow: style.boxShadow};
            }""")
            assert selection_style == {"appearance": "auto", "minHeight": "0px", "boxShadow": "none"}
            long_card.get_by_role("button", name=f"收藏 {long_site}", exact=True).click()
            long_card.get_by_role("button", name=f"取消收藏 {long_site}", exact=True).wait_for()
            assert page.locator(".vault-card h3").first.inner_text() == long_site
            long_card.get_by_role("button", name="查看", exact=True).click()
            for width in (1440, 1024, 768, 390):
                page.set_viewport_size({"width": width, "height": 1000})
                page.wait_for_timeout(180)  # Allow the card hover transition to settle.
                assert category_groups.evaluate("""group => [...group.querySelectorAll('button')].every(button => {
                    const outer = group.getBoundingClientRect();
                    const inner = button.getBoundingClientRect();
                    return inner.left >= outer.left - 1 && inner.right <= outer.right + 1;
                })"""), f"Category groups overflow at {width}px"
                assert page.locator(".vault-card").evaluate_all("""cards => cards.every(card => {
                    const box = card.getBoundingClientRect();
                    const grid = card.parentElement.getBoundingClientRect();
                    return box.right <= grid.right + 1 && card.scrollWidth <= card.clientWidth + 1 &&
                        [...card.querySelectorAll('h3, p, .badge, code, button, dd')].every(el => {
                            const r = el.getBoundingClientRect();
                            return r.left >= box.left - 1 && r.right <= box.right + 1 &&
                                (el.tagName === 'CODE' || el.scrollWidth <= el.clientWidth + 1);
                        });
                })"""), f"Vault card content overflow at {width}px"

            long_card.get_by_role("button", name="隐藏", exact=True).click()
            assert long_card.locator("code").inner_text() == "••••••••••••"
            select_all = page.get_by_role("checkbox", name="全选当前页", exact=True)
            assert select_all.evaluate("element => getComputedStyle(element).appearance") == "none"
            select_all_label = select_all.locator("xpath=ancestor::label")
            assert select_all.evaluate("element => getComputedStyle(element).width") == "16px"
            assert select_all.evaluate("element => getComputedStyle(element).height") == "16px"
            assert select_all.evaluate("element => getComputedStyle(element).padding") == "0px"
            assert select_all_label.evaluate("element => getComputedStyle(element).minHeight") == "31px"
            assert select_all_label.evaluate("element => getComputedStyle(element).borderRadius") == "7px"
            category_box = category_groups.bounding_box()
            selection_box = select_all_label.bounding_box()
            assert selection_box["y"] - (category_box["y"] + category_box["height"]) >= 8
            page.locator(".vault-card").first.locator('input[type="checkbox"]').check()
            assert not select_all.is_checked()
            assert select_all.evaluate("element => element.indeterminate") is True
            assert "has-selection" in (select_all_label.get_attribute("class") or "")
            assert "is-all-selected" not in (select_all_label.get_attribute("class") or "")
            select_all.check()
            assert select_all.evaluate("element => element.indeterminate") is False
            assert "is-all-selected" in (select_all_label.get_attribute("class") or "")
            page.get_by_text("本页已全选 2 条", exact=True).wait_for()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="删除所选", exact=True).click()
            assert page.locator(".vault-card").count() == 2
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="删除所选", exact=True).click()
            page.get_by_text("已删除 2 条密码", exact=True).wait_for()
            page.get_by_text("保险箱为空", exact=True).wait_for()

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
            page.get_by_role("combobox", name="每页条数").select_option("20")
            page.get_by_role("button", name="第 11 页", exact=True).click()
            page.get_by_text("第 11 / 11 页", exact=True).wait_for(state="attached")
            page.get_by_role("button", name="查看/编辑").first.click()
            body = page.get_by_label("脚本正文").input_value()
            assert body.startswith("body ")
            page.get_by_label("名称").fill("Edited beyond row 200")
            with page.expect_response(
                lambda response: response.request.method == "PUT" and "/api/scripts/" in response.url
            ) as update:
                page.get_by_role("dialog").get_by_role("button", name="保存").click()
            assert update.value.status == 200
            page.get_by_placeholder("按标题搜索脚本库").fill("Edited beyond row 200")
            page.get_by_text("Edited beyond row 200", exact=True).wait_for()
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(
    "module,nav_label,table,title_field,db_field,category_field,category,other_category,category_label",
    [
        ("scripts", "脚本库", "scripts", "title", "db_type", "wb_type", "巡检", "备份", "脚本类型"),
        ("articles", "知识库", "articles", "title", "wb_db", "category", "安装部署", "排障手册", "文档分类"),
        ("resources", "资源中心", "resources", "name", "wb_db", "kind", "安装包", "软件工具", ""),
    ],
)
def test_classification_filters_and_page_jump(
    live_server, isolated_app, module, nav_label, table, title_field, db_field,
    category_field, category, other_category, category_label,
) -> None:
    client, _ = _api_client(live_server)
    client.close()
    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.executemany(
            f"INSERT INTO {table} ({title_field}, {db_field}, {category_field}) VALUES (?, ?, ?)",
            [(f"classification-target-{index:03d}", "Oracle", category) for index in range(41)]
            + [(f"classification-other-{index}", "Oracle", other_category) for index in range(4)]
            + [(f"mysql-record-{index}", "MySQL", category) for index in range(2)]
            + [("custom-database-record", "达梦", category)],
        )

    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=nav_label).click()
            page.get_by_role("combobox", name="每页条数").select_option("20")
            databases = page.get_by_role("group", name="数据库分类")
            oracle = databases.get_by_role("button", name=re.compile(r"^Oracle"))
            oracle.wait_for()
            assert oracle.inner_text().splitlines()[-1] == "45"
            assert databases.get_by_role("button", name=re.compile(r"^达梦")).is_visible()
            oracle.click()
            if category_label:
                categories = page.get_by_role("group", name=category_label, exact=True)
                categories.get_by_role("button", name=re.compile("^" + category)).click()
            page.get_by_text("第 1 / 3 页", exact=True).wait_for(state="attached")
            page.get_by_role("button", name="第 3 页", exact=True).click()
            page.get_by_text("第 3 / 3 页", exact=True).wait_for(state="attached")
            page.get_by_role("combobox", name="每页条数").select_option("10")
            page.get_by_text("第 1 / 5 页", exact=True).wait_for(state="attached")
            assert oracle.get_attribute("aria-pressed") == "true"
            if category_label:
                assert categories.get_by_role("button", name=re.compile("^" + category)).get_attribute("aria-pressed") == "true"
            page.get_by_role("combobox", name="每页条数").select_option("20")
            page.get_by_text("第 1 / 3 页", exact=True).wait_for(state="attached")

            page.get_by_role("button", name="新增", exact=True).click()
            dialog = page.get_by_role("dialog")
            assert dialog.get_by_label("数据库", exact=True).input_value() == "Oracle"
            if category_label:
                label = "类型" if module == "scripts" else "分类"
                assert dialog.get_by_label(label, exact=True).input_value() == category
            dialog.get_by_role("button", name="取消", exact=True).click()

            page.get_by_placeholder("按标题搜索" + ("资源与快捷入口" if module == "resources" else nav_label)).fill("classification-target-040")
            page.get_by_text("第 1 / 1 页", exact=True).wait_for(state="attached")
            page.get_by_text("classification-target-040", exact=True).wait_for()
            assert oracle.get_attribute("aria-pressed") == "true"
            page.get_by_placeholder("按标题搜索" + ("资源与快捷入口" if module == "resources" else nav_label)).fill("")
            page.get_by_text("第 1 / 3 页", exact=True).wait_for(state="attached")
            databases.get_by_role("button", name=re.compile(r"^MySQL")).click()
            page.get_by_text("mysql-record-0", exact=True).wait_for()
            assert page.get_by_role("button", name="下一页").is_disabled()
            if category_label:
                assert page.get_by_role("group", name=category_label, exact=True).get_by_role("button", name=re.compile(r"^全部")).get_attribute("aria-pressed") == "true"

            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
            assert page.get_by_role("combobox", name="每页条数").is_visible()
            assert page.get_by_role("button", name="第 1 页", exact=True).get_attribute("aria-current") == "page"
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 800}, {"width": 390, "height": 844}])
def test_pagination_stays_visible_during_loading_and_cached_page_changes(live_server, isolated_app, viewport):
    client, _ = _api_client(live_server)
    client.close()
    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.executemany(
            "INSERT INTO scripts(title, db_type, wb_type) VALUES (?, 'Oracle', '巡检')",
            [(f"Scroll regression script {index:03d}",) for index in range(61)],
        )
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport=viewport)
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
            page.get_by_role("combobox", name="每页条数").select_option("20")
            page.get_by_text("第 1 / 4 页", exact=True).wait_for(state="attached")
            pager = page.get_by_role("navigation", name="列表分页")
            pager.scroll_into_view_if_needed()
            during_loading = []

            def delay_page_response(route):
                response = route.fetch()
                page.wait_for_timeout(350)
                during_loading.append(page.evaluate("""() => {
                    const pager = document.querySelector('.pagination');
                    const rect = pager?.getBoundingClientRect();
                    return { rows: document.querySelectorAll('tbody tr').length,
                        visible: !!rect && rect.top >= 0 && rect.bottom <= innerHeight + 2 };
                }"""))
                route.fulfill(response=response)

            page.route("**/api/scripts/?*", delay_page_response)
            for number in [2, 1, 4, 2, 4, 1]:
                pager.get_by_role("button", name=f"第 {number} 页", exact=True).click()
                page.get_by_text(f"第 {number} / 4 页", exact=True).wait_for(state="attached")
                assert page.evaluate("""() => {
                    const rect = document.querySelector('.pagination').getBoundingClientRect();
                    return rect.top >= 0 && rect.bottom <= innerHeight + 2;
                }"""), f"pagination left the viewport after selecting page {number}"
            assert during_loading
            assert all(state["rows"] > 0 and state["visible"] for state in during_loading), during_loading
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(
    "module,nav_label,path_field,open_label,open_mode",
    [("scripts", "脚本库", "file_path", "打开脚本", "edit"),
     ("articles", "知识库", "file_path", "打开文档", "open"),
     ("resources", "资源中心", "path", "打开资源", "open")],
)
def test_local_file_shortcuts_in_each_library(
    live_server, tmp_path, monkeypatch, module, nav_label, path_field, open_label, open_mode,
):
    from types import SimpleNamespace
    from backend import local_capabilities
    from backend.config import Settings
    from backend.routers import launcher

    target = tmp_path / "快捷打开 测试.sql"
    target.write_text("select 1;", encoding="utf-8")
    settings = Settings.from_env({"DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "edit,folder,open"})
    monkeypatch.setattr(local_capabilities, "settings", settings)
    monkeypatch.setattr(launcher, "settings", settings)
    monkeypatch.setattr(launcher, "EDITORS", [])
    commands, opened = [], []
    monkeypatch.setattr(launcher, "subprocess", SimpleNamespace(Popen=lambda args: commands.append(args)))
    monkeypatch.setattr(launcher.os, "startfile", lambda path: opened.append(path))
    client, csrf = _api_client(live_server)
    title_field = "name" if module == "resources" else "title"
    label = "快捷入口测试"
    response = client.post(f"/api/{module}/", headers={"X-CSRF-Token": csrf}, json={title_field: label, path_field: str(target)})
    response.raise_for_status()
    client.close()

    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: {writeText: async text => { window.__copiedPath = text; }}})")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=nav_label).click()
            page.get_by_role("button", name=f"{open_label}：{label}", exact=True).click()
            page.get_by_role("status").filter(has_text=f"已{open_label}：{label}").wait_for()
            if open_mode == "edit":
                assert commands == [["notepad.exe", str(target.resolve())]]
            else:
                assert opened == [str(target.resolve())]
            page.get_by_role("button", name=f"打开所在文件夹：{label}", exact=True).click()
            page.get_by_role("status").filter(has_text="已打开所在文件夹").wait_for()
            assert commands[-1] == ["explorer", "/select,", str(target.resolve())]
            page.get_by_role("button", name=f"复制路径：{label}", exact=True).click()
            page.get_by_role("status").filter(has_text="路径已复制").wait_for()
            assert page.evaluate("window.__copiedPath") == str(target)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        finally:
            browser.close()
