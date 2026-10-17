from __future__ import annotations

import time

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
            page.locator("#scriptDBChart .db-item").filter(has_text="Oracle").click()
            page.locator("#scriptTypeChart .db-item").filter(has_text="巡检").click()

            row = page.locator("#scriptsTableBody tr").filter(has_text="Browser smoke script")
            row.wait_for(state="visible")
            row.get_by_role("button", name="编辑").click()
            page.locator('#modalContent input[name="name"]').fill("Browser smoke script edited")
            page.locator('#modalContent button[type="submit"]').click()
            _wait_for_script(live_server, script_id, "Browser smoke script edited")

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
