import re
from urllib.parse import quote

import pytest
from playwright.sync_api import expect, sync_playwright

from backend.database import get_db_ctx
from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_customer_directory_responsive_and_multi_owner_edit(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    name = "演示客户" * 30
    group_name = "客户协作群" * 30
    legacy = {"name": name, "group_name": group_name, "wb_contact": "企业微信", "wb_person": "统一负责人甲", "notes": "原始备注"}
    customer = client.post("/api/customers/", json=legacy, headers=headers).raise_for_status().json()
    base = f"/api/customers/{customer['id']}"
    with get_db_ctx() as conn:
        conn.execute(
            "INSERT INTO contacts (customer_id, name, phone) VALUES (?, ?, ?)",
            (customer["id"], "资源对接人", "13800000000"),
        )
        conn.execute(
            "INSERT INTO communications (customer_id, date, content) VALUES (?, ?, ?)",
            (customer["id"], "2026-10-21", "历史沟通"),
        )
        conn.commit()
    client.post("/api/tasks/", json={"title": "已有巡检", "customer_id": customer["id"]}, headers=headers).raise_for_status()
    client.post("/api/customers/", json={
        "name": "独立客户", "project_name": "电鳗", "group_name": "巡检群", "wb_contact": "微信", "wb_person": "巡检负责人",
    }, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.emulate_media(reduced_motion="reduce")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="客户项目", exact=True).click()
            single = page.locator(".customer-entry").filter(has_text="独立客户")
            single_toggle = single.locator(".customer-disclosure")
            expect(single_toggle).to_have_attribute("aria-expanded", "false")
            expect(single.get_by_text("电鳗", exact=True)).to_have_count(0)
            single_toggle.press("Enter")
            expect(single.get_by_text("电鳗", exact=True)).to_be_visible()
            expect(single.get_by_text("巡检负责人", exact=True)).to_be_visible()
            expect(single.locator(".customer-avatar")).to_have_text("独")
            entry = page.locator(".customer-entry").filter(has_text=name)
            disclosure = entry.locator(".customer-disclosure")
            expect(disclosure).to_have_count(0)
            expect(entry.get_by_text(group_name, exact=True)).to_be_visible()
            expect(entry.get_by_text("统一负责人甲", exact=True)).to_be_visible()
            entry.locator(".customer-entry-header").hover()
            expect(entry.locator(".customer-entry-header")).to_have_css("background-color", "rgb(231, 240, 255)")
            expect(entry.locator(".customer-entry-details")).to_have_count(0)
            expect(entry.get_by_text("0 个项目", exact=True)).to_have_count(0)
            entry.get_by_role("button", name="查看/编辑", exact=True).click()
            dialog = page.get_by_role("dialog")
            expect(dialog.get_by_label("客户群聊名", exact=True)).to_have_value(group_name)
            expect(dialog.get_by_label("客户群聊平台", exact=True)).to_have_value("企业微信")
            expect(dialog.get_by_text("关联联系人", exact=True)).to_have_count(0)
            expect(dialog.get_by_text("关联任务", exact=True)).to_have_count(0)
            expect(dialog.get_by_text("历史沟通", exact=True)).to_have_count(0)
            save = dialog.get_by_role("button", name="保存", exact=True)
            expect(save).to_be_in_viewport()
            for number in [7, 3, 1, 6, 2, 4, 5]:
                dialog.get_by_role("button", name="新增项目", exact=True).click()
                project = dialog.get_by_role("group", name="项目 1", exact=True)
                project_name = project.get_by_label("项目名", exact=True)
                expect(project_name).to_be_focused()
                expect(project_name).to_be_in_viewport()
                project_name.fill(f"项目 {number}")
                if number == 2:
                    project.get_by_label("项目群聊平台", exact=True).fill("飞书")
                if number == 1:
                    project.get_by_label("项目群聊名", exact=True).fill("迁移协作群")
                    project.get_by_label("项目群聊平台", exact=True).fill("钉钉")
                    for person, role in [("资源对接人", "资源开通"), ("技术对接人", "技术支持")]:
                        project.get_by_role("button", name="添加项目负责人").click()
                        project.get_by_label("负责人姓名", exact=True).last.fill(person)
                        project.get_by_label("职责标签", exact=True).last.fill(role)
            expect(save).to_be_in_viewport()
            save.click()
            expect(dialog).to_have_count(0)
            expect(disclosure).to_have_attribute("aria-expanded", "false")
            disclosure.press("Enter")
            expect(entry.get_by_role("table", name="项目清单")).to_be_visible()
            projects = entry.locator("tbody tr")
            expect(projects).to_have_count(5)
            expect(projects.locator("td:first-child")).to_have_text([f"项目 {n}" for n in range(1, 6)])
            expect(projects.first).to_contain_text("资源对接人")
            expect(projects.first).to_contain_text("技术支持")
            expect(projects.nth(1)).to_contain_text("沿用客户负责人")
            entry.get_by_role("button", name=re.compile("查看更多")).click()
            expect(projects).to_have_count(7)
            entry.get_by_role("button", name="收起", exact=True).click()
            expect(projects).to_have_count(5)
            entry.get_by_role("button", name=re.compile("查看更多")).click()
            expect(projects).to_have_count(7)
            for theme, width in [("light", 1440), ("dark", 1024), ("light", 768), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 900})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert entry.locator(".table-wrap").evaluate("element => element.scrollWidth <= element.clientWidth + 1")
                if width > 720:
                    assert projects.first.locator("td").first.evaluate("cell => getComputedStyle(cell).borderBottomWidth") == "1px"
                else:
                    assert projects.first.evaluate("row => row.nextElementSibling.offsetTop > row.offsetTop + row.offsetHeight")
                owner_summary = entry.locator(".customer-owner-summary")
                label = owner_summary.get_by_text("负责人", exact=True).bounding_box()
                owner = owner_summary.get_by_text("统一负责人甲", exact=True).bounding_box()
                assert label["x"] + label["width"] <= owner["x"]
                assert label["y"] < owner["y"] + owner["height"] and owner["y"] < label["y"] + label["height"]
                expect(single.get_by_text("电鳗", exact=True)).to_be_visible()
                assert single.locator(".table-wrap").evaluate("element => element.scrollWidth <= element.clientWidth + 1")
                badges = page.locator(".customer-platform")
                expect(badges).to_have_text(["企业微信", "钉钉", "飞书", "微信"])
                colors = badges.evaluate_all("badges => badges.map(badge => getComputedStyle(badge).backgroundColor)")
                assert len(set(colors)) == 4 and "rgba(0, 0, 0, 0)" not in colors
                role_badges = projects.first.locator(".customer-owner-role")
                expect(role_badges).to_have_text(["资源开通", "技术支持"])
                role_colors = role_badges.evaluate_all("badges => badges.map(badge => getComputedStyle(badge).backgroundColor)")
                assert len(set(role_colors)) == 1 and role_colors[0] not in [*colors, "rgba(0, 0, 0, 0)"]
                for badge in role_badges.all():
                    expect(badge).to_have_css("border-radius", "999px")
                expect(entry.locator(".customer-entry-details")).to_have_css("border-top-left-radius", "9px")
                expect(projects.nth(1).get_by_text("飞书", exact=True)).not_to_have_attribute("data-platform", re.compile(".+"))
                page.screenshot(animations="disabled", path=str(tmp_path / f"customer-directory-{theme}-{width}.png"))
                entry.get_by_role("button", name="查看/编辑", exact=True).click()
                expect(dialog.get_by_label("客户名", exact=True)).to_have_value(name)
                assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
                content = dialog.locator(".customer-edit-content")
                assert content.evaluate("element => element.scrollHeight > element.clientHeight")
                before_scroll = save.bounding_box()
                content.evaluate("element => { element.scrollTop = element.scrollHeight; }")
                assert save.bounding_box() == before_scroll
                if width == 390:
                    dialog.get_by_role("button", name="新增项目", exact=True).click()
                    added_name = dialog.get_by_role("group", name="项目 1", exact=True).get_by_label("项目名", exact=True)
                    expect(added_name).to_be_focused()
                    expect(added_name).to_be_in_viewport()
                    expect(save).to_be_in_viewport()
                    page.screenshot(animations="disabled", path=str(tmp_path / "customer-editor-narrow.png"))
                dialog.get_by_role("button", name="关闭", exact=True).click()
            saved = client.get(base).json()
            assert all(saved[field] == value for field, value in legacy.items())
            assert [contact["name"] for contact in saved["contacts"]] == ["资源对接人"]
            with get_db_ctx() as conn:
                communications = conn.execute("SELECT customer_id, content FROM communications").fetchall()
            assert [tuple(row) for row in communications] == [(customer["id"], "历史沟通")]
            tasks = client.get("/api/tasks/").raise_for_status().json()["items"]
            assert [(row["customer_id"], row["title"]) for row in tasks] == [(customer["id"], "已有巡检")]
            assert [project["name"] for project in saved["project_profile"]["projects"]] == [f"项目 {n}" for n in range(1, 8)]

            search = page.get_by_role("textbox", name="搜索客户名或项目名")
            for query in ("电", "电鳗"):
                with page.expect_response(lambda response: "/api/customers/?" in response.url and response.request.method == "GET"
                                          and response.status == 200 and response.url.endswith(f"keyword={quote(query)}")):
                    search.fill(query)
                expect(single_toggle).to_have_attribute("aria-expanded", "true")
                expect(single.get_by_text("电鳗", exact=True)).to_be_visible()
                expect(entry).to_have_count(0)
            search.fill("项目 7")
            expect(entry.get_by_text("项目 7", exact=True)).to_be_visible()
            expect(projects).to_have_count(1)
            expect(single).to_have_count(0)
            project_edit = entry.get_by_role("button", name="编辑项目 项目 7", exact=True)
            project_edit.press("Enter")
            quick_dialog = page.get_by_role("dialog", name="编辑项目")
            name_field = quick_dialog.get_by_label("项目名", exact=True)
            expect(name_field).to_have_value("项目 7")
            expect(name_field).to_be_focused()
            expect(quick_dialog.get_by_label("客户名", exact=True)).to_have_count(0)
            expect(quick_dialog.get_by_role("button", name="保存", exact=True)).to_be_in_viewport()
            expect(quick_dialog.get_by_text(name, exact=True)).to_have_attribute("title", name)
            assert quick_dialog.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
            page.screenshot(animations="disabled", path=str(tmp_path / "quick-project-edit-dark-390.png"))
            name_field.press("Escape")
            expect(quick_dialog).to_have_count(0)
            expect(project_edit).to_be_focused()

            project_edit.click()
            quick_dialog.get_by_label("项目群聊名", exact=True).fill("项目七专属群")
            quick_dialog.get_by_role("button", name="保存", exact=True).click()
            expect(quick_dialog).to_have_count(0)
            expect(projects.get_by_text("项目七专属群", exact=True)).to_be_visible()
            expect(search).to_have_value("项目 7")
            updated = client.get(base).raise_for_status().json()
            expected_projects = saved["project_profile"]["projects"]
            expected_projects[-1]["chat"]["name"] = "项目七专属群"
            assert updated["project_profile"] == saved["project_profile"]
            assert all(updated[field] == value for field, value in legacy.items())

            project_edit.click()
            expect(name_field).to_have_value("项目 7")
            client.put(base, json={"notes": "其他窗口刚更新"}, headers={**headers, "If-Match": str(updated["revision"])}).raise_for_status()
            name_field.fill("项目七新名称")
            quick_dialog.get_by_role("button", name="保存", exact=True).click()
            expect(quick_dialog.get_by_role("alert")).to_contain_text("已在其他窗口更新")
            expect(name_field).to_have_value("项目七新名称")
            assert client.get(base).raise_for_status().json()["project_profile"] == saved["project_profile"]
            quick_dialog.get_by_role("button", name="取消", exact=True).click()
            project_edit.click()
            expect(quick_dialog.get_by_label("项目名", exact=True)).to_have_count(0)
            with page.expect_response(lambda response: "/api/customers/?" in response.url and response.status == 200):
                quick_dialog.get_by_role("button", name="刷新清单", exact=True).click()
            expect(quick_dialog).to_have_count(0)
            expect(search).to_have_value("项目 7")
            search.fill("独立客户")
            expect(single_toggle).to_have_attribute("aria-expanded", "false")
            expect(entry).to_have_count(0)

            global_search = page.get_by_role("combobox", name="跨模块搜索关键词")
            global_search.fill("项目 6")
            result = page.get_by_role("option", name=f"项目 6 {name} 项目")
            expect(result.locator(".global-search-result-customer")).to_have_text(name)
            result.click()
            drawer = page.get_by_role("dialog", name="项目 6")
            expect(drawer.get_by_text("沿用客户负责人", exact=True)).to_be_visible()
            expect(drawer.get_by_text("统一负责人甲", exact=True)).to_be_visible()
            page.screenshot(animations="disabled", path=str(tmp_path / "project-search-drawer-dark-390.png"))
            drawer.get_by_role("button", name="关闭项目详情").press("Escape")
            expect(drawer).to_have_count(0)
            expect(search).to_have_value("独立客户")
            expect(search).to_be_focused()
            expect(single).to_be_visible()
            expect(entry).to_have_count(0)

            # The target is on page two and below the collapsed five-project limit.
            for index in range(10):
                client.post("/api/customers/", json={"name": f"Seed {index}"}, headers=headers).raise_for_status()
            page.reload()
            expect(search).to_have_value("")
            expect(page.locator(".customer-entry")).to_have_count(10)
            global_search.fill("项目 6")
            result.click()
            expect(entry.get_by_text("项目 6", exact=True)).to_be_visible()
            expect(entry.get_by_text("项目 6", exact=True)).to_be_in_viewport()
            expect(projects).to_have_count(7)
            expect(single).to_be_visible()
            expect(page.get_by_role("button", name="第 2 页", exact=True)).to_have_attribute("aria-current", "page")
            expect(search).to_have_value("")
            expect(page.get_by_role("dialog")).to_have_count(0)
            located = projects.filter(has=page.get_by_text("项目 6", exact=True))
            expect(located).to_have_attribute("aria-current", "true")
            expect(located.get_by_text("已定位", exact=True)).to_have_count(0)
            assert located.evaluate("row => getComputedStyle(row).backgroundColor !== getComputedStyle(row.previousElementSibling).backgroundColor")
            page.screenshot(animations="disabled", path=str(tmp_path / "project-location-dark-390.png"))
            page.set_viewport_size({"width": 1440, "height": 900})
            page.evaluate("document.documentElement.dataset.theme = 'light'")
            expect(located).to_have_attribute("aria-current", "true")
            located.scroll_into_view_if_needed()
            expect(page.get_by_role("button", name="取消高亮", exact=True)).to_have_count(0)
            nearby = projects.nth(4)
            nearby.hover()
            for theme, hover_color, heading_color, location_color in [
                ("light", "rgb(231, 240, 255)", "rgb(238, 240, 244)", "rgb(240, 233, 255)"),
                ("dark", "rgb(28, 54, 82)", "rgb(42, 48, 58)", "rgb(55, 39, 73)"),
            ]:
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                header = entry.locator(".customer-entry-header")
                header.hover()
                expect(header).to_have_css("background-color", hover_color)
                page.screenshot(animations="disabled", path=str(tmp_path / f"customer-hover-{theme}-1440.png"))
                nearby.hover()
                expect(header).to_have_css("background-color", "rgba(0, 0, 0, 0)")
                expect(nearby).to_have_css("background-color", hover_color)
                expect(entry.get_by_role("columnheader", name="项目名")).to_have_css("background-color", heading_color)
                located.hover()
                expect(located).to_have_css("background-color", location_color)
                nearby.hover()
                expect(nearby).to_have_css("background-color", hover_color)
                page.screenshot(animations="disabled", path=str(tmp_path / f"project-row-colors-{theme}-1440.png"))
            expect(located).to_have_attribute("aria-current", "true")
            nearby.get_by_text("项目 5", exact=True).click()
            expect(projects.locator("[aria-current=true]")).to_have_count(0)
            expect(located).to_be_visible()
            expect(projects).to_have_count(7)
            expect(search).to_have_value("")
            expect(page.get_by_role("button", name="第 2 页", exact=True)).to_have_attribute("aria-current", "page")

            global_search.click()
            result.click()
            expect(located).to_have_attribute("aria-current", "true")
            entry.get_by_role("button", name="查看/编辑", exact=True).click()
            expect(dialog.get_by_label("客户名", exact=True)).to_have_value(name)
            expect(projects.locator("[aria-current=true]")).to_have_count(0)
        finally:
            browser.close()
            client.close()
