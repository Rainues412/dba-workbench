# -*- coding: utf-8 -*-
"""
Browser test for installer module - precise selectors
"""
import asyncio
import sys
from playwright.async_api import async_playwright

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://localhost:8686", wait_until="networkidle")
        await asyncio.sleep(2)

        # Click installer nav item specifically
        print("[1] Clicking installer nav...")
        await page.click('[data-view="installers"]')
        await asyncio.sleep(1)

        # Verify view is active
        is_active = await page.evaluate("""
            () => {
                const el = document.getElementById('view-installers');
                return el ? el.classList.contains('active') : false;
            }
        """)
        print(f"  view-installers active: {is_active}")

        # Check cards
        cards = await page.evaluate("""
            () => {
                const chart = document.getElementById('instDBChart');
                if (!chart) return [];
                return Array.from(chart.querySelectorAll('.db-item')).map(item => {
                    const name = (item.querySelector('.db-name') || {}).textContent || '';
                    const count = (item.querySelector('.db-bar-num') || {}).textContent || '0';
                    return {name, count};
                });
            }
        """)
        print(f"\n[2] Database cards ({len(cards)}):")
        for c in cards:
            print(f"  {c['name']}: {c['count']}")

        # Click MySQL card using precise selector (only within instDBChart)
        print("\n[3] Clicking MySQL card in instDBChart...")
        mysql_clicked = await page.evaluate("""
            () => {
                const chart = document.getElementById('instDBChart');
                if (!chart) return 'chart not found';
                const items = chart.querySelectorAll('.db-item');
                for (const item of items) {
                    const nameEl = item.querySelector('.db-name');
                    if (nameEl && nameEl.textContent === 'MySQL') {
                        item.click();
                        return 'clicked';
                    }
                }
                return 'MySQL card not found';
            }
        """)
        print(f"  Result: {mysql_clicked}")
        await asyncio.sleep(1)

        # Check list view
        list_info = await page.evaluate("""
            () => {
                const list = document.getElementById('instList');
                const title = document.getElementById('instListTitle');
                const count = document.getElementById('instListCount');
                const tbody = document.getElementById('installersTableBody');
                const dbGrid = document.getElementById('instDBGrid');
                return {
                    listVisible: list ? list.style.display !== 'none' : false,
                    dbGridHidden: dbGrid ? dbGrid.style.display === 'none' : false,
                    title: title ? title.textContent : '',
                    count: count ? count.textContent : '',
                    rowCount: tbody ? tbody.querySelectorAll('tr').length : 0,
                    firstRows: tbody ? Array.from(tbody.querySelectorAll('tr')).slice(0, 3).map(tr => {
                        const td = tr.querySelector('td');
                        return td ? td.textContent.substring(0, 60) : '';
                    }) : []
                };
            }
        """)
        print(f"\n[4] List view after MySQL click:")
        print(f"  List visible: {list_info['listVisible']}")
        print(f"  DB grid hidden: {list_info['dbGridHidden']}")
        print(f"  Title: {list_info['title']}")
        print(f"  Count: {list_info['count']}")
        print(f"  Table rows: {list_info['rowCount']}")
        if list_info['firstRows']:
            print("  First 3 rows:")
            for r in list_info['firstRows']:
                print(f"    - {r}")

        # Test breadcrumb back
        print("\n[5] Testing breadcrumb back to DB grid...")
        back_result = await page.evaluate("""
            () => {
                const breadcrumb = document.getElementById('instBreadcrumb');
                const link = breadcrumb ? breadcrumb.querySelector('a') : null;
                if (link) {
                    link.click();
                    return 'clicked breadcrumb';
                }
                return 'no breadcrumb link';
            }
        """)
        print(f"  Result: {back_result}")
        await asyncio.sleep(0.5)

        after_back = await page.evaluate("""
            () => {
                const dbGrid = document.getElementById('instDBGrid');
                const list = document.getElementById('instList');
                return {
                    dbGridVisible: dbGrid ? dbGrid.style.display !== 'none' : false,
                    listHidden: list ? list.style.display === 'none' : false
                };
            }
        """)
        print(f"  DB grid visible: {after_back['dbGridVisible']}")
        print(f"  List hidden: {after_back['listHidden']}")

        # Test Oracle cards (most data)
        print("\n[6] Clicking Oracle card (43 items)...")
        await page.evaluate("""
            () => {
                const chart = document.getElementById('instDBChart');
                const items = chart.querySelectorAll('.db-item');
                for (const item of items) {
                    const nameEl = item.querySelector('.db-name');
                    if (nameEl && nameEl.textContent === 'Oracle') { item.click(); return; }
                }
            }
        """)
        await asyncio.sleep(1)

        oracle_info = await page.evaluate("""
            () => {
                const tbody = document.getElementById('installersTableBody');
                const count = document.getElementById('instListCount');
                return {
                    count: count ? count.textContent : '',
                    rowCount: tbody ? tbody.querySelectorAll('tr').length : 0
                };
            }
        """)
        print(f"  Count: {oracle_info['count']}")
        print(f"  Table rows: {oracle_info['rowCount']}")

        # Test empty view (PostgreSQL)
        print("\n[7] Testing empty view (PostgreSQL)...")
        await page.evaluate("""
            () => {
                // Back to DB first
                const breadcrumb = document.getElementById('instBreadcrumb');
                const link = breadcrumb ? breadcrumb.querySelector('a') : null;
                if (link) link.click();
            }
        """)
        await asyncio.sleep(0.5)
        await page.evaluate("""
            () => {
                const chart = document.getElementById('instDBChart');
                const items = chart.querySelectorAll('.db-item');
                for (const item of items) {
                    const nameEl = item.querySelector('.db-name');
                    if (nameEl && nameEl.textContent === 'PostgreSQL') { item.click(); return; }
                }
            }
        """)
        await asyncio.sleep(0.5)

        empty_info = await page.evaluate("""
            () => {
                const tbody = document.getElementById('installersTableBody');
                const count = document.getElementById('instListCount');
                const emptyMsg = tbody ? tbody.querySelector('td[colspan]') : null;
                return {
                    count: count ? count.textContent : '',
                    rowCount: tbody ? tbody.querySelectorAll('tr').length : 0,
                    emptyMessage: emptyMsg ? emptyMsg.textContent : ''
                };
            }
        """)
        print(f"  Count: {empty_info['count']}")
        print(f"  Table rows: {empty_info['rowCount']}")
        print(f"  Empty message: {empty_info['emptyMessage']}")

        # Summary
        print("\n" + "=" * 50)
        all_ok = (
            is_active
            and len(cards) == 7
            and mysql_clicked == 'clicked'
            and list_info['listVisible']
            and list_info['rowCount'] > 0
            and after_back['dbGridVisible']
            and oracle_info['rowCount'] > 0
            and empty_info['emptyMessage'] != ''
        )
        print(f"OVERALL: {'ALL PASS' if all_ok else 'ISSUES FOUND'}")
        print("=" * 50)

        print("\nBrowser closing in 5s...")
        await asyncio.sleep(5)
        await browser.close()

asyncio.run(test())
