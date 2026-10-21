import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
@pytest.mark.parametrize("module,name", [
    ("scripts", "脚本库"), ("articles", "知识库"), ("resources", "资源中心"),
])
def test_favorite_checkbox_style_and_keyboard_filter(live_server, tmp_path, module, name):
    client, csrf = _api_client(live_server)
    title_field = "name" if module == "resources" else "title"
    headers = {"X-CSRF-Token": csrf}
    favorite = client.post(f"/api/{module}/", json={title_field: "收藏记录"}, headers=headers)
    favorite.raise_for_status()
    row = favorite.json()
    updated = client.put(f"/api/{module}/{row['id']}", json={"is_favorite": 1}, headers={**headers, "If-Match": str(row["revision"])})
    updated.raise_for_status()
    row = updated.json()
    client.post(f"/api/{module}/", json={title_field: "普通记录"}, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=name, exact=True).click()
            checkbox = page.get_by_role("checkbox", name="只看收藏", exact=True)
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                expect(page.get_by_text("普通记录", exact=True)).to_be_visible()
                page.get_by_role("heading", level=1).click()
                checkbox.click()
                expect(checkbox).to_be_checked()
                expect(page.get_by_text("普通记录", exact=True)).to_have_count(0)
                expect(page.get_by_text("收藏记录", exact=True)).to_be_visible()
                checkbox.hover()
                style = checkbox.evaluate("""element => {
                    const style = getComputedStyle(element);
                    return {width: style.width, height: style.height, minHeight: style.minHeight,
                        padding: style.padding, boxShadow: style.boxShadow, outlineWidth: style.outlineWidth};
                }""")
                assert style == {"width": "16px", "height": "16px", "minHeight": "0px", "padding": "0px", "boxShadow": "none", "outlineWidth": "0px"}
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                checkbox.scroll_into_view_if_needed()
                page.screenshot(path=str(tmp_path / f"{module}-{theme}-{width}.png"))
                # Tab reaches the filter from the title search; Space still toggles it.
                page.get_by_role("textbox", name=f"按标题搜索{'资源与快捷入口' if module == 'resources' else name}").focus()
                page.keyboard.press("Tab")
                expect(checkbox).to_be_focused()
                assert checkbox.evaluate("element => getComputedStyle(element).outlineWidth") == "2px"
                checkbox.press("Space")
                expect(checkbox).not_to_be_checked()
            updated = client.put(f"/api/{module}/{row['id']}", json={"is_favorite": 0}, headers={**headers, "If-Match": str(row["revision"])})
            updated.raise_for_status()
            page.reload(wait_until="networkidle")
            checkbox.check()
            expect(page.get_by_text(f"没有{'资源与快捷入口' if module == 'resources' else name}数据", exact=True)).to_be_visible()
            assert checkbox.bounding_box()["height"] == 16
        finally:
            browser.close()
            client.close()
