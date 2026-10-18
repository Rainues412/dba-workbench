from __future__ import annotations

import time
import sqlite3

import httpx
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


def _wait_for_script(base_url: str, script_id: int, expected_title: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = httpx.get(f"{base_url}/api/scripts/{script_id}", timeout=2)
        if response.status_code == 200 and response.json()["title"] == expected_title:
            return
        time.sleep(0.1)
    pytest.fail(f"script {script_id} did not become {expected_title!r}")


def _wait_for_script_count(base_url: str, expected: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = httpx.get(f"{base_url}/api/scripts/", timeout=2)
        if response.status_code == 200 and response.json()["total"] == expected:
            return
        time.sleep(0.1)
    pytest.fail(f"script count did not become {expected}")


@pytest.mark.browser
def test_edge_ui_smoke_and_vault_starts_locked(live_server: str) -> None:
    created = httpx.post(
        f"{live_server}/api/scripts/",
        json={
            "title": "Browser smoke script",
            "description": "safe temporary data",
            "db_type": "Oracle",
            "wb_type": "巡检",
            "tags": "smoke",
            "content": "select 1 from dual;",
            "file_path": r"D:\tests\browser-smoke.sql",
        },
        timeout=5,
    )
    created.raise_for_status()
    script_id = created.json()["id"]
    assert created.json()["revision"] == 1
    assert httpx.get(f"{live_server}/api/scripts/", timeout=5).json()["items"][0]["revision"] == 1

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except PlaywrightError as error:
            pytest.skip(f"Microsoft Edge is unavailable: {error}")

        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(5_000)
            page.goto(live_server, wait_until="networkidle")

            assert page.title() == "DBA 工作台"
            page.locator("#apiBadge").wait_for(state="visible")
            assert page.locator("#apiBadge").inner_text() == "已连接服务器"

            page.locator('[data-view="scripts"]').click()
            assert page.evaluate("gd('scripts')[0]")["revision"] == 1
            page.locator("#scriptDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#scriptTypeChart .db-item").filter(has_text="巡检").click()

            row = page.locator("#scriptsTableBody tr").filter(has_text="Browser smoke script")
            row.wait_for(state="visible")
            row.get_by_role("button", name="编辑").click()
            page.locator('#modalContent input[name="name"]').fill("Browser smoke script edited")
            with page.expect_response(
                lambda response: response.request.method == "PUT"
                and f"/api/scripts/{script_id}" in response.url
            ) as update_info:
                page.locator('#modalContent button[type="submit"]').click()
            assert update_info.value.status == 200, (
                update_info.value.text(), update_info.value.request.headers
            )
            _wait_for_script(live_server, script_id, "Browser smoke script edited")
            assert httpx.get(
                f"{live_server}/api/scripts/{script_id}", timeout=5
            ).json()["content"] == "select 1 from dual;"

            # The current UI returns to the database grid after an edit.
            page.locator("#scriptDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#scriptTypeChart .db-item").filter(has_text="巡检").click()
            edited_row = page.locator("#scriptsTableBody tr").filter(
                has_text="Browser smoke script edited"
            )
            page.once("dialog", lambda dialog: dialog.accept())
            edited_row.get_by_role("button", name="删除").click()
            _wait_for_script_count(live_server, 0)

            page.locator('[data-view="accounts"]').click()
            assert page.locator("#pinLockSection").is_visible()
            assert page.locator("#accountsContent").is_hidden()
        finally:
            browser.close()


@pytest.mark.browser
def test_user_content_is_rendered_as_text_in_edge(live_server: str) -> None:
    payload = '<img src=x onerror="window.__xssFired=(window.__xssFired||0)+1">'
    script_payload = "<script>window.__xssFired=99</script>"
    url_payload = "javascript:window.__xssFired=100"
    records = [
        (
            "/api/scripts/",
            {
                "title": script_payload,
                "description": payload,
                "db_type": "Oracle",
                "wb_type": "巡检",
                "tags": payload,
                "content": payload,
                "file_path": url_payload,
            },
        ),
        (
            "/api/articles/",
            {
                "title": payload,
                "summary": payload,
                "content": payload,
                "category": "巡检规范",
                "tags": payload,
                "wb_db": "Oracle",
                "file_path": payload,
            },
        ),
        (
            "/api/resources/",
            {
                "name": payload,
                "kind": "安装包",
                "path": payload,
                "version": payload,
                "tags": payload,
                "wb_db": "Oracle",
            },
        ),
        (
            "/api/tasks/",
            {"title": payload, "description": payload, "priority": "高"},
        ),
        (
            "/api/customers/",
            {
                "name": payload,
                "project_name": payload,
                "group_name": payload,
                "status": "进行中",
                "wb_person": payload,
                "wb_contact": payload,
            },
        ),
    ]
    for path, body in records:
        response = httpx.post(f"{live_server}{path}", json=body, timeout=5)
        response.raise_for_status()

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except PlaywrightError as error:
            pytest.skip(f"Microsoft Edge is unavailable: {error}")

        try:
            page = browser.new_page()
            page.set_default_timeout(5_000)
            page.add_init_script("window.__xssFired = 0")
            page.goto(live_server, wait_until="networkidle")

            page.locator('[data-view="scripts"]').click()
            page.locator("#scriptDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#scriptTypeChart .db-item").filter(has_text="巡检").click()
            page.locator("#scriptsTableBody").get_by_text(script_payload, exact=True).wait_for()
            page.locator("#scriptsTableBody").get_by_text(payload, exact=True).first.wait_for()
            assert page.locator('#scriptsTableBody img[src="x"]').count() == 0
            assert page.locator("#scriptsTableBody script").count() == 0
            page.locator("#scriptsTableBody").get_by_role("button", name="编辑").click()
            assert page.locator('#modalContent input[name="name"]').input_value() == script_payload
            assert page.locator('#modalContent input[name="path"]').input_value() == url_payload
            page.locator("#modalContent .modal-close").click()

            page.locator('[data-view="knowledge"]').click()
            page.locator("#kbDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#kbTypeChart .db-item").filter(has_text="巡检规范").click()
            page.locator("#knowledgeTableBody").get_by_text(payload, exact=True).first.wait_for()
            assert page.locator('#knowledgeTableBody img[src="x"]').count() == 0

            page.locator('[data-view="installers"]').click()
            page.locator("#instDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#installersTableBody").get_by_text(payload, exact=True).first.wait_for()
            assert page.locator('#installersTableBody img[src="x"]').count() == 0

            page.locator('[data-view="tasks"]').click()
            page.locator("#tasksTableBody").get_by_text(payload, exact=True).first.wait_for()
            assert page.locator('#tasksTableBody img[src="x"]').count() == 0

            page.locator('[data-view="contacts"]').click()
            page.locator("#contactsTableBody").get_by_text(payload, exact=True).first.wait_for()
            assert page.locator('#contactsTableBody img[src="x"]').count() == 0

            page.evaluate(
                "([key, value]) => localStorage.setItem(key, JSON.stringify(value))",
                [
                    "wb_dba_workbench_accounts",
                    [
                        {
                            "id": 1,
                            "site": payload,
                            "username": payload,
                            "password": payload,
                            "notes": payload,
                        }
                    ],
                ],
            )
            page.reload(wait_until="networkidle")
            page.locator('[data-view="accounts"]').click()
            for digit, value in zip(page.locator(".pin-digit").all(), "1234"):
                digit.fill(value)
            page.locator("#accountsTableBody").get_by_text(payload, exact=True).first.wait_for()
            assert page.locator('#accountsTableBody img[src="x"]').count() == 0
            assert page.evaluate("window.__xssFired") == 0
        finally:
            browser.close()


@pytest.mark.browser
def test_edge_can_page_to_and_edit_records_after_200(live_server: str, isolated_app) -> None:
    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.executemany(
            """INSERT INTO scripts (title, content, db_type, wb_type, file_path)
               VALUES (?, ?, 'Oracle', '巡检', ?)""",
            [
                (f"Browser paged {index:03d}", f"body {index:03d}", rf"D:\tests\paged-{index:03d}.sql")
                for index in range(205)
            ],
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except PlaywrightError as error:
            pytest.skip(f"Microsoft Edge is unavailable: {error}")

        try:
            page = browser.new_page()
            page.set_default_timeout(8_000)
            page.goto(live_server, wait_until="networkidle")
            page.locator('[data-view="scripts"]').click()
            page.locator("#scriptDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#scriptTypeChart .db-item").filter(has_text="巡检").click()
            page.locator("#wbPager-scripts").get_by_text("共 205 条").wait_for()

            for expected_page in range(2, 6):
                with page.expect_response(
                    lambda response, target=expected_page: response.request.method == "GET"
                    and "/api/scripts/" in response.url
                    and f"page={target}" in response.url
                ):
                    page.locator("#wbPager-scripts").get_by_role("button", name="下一页").click()
                page.locator("#wbPager-scripts").get_by_text(
                    f"第 {expected_page} / 5 页", exact=False
                ).wait_for()

            row = page.locator("#scriptsTableBody tr").first
            original_title = row.locator("strong").inner_text()
            with page.expect_response(
                lambda response: response.request.method == "GET"
                and "/api/scripts/" in response.url
                and response.url.rstrip("/").split("/")[-1].isdigit()
            ):
                row.get_by_role("button", name="编辑").click()
            page.locator('#modalContent input[name="name"]').fill(original_title + " edited")
            with page.expect_response(
                lambda response: response.request.method == "PUT"
                and "/api/scripts/" in response.url
            ) as update_info:
                page.locator('#modalContent button[type="submit"]').click()
            assert update_info.value.status == 200
            assert update_info.value.json()["content"].startswith("body ")
        finally:
            browser.close()
