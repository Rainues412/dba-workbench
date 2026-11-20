"""Sample real rendered frames; use synthetic responses and an isolated app."""
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _edge


STATS = {
    "script_count": 12345, "article_count": 6789, "task_total": 120,
    "task_pending": 120, "task_overdue": 0, "customer_count": 2400,
    "resource_count": 4500, "password_count": 0,
}
DISTRIBUTION = [{"name": name, "count": count} for name, count in [
    ("Oracle", 2760), ("MySQL", 3850), ("PostgreSQL", 80), ("SQL Server", 170),
    ("Linux", 260), ("Redis", 240), ("MongoDB", 80), ("其他", 0),
]]
TARGETS = [12345, 6789, 120, 2400, 4500, 0, *[item["count"] for item in DISTRIBUTION]]

RECORDER = """() => {
    if (document.documentElement) delete document.documentElement.dataset.entranceFinished;
    window.entranceFrames = [];
    let start;
    const read = () => {
        const numbers = [...document.querySelectorAll('.dashboard-number [aria-hidden]')];
        if (numbers.length !== 14) return;
        start ??= performance.now();
        const bars = [...document.querySelectorAll('.database-panel .progress-track > span')];
        window.entranceFrames.push({
            t: performance.now() - start,
            texts: numbers.map(el => el.textContent),
            counts: numbers.map(el => Number(el.textContent.replaceAll(',', ''))),
            scales: bars.map(el => new DOMMatrix(getComputedStyle(el).transform).a),
        });
    };
    const observer = new MutationObserver(() => { if (start === undefined) read(); });
    observer.observe(document, {childList: true, subtree: true});
    const frame = () => {
        read();
        if (start === undefined || performance.now() - start < 1300) requestAnimationFrame(frame);
        else { observer.disconnect(); document.documentElement.dataset.entranceFinished = 'true'; }
    };
    requestAnimationFrame(frame);
}"""


@pytest.mark.browser
@pytest.mark.parametrize("theme,width", [("light", 1440), ("dark", 390)])
def test_dashboard_counts_and_bars_grow_without_overshoot(live_server, monkeypatch, theme, width):
    from backend import auth

    monkeypatch.setattr(auth, "_desktop_token", "test-dashboard-entrance")
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="no-preference")
            page.add_init_script(f"localStorage.setItem('dba-ui-theme', '{theme}');")
            page.add_init_script(f"({RECORDER})()")
            page.route("**/api/dashboard/stats", lambda route: route.fulfill(json=STATS))
            page.route("**/api/dashboard/recent-tasks", lambda route: route.fulfill(json=[]))
            page.route("**/api/dashboard/database-distribution", lambda route: route.fulfill(json=DISTRIBUTION))
            page.goto(live_server + "/#desktop=test-dashboard-entrance")
            expect(page.locator('html')).to_have_attribute('data-entrance-finished', 'true')
            frames = page.evaluate("window.entranceFrames")
            assert frames[0]["counts"] == [0] * len(TARGETS)
            assert frames[0]["scales"] == [0] * 8
            assert frames[-1]["counts"] == TARGETS
            assert frames[-1]["scales"] == [1] * 8
            assert frames[-1]["texts"][0] == "12,345"
            assert all(frame["counts"][5] == frame["counts"][-1] == 0 for frame in frames)
            assert any(0 < frame["counts"][0] < TARGETS[0] for frame in frames)
            assert all(0 <= actual <= target for frame in frames for actual, target in zip(frame["counts"], TARGETS))
            assert all(0 <= scale <= 1 for frame in frames for scale in frame["scales"])
            for previous, current in zip(frames, frames[1:]):
                assert all(after >= before for before, after in zip(previous["counts"], current["counts"]))
                assert all(after >= before for before, after in zip(previous["scales"], current["scales"]))
            # All metrics and bars follow the same progress, within integer rounding.
            for frame in frames:
                progress = frame["scales"][0]
                assert all(abs(actual - target * progress) < 1.5 for actual, target in zip(frame["counts"], TARGETS))
                assert all(abs(scale - progress) < .0001 for scale in frame["scales"])
            settled = next(frame["t"] for frame in frames if frame["t"] > 850 and frame["counts"] == TARGETS and frame["scales"] == [1] * 8)
            # Measure motion itself, excluding time from DOM insertion to the first update.
            started = next(frame["t"] for frame in frames if frame["counts"][0] > 0)
            assert 850 <= settled - started <= 1150
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # Background refreshes do not restart an entrance on a mounted page.
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.locator('.stat-copy .dashboard-number [aria-hidden]').first).to_have_text("12,345")
            output = Path(os.environ["TEMP"])
            (output / f"entrance-{theme}.json").write_text(json.dumps(frames), encoding="utf-8")
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            page.screenshot(path=str(output / f"dashboard-{theme}-{width}.png"), full_page=True)
            # A cached route revisit must start a fresh entrance too.
            page.locator('.stat-card').first.click()
            page.evaluate(RECORDER)
            page.get_by_role('link', name='返回工作台', exact=True).click()
            expect(page.locator('html')).to_have_attribute('data-entrance-finished', 'true')
            revisited = page.evaluate('window.entranceFrames')
            assert revisited[0]['counts'] == [0] * len(TARGETS)
            assert any(0 < frame['counts'][0] < TARGETS[0] for frame in revisited)
            expect(page.locator('.stat-copy .dashboard-number [aria-hidden]').first).to_have_text("12,345")
            for system, app in [("reduce", False), ("no-preference", True)]:
                page.emulate_media(reduced_motion=system)
                page.evaluate("enabled => localStorage.setItem('dba-preference:reduceMotion', String(enabled))", app)
                page.reload()
                expect(page.locator('html')).to_have_attribute('data-entrance-finished', 'true')
                reduced = page.evaluate("window.entranceFrames")
                assert all(frame["counts"] == TARGETS and frame["scales"] == [1] * 8 for frame in reduced)
        finally:
            browser.close()
