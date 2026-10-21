import re

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_customer_layout_and_related_forms_preserve_business_data(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    name = "客户名称" * 30
    project = "数据库高可用建设项目" * 12
    contact = "customer-contact-" * 12 + "@example.test"
    payload = {"name": name, "project_name": project, "group_name": "重点项目组", "status": "进行中", "wb_person": "项目负责人", "wb_contact": contact, "notes": "客户原始备注\n第二行内容"}
    response = client.post("/api/customers/", json=payload, headers=headers)
    response.raise_for_status()
    customer = response.json()
    base = f"/api/customers/{customer['id']}"
    client.post(f"{base}/contacts", json={"name": "技术联系人", "role": "DBA", "phone": "13800000000", "wechat": "wechat-" * 20, "notes": "联系人说明" * 20}, headers=headers).raise_for_status()
    client.post(f"{base}/communications", json={"date": "2026-10-21", "content": "需求确认\n" + "沟通内容" * 40, "follow_up": "下周回访"}, headers=headers).raise_for_status()
    client.post("/api/tasks/", json={"title": "客户关联巡检" * 10, "customer_id": customer["id"]}, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="客户项目", exact=True).click()
            expect(page.get_by_role("heading", name="客户项目", exact=True)).to_be_visible()
            expect(page.get_by_text("重点项目组", exact=True)).to_be_visible()
            expect(page.locator(".customer-copy small").filter(has_text=contact)).to_have_attribute("title", contact)
            expect(page.locator(".customer-identity strong")).to_have_attribute("title", name)
            for theme in ("light", "dark"):
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                for width in (1440, 1024, 768, 390):
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(animations="disabled", path=str(tmp_path / f"customers-{theme}-{width}.png"))
                    page.get_by_role("button", name="查看/编辑", exact=True).click()
                    dialog = page.get_by_role("dialog")
                    expect(dialog.get_by_label("客户", exact=True)).to_have_value(name)
                    expect(dialog.get_by_role("group", name="负责人信息")).to_be_visible()
                    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
                    page.screenshot(animations="disabled", path=str(tmp_path / f"customer-form-{theme}-{width}.png"))
                    contacts = dialog.get_by_role("region", name=re.compile("^关联联系人"))
                    communications = dialog.get_by_role("region", name=re.compile("^沟通记录"))
                    contacts.scroll_into_view_if_needed()
                    left, right = contacts.bounding_box(), communications.bounding_box()
                    if width > 720:
                        assert abs(left["y"] - right["y"]) < 2 and right["x"] > left["x"]
                    else:
                        assert right["y"] > left["y"]
                    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
                    expect(dialog.get_by_role("link", name=re.compile("客户关联巡检"))).to_have_attribute("href", re.compile(r"/tasks\?record=\d+"))
                    page.screenshot(animations="disabled", path=str(tmp_path / f"customer-relations-{theme}-{width}.png"))
                    dialog.get_by_role("button", name="关闭", exact=True).click()
            page.get_by_role("button", name="查看/编辑", exact=True).click()
            dialog = page.get_by_role("dialog")
            contacts = dialog.get_by_role("region", name=re.compile("^关联联系人"))
            contacts.get_by_role("button", name="新增联系人", exact=True).click()
            contacts.get_by_label("姓名", exact=True).fill("新增业务联系人")
            contacts.get_by_label("电话", exact=True).fill("13900000000")
            contacts.get_by_role("button", name="保存联系人", exact=True).click()
            expect(contacts.get_by_text("新增业务联系人", exact=True)).to_be_visible()
            communications = dialog.get_by_role("region", name=re.compile("^沟通记录"))
            communications.get_by_role("button", name="新增沟通记录", exact=True).click()
            communications.get_by_label("日期", exact=True).fill("2026-10-21")
            communications.get_by_label("沟通内容", exact=True).fill("新的沟通内容")
            communications.get_by_label("后续跟进", exact=True).fill("继续验证布局")
            communications.get_by_role("button", name="保存沟通记录", exact=True).click()
            expect(communications.get_by_text("新的沟通内容", exact=True)).to_be_visible()
            dialog.get_by_label("负责人", exact=True).fill("新的负责人")
            dialog.get_by_role("button", name="保存", exact=True).click()
            expect(dialog).to_have_count(0)
            saved = client.get(base).json()
            for field, value in payload.items():
                assert saved[field] == ("新的负责人" if field == "wb_person" else value)
            assert len(saved["contacts"]) == 2 and len(saved["communications"]) == 2 and len(saved["tasks"]) == 1
            assert saved["revision"] == customer["revision"] + 1
        finally:
            browser.close()
            client.close()
