import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_customer_name_order_stays_stable_after_status_edit(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    for name, status in [("Zulu 客户", "活跃"), ("Alpha 客户", "已暂停"), ("Beta 客户", "活跃"), ("Aardvark 客户", "已结束"), ("Zeta 客户", "进行中")]:
        response = client.post("/api/customers/", json={"name": name, "status": status, "project_name": "项目", "notes": "保留原始备注"}, headers={"X-CSRF-Token": csrf})
        response.raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="客户项目", exact=True).click()
            names = page.locator(".customer-identity strong")
            order = ["Aardvark 客户", "Alpha 客户", "Beta 客户", "Zeta 客户", "Zulu 客户"]
            expect(names).to_have_text(order)
            badges = page.locator(".customer-status")
            expect(badges).to_have_text(["已结束", "已暂停", "活跃", "进行中", "活跃"])
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                colors = badges.evaluate_all("badges => badges.map(badge => getComputedStyle(badge).backgroundColor)")
                assert len(set(colors)) == 4 and colors[2] == colors[4]
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"customer-status-{theme}.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            row = page.locator(".customer-entry").filter(has_text="Alpha 客户")
            row.get_by_role("button", name="查看/编辑", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("状态", exact=True).select_option("活跃")
            dialog.get_by_role("button", name="保存", exact=True).click()
            expect(dialog).to_have_count(0)
            expect(names).to_have_text(order)
            page.screenshot(animations="disabled", path=str(tmp_path / "customer-sorted.png"))
            rows = client.get("/api/customers/").json()["items"]
            detail = client.get(f"/api/customers/{rows[1]['id']}").json()
            assert detail["notes"] == "保留原始备注" and detail["status"] == "活跃"
        finally:
            browser.close()
            client.close()
