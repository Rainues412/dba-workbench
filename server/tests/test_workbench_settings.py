import pytest
import os
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge


def test_frequently_viewed_scripts_are_pinned_without_changing_search(client):
    ids = []
    for name in ("SQL test older", "SQL test newer"):
        response = client.post("/api/scripts/", json={"title": name, "db_type": "MySQL"})
        assert response.status_code == 200, response.text
        ids.append(response.json()["id"])
    older, newer = ids
    for _ in range(3):
        assert client.post(f"/api/scripts/{older}/view").status_code == 204

    assert client.get("/api/scripts/", params={"auto_pin": "1"}).json()["items"][0]["id"] == older
    assert client.get("/api/scripts/").json()["items"][0]["id"] == newer
    assert client.get("/api/scripts/", params={"auto_pin": "1", "keyword": "SQL test"}).json()["items"][0]["id"] == newer
    located = client.get("/api/scripts/", params={"auto_pin": "1", "db_type": "MySQL", "locate_id": newer, "page_size": 1})
    assert located.status_code == 200, located.text
    assert located.json()["page"] == 2
    assert located.json()["items"][0]["id"] == newer
    assert client.get("/api/scripts/recent-views").json()[0]["id"] == older


@pytest.mark.browser
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_window_startup_settings_persist_and_report_save_errors(live_server, tmp_path, monkeypatch, theme):
    import main
    from backend import auth
    from backend.desktop_settings import DesktopSettings
    from test_desktop_settings import FakeStartup

    startup = FakeStartup()
    preferences = DesktopSettings(tmp_path / "desktop-settings.json", startup)
    preferences.native_window = True
    monkeypatch.setattr(main.app.state, "desktop_settings", preferences, raising=False)
    monkeypatch.setattr(auth, "_desktop_token", "test-only-window-settings")
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1320, "height": 880})
            page.set_default_timeout(7000)
            page.add_init_script("""window.pywebview = {api: {
                minimize: async () => {}, destroy: async () => {},
                start_window_drag: async () => {}, window_is_maximized: async () => true,
                toggle_window_size: async () => false
            }}""")
            page.goto(f"{live_server}/#desktop=test-only-window-settings")
            if theme == "dark":
                page.get_by_role("button", name="切换到深色模式").click()
            page.locator(".sidebar-foot").get_by_role("button", name="设置", exact=True).click()
            dialog = page.get_by_role("dialog", name="设置", exact=True)
            dialog.get_by_role("button", name="窗口与启动", exact=True).click()
            auto = dialog.get_by_role("switch", name="开机启动", exact=True)
            silent = dialog.get_by_role("switch", name="静默启动", exact=True)
            close = dialog.get_by_role("switch", name="关闭时最小化到托盘", exact=True)
            expect(auto).not_to_be_checked()
            expect(silent).to_be_enabled()
            expect(close).to_be_checked()
            expect(dialog.get_by_role("button", name="窗口与启动", exact=True).locator(".lucide-power")).to_be_visible()
            silent.click()
            expect(silent).to_be_checked()
            expect(auto).not_to_be_checked()
            assert startup.read() is None
            auto.focus()
            auto.press("Space")
            expect(auto).to_be_checked()
            assert startup.read() == startup.command
            expect(silent).to_be_checked()
            close.click()
            expect(page.get_by_role("button", name="退出工作台", exact=True)).to_be_visible()
            expect(dialog.get_by_role("status")).to_contain_text("已保存")
            page.reload()
            page.locator(".sidebar-foot").get_by_role("button", name="设置", exact=True).click()
            dialog.get_by_role("button", name="窗口与启动", exact=True).click()
            expect(auto).to_be_checked()
            expect(silent).to_be_checked()
            expect(close).not_to_be_checked()
            close.click()
            expect(close).to_be_checked()
            expect(close).to_be_enabled()
            page.screenshot(path=str(Path(os.environ["TEMP"]) / f"window-startup-{theme}.png"))
            page.route("**/api/desktop/settings", lambda route: route.fulfill(status=503, json={"detail": "测试保存失败"}) if route.request.method == "PUT" else route.continue_())
            auto.click()
            expect(dialog.get_by_role("alert")).to_contain_text("测试保存失败")
            expect(auto).to_be_checked()
            page.unroute("**/api/desktop/settings")
            expect(auto).to_be_enabled()
            auto.click()
            expect(auto).not_to_be_checked()
            expect(silent).to_be_checked()
            expect(silent).to_be_enabled()
            assert startup.read() is None
            page.reload()
            page.locator(".sidebar-foot").get_by_role("button", name="设置", exact=True).click()
            dialog.get_by_role("button", name="窗口与启动", exact=True).click()
            expect(auto).not_to_be_checked()
            expect(silent).to_be_checked()
            page.set_viewport_size({"width": 980, "height": 640})
            assert dialog.evaluate("node => node.scrollWidth <= node.clientWidth")
            page.screenshot(path=str(Path(os.environ["TEMP"]) / f"window-startup-small-{theme}.png"))
        finally:
            browser.close()


