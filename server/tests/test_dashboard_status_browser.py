"""Dashboard status badges against real API data in an isolated database."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_dashboard_preserves_status_and_overdue_labels(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    rows = []
    for status in ("待处理", "进行中"):
        for overdue in (False, True):
            title = f"{status}任务{'（逾期）' if overdue else '（无截止日期）'}"
            response = client.post("/api/tasks/", headers={"X-CSRF-Token": csrf}, json={
                "title": title, "status": status, "priority": "低" if status == "待处理" and overdue else "高",
                "due_date": "2000-01-01" if overdue else None,
            })
            response.raise_for_status()
            rows.append((title, status, overdue, response.json()["id"]))
    completed = client.post("/api/tasks/", headers={"X-CSRF-Token": csrf}, json={
        "title": "已完成不显示", "status": "已完成",
    })
    completed.raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            queue = page.get_by_role("list", name="未完成任务列表")
            expect(queue.get_by_role("listitem")).to_have_count(4)
            expect(queue.locator(".task-copy strong")).to_have_text([rows[index][0] for index in (3, 1, 2, 0)])
            expect(queue.get_by_text("已完成不显示", exact=True)).to_have_count(0)
            for width, theme in [(1440, "light"), (1440, "dark"), (390, "light"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                for title, status, overdue, _ in rows:
                    row = queue.get_by_role("listitem").filter(has=page.get_by_text(title, exact=True))
                    expect(row.get_by_text(status, exact=True)).to_be_visible()
                    expect(row.get_by_text("已逾期", exact=True)).to_have_count(int(overdue))
                    if status == "进行中":
                        assert "status-info" in row.get_by_text(status, exact=True).get_attribute("class")
                    assert row.locator("strong").get_attribute("title") == title
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert queue.evaluate("""list => [...list.querySelectorAll('li')].every(row => {
                    const bounds = row.getBoundingClientRect();
                    return row.scrollWidth <= row.clientWidth + 1 && [...row.querySelectorAll('.badge, button')].every(el => {
                        const r = el.getBoundingClientRect();
                        return r.left >= bounds.left - 1 && r.right <= bounds.right + 1;
                    });
                })"""), f"Task controls overflow at {width}px ({theme})"
                page.locator(".task-panel").screenshot(path=str(tmp_path / f"task-status-{width}-{theme}.png"))
            title, _, _, task_id = rows[-1]
            queue.get_by_role("button", name=f"完成任务：{title}", exact=True).click()
            expect(queue.get_by_role("listitem")).to_have_count(3)
            assert client.get(f"/api/tasks/{task_id}").json()["status"] == "已完成"
        finally:
            browser.close()
            client.close()