@pytest.mark.browser
def test_forge_settings_open_from_sidebar_and_control_navigation(live_server, monkeypatch):
    from backend import auth

    monkeypatch.setattr(auth, "_desktop_token", "test-only-settings-launch")
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1520, "height": 880})
            page.goto(f"{live_server}/#desktop=test-only-settings-launch")
            sidebar = page.locator(".sidebar-foot")
            sidebar.get_by_role("button", name="设置", exact=True).click()
            settings = page.get_by_role("dialog", name="设置")
            expect(settings.get_by_role("navigation", name="设置分类").get_by_role("button")).to_have_count(7)
            expect(settings.get_by_role("searchbox", name="搜索设置")).to_be_focused()
            settings.get_by_label("界面密度").select_option("comfortable")
            expect(page.locator("html")).to_have_attribute("data-density", "comfortable")
            settings.get_by_role("switch", name="减少动态效果").check()
            expect(page.locator("html")).to_have_attribute("data-reduce-motion", "true")
            query = settings.get_by_role("searchbox", name="搜索设置")
            query.fill("锁定")
            expect(settings.get_by_role("heading", name="密码库安全")).to_be_visible()
            expect(settings.get_by_label("闲置时自动锁定")).to_have_value("15")
            settings.get_by_label("闲置时自动锁定").select_option("120")
            settings.get_by_text("密码库数据位置").click()
            expect(settings.get_by_text("0 条凭据")).to_be_visible()
            query.clear()
            settings.get_by_role("button", name="导航栏", exact=True).click()
            for position in ("right", "top", "bottom", "left"):
                settings.get_by_label("导航栏位置").select_option(position)
                expect(page.locator(f".app-shell.navigation-{position}")).to_have_count(1)
                if position == "right":
                    assert page.locator(".sidebar").evaluate("(element) => element.getBoundingClientRect().x > 1000")
                if position == "bottom":
                    assert page.locator(".sidebar").evaluate("(element) => element.getBoundingClientRect().bottom") == 880
            page.keyboard.press("Escape")
            expect(settings).to_have_count(0)
            page.get_by_role("separator", name="调整主侧边栏宽度").focus()
            page.keyboard.press("ArrowRight")
            expect(page.get_by_role("separator", name="调整主侧边栏宽度")).to_have_attribute("aria-valuenow", "230")
            page.keyboard.press("Control+,")
            expect(settings).to_be_visible()
            page.set_viewport_size({"width": 430, "height": 710})
            bounds = settings.bounding_box()
            assert bounds and bounds["width"] <= 430 and bounds["height"] <= 710
            page.keyboard.press("Escape")
            page.keyboard.press("Control+Shift+P")
            commands = page.get_by_role("dialog", name="快捷操作")
            commands.get_by_role("textbox", name="搜索快捷操作").fill("新建脚本")
            page.keyboard.press("Enter")
            editor = page.get_by_role("dialog", name="新增脚本库")
            editor.get_by_label("名称").fill("设置功能测试脚本")
            editor.locator('textarea[name="content"]').fill("select 1;\nselect 2;")
            page.keyboard.press("Control+s")
            expect(editor).to_have_count(0)
            page.get_by_role("button", name="预览：设置功能测试脚本").click()
            expect(page.locator(".script-code-viewer")).to_be_visible()
            page.keyboard.press("Control+f")
            page.get_by_label("代码内查找").fill("select")
            expect(page.get_by_text("1 / 2")).to_be_visible()
            page.keyboard.press("Enter")
            expect(page.get_by_text("2 / 2")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.get_by_label("代码内查找")).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_desktop_overlays_leave_window_controls_available_and_fill_preview(live_server, tmp_path, monkeypatch, theme):
    from backend import auth

    client, csrf = _api_client(live_server)
    created = client.post("/api/articles/", headers={"X-CSRF-Token": csrf}, json={
        "title": "预览布局验收.pdf", "file_path": str(tmp_path / "preview.pdf"),
        "wb_db": "Oracle", "category": "安装与升级",
    })
    created.raise_for_status()
    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-overlay")
    screenshots = Path(os.environ["TEMP"])
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1320, "height": 880})
            page.set_default_timeout(5000)
            page.add_init_script("""(() => {
              window.testWindowActions = [];
              window.testMaximized = true;
              const record = name => async () => { window.testWindowActions.push(name); };
              window.pywebview = {api: {
                minimize: record('minimize'), destroy: record('close'),
                start_window_drag: record('drag'),
                window_is_maximized: async () => window.testMaximized,
                toggle_window_size: async () => {
                  window.testWindowActions.push('resize');
                  window.testMaximized = !window.testMaximized;
                  return window.testMaximized;
                }
              }};
            })()""")
            page.route("**/api/articles/*/visual-preview", lambda route: route.fulfill(json={
                "filename": "预览布局验收.pdf", "viewer": "kkFileView",
                "viewer_url": "http://127.0.0.1:8012/preview-layout-fixture",
            }))
            page.route("**/preview-layout-fixture", lambda route: route.fulfill(
                content_type="text/html; charset=utf-8",
                body="<body style='margin:0;background:#eee'><header style='padding:12px;background:#ddd'>PDF 预览工具栏</header><article style='margin:20px;padding:30px;background:white;height:1800px'>隔离预览文档</article></body>",
            ))
            page.goto(f"{live_server}/#desktop=test-only-desktop-overlay")
            expect(page.locator(".desktop-window-controls")).to_be_visible()
            if theme == "dark":
                page.get_by_role("button", name="切换到深色模式").click()
            expect(page.locator("html")).to_have_attribute("data-theme", theme)
            page.locator(".sidebar").screenshot(path=str(screenshots / f"sidebar-{theme}.png"))
            account = page.locator(".user-card")
            account.screenshot(path=str(screenshots / f"account-{theme}.png"))
            account.hover()
            account.screenshot(path=str(screenshots / f"account-hover-{theme}.png"))
            page.mouse.move(300, 120)

            for shortcut, name in [("Control+,", "设置"), ("Control+Shift+P", "快捷操作")]:
                page.keyboard.press(shortcut)
                dialog = page.get_by_role("dialog", name=name, exact=True)
                expect(dialog).to_be_visible()
                assert page.locator(".app-dialog-shade").evaluate("(node) => getComputedStyle(node).clipPath") == "none"
                assert "linear-gradient" in page.locator(".app-dialog-shade").evaluate("(node) => getComputedStyle(node).maskImage")
                page.screenshot(path=str(screenshots / f"overlay-{name}-{theme}.png"))
                if name == "设置":
                    expect(dialog.get_by_role("searchbox", name="搜索设置")).to_be_focused()
                else:
                    expect(dialog.get_by_role("textbox", name="搜索快捷操作")).to_be_focused()
                dialog.screenshot(path=str(screenshots / f"{name}-{theme}.png"))
                page.get_by_role("button", name="最小化窗口").click()
                page.get_by_role("button", name="还原窗口").click()
                page.get_by_role("button", name="最大化窗口").click()
                page.get_by_role("button", name="关闭到托盘").click()
                expect(dialog).to_be_visible()
                page.mouse.click(20, 300)
                expect(dialog).to_have_count(0)
                page.keyboard.press(shortcut)
                expect(dialog).to_be_visible()
                page.keyboard.press("Escape")
                expect(dialog).to_have_count(0)
            assert page.evaluate("testWindowActions") == ["minimize", "resize", "resize", "close"] * 2

            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            page.get_by_role("button", name="预览：预览布局验收.pdf").click()
            preview = page.get_by_role("dialog", name="预览布局验收.pdf")
            frame = page.locator(".library-visual-frame")
            expect(frame).to_be_visible()
            expect(page.locator(".app-dialog-shade")).to_have_count(0)
            expect(page.frame_locator(".library-visual-frame").get_by_text("隔离预览文档")).to_be_visible()
            assert frame.bounding_box()["height"] > 500
            assert preview.bounding_box()["y"] >= page.locator(".topbar").bounding_box()["height"]
            page.screenshot(path=str(screenshots / f"preview-{theme}.png"))
            preview.get_by_role("button", name="大屏阅读", exact=True).click()
            expect(preview.get_by_role("button", name="退出大屏阅读")).to_be_visible()
            assert page.evaluate("document.fullscreenElement === null")
            page.get_by_role("button", name="最小化窗口").click()
            page.get_by_role("button", name="还原窗口").click()
            page.get_by_role("button", name="最大化窗口").click()
            for width in (980, 1600):
                page.set_viewport_size({"width": width, "height": 800})
                assert preview.bounding_box()["y"] >= 64
                assert frame.bounding_box()["height"] > 450
                page.get_by_role("button", name="关闭到托盘").click()
                expect(preview).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.get_by_role("button", name="大屏阅读", exact=True)).to_be_visible()
            # After restoring a wide layout the preview becomes a split pane.
            page.get_by_role("button", name="大屏阅读", exact=True).click()
            expect(page.locator(".desktop-expanded")).to_be_visible()
            page.get_by_role("button", name="最小化窗口").click()
            assert page.locator(".desktop-expanded").bounding_box()["y"] >= 64
            page.get_by_role("button", name="退出大屏阅读").click()
            page.get_by_role("button", name="关闭预览").click()
            expect(page.locator(".library-panels")).to_have_attribute("data-preview-open", "false")
        finally:
            browser.close()
            client.close()
