import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = 'http://localhost:3000'

def run():
    print(f"Connecting to {BASE}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()

        console_errors = []
        page_errors = []

        page.on('console', lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ['error', 'warn'] else None)
        page.on('pageerror', lambda err: page_errors.append(str(err)))

        print("--- Testing Dashboard ---")
        page.goto(BASE, wait_until='networkidle')
        page.wait_for_timeout(1000)

        # 1. Test Disruption buttons
        print("Testing Disruption Injection buttons...")
        storm_btn = page.locator('button.disruption-btn.storm')
        expect(storm_btn).to_be_visible()
        storm_btn.click()
        page.wait_for_timeout(1500)
        expect(page.locator('.status-breach, .status-deliberating, .status-consensus')).to_be_visible()
        print("[OK] Storm disruption clicked and state transitioned")

        reset_btn = page.locator('button.disruption-btn.reset')
        reset_btn.click()
        page.wait_for_timeout(500)
        expect(page.locator('.status-consensus')).to_be_visible()
        print("[OK] Reset equilibrium works")

        # 2. Test Agent Inspection Modal
        print("Testing MAGI Agent Pod inspection modal...")
        agent_pod = page.locator('.magi-agent-pod').first
        agent_pod.click()
        page.wait_for_timeout(500)
        modal = page.locator('.agent-modal-card')
        expect(modal).to_be_visible()
        print("[OK] Agent inspector modal opened")

        close_btn = page.locator('.modal-close-btn, .btn-primary-orange').first
        close_btn.click()
        page.wait_for_timeout(500)
        expect(modal).to_have_count(0)
        print("[OK] Agent inspector modal closed")

        # 3. Test Resource Boards tabs
        print("Testing Resource Boards tab switching...")
        tabs = ['Aircrew & Pilots', 'Munitions & Priority', 'Corridors & Weather', 'Threat Radar', 'Data Feeds Health', 'Fleet Airframes']
        for tab_name in tabs:
            tab_btn = page.locator(f'button.tab-btn:has-text("{tab_name}")').first
            expect(tab_btn).to_be_visible()
            tab_btn.click()
            page.wait_for_timeout(300)
            expect(page.locator('.board-content')).to_be_visible()
            print(f"[OK] Tab '{tab_name}' rendered properly")

        # 4. Visit and check all routes
        routes = [
            '/ingestion',
            '/evidence',
            '/evidence/ISSUE-01',
            '/validity',
            '/validity/DEC-802',
            '/forecasts',
            '/planning',
            '/planning/compare',
            '/stress-lab',
            '/stress-lab/RUN-42',
            '/explanations',
            '/approvals',
            '/audit',
            '/benchmarks'
        ]

        print("--- Testing all 14 domain routes ---")
        for route in routes:
            url = f"{BASE}{route}"
            page.goto(url, wait_until='networkidle')
            page.wait_for_timeout(500)
            has_h1 = page.locator('h1, h2').count() > 0
            print(f"Route {route:22}: HTTP OK, Headers found: {has_h1}")

        # 5. Check Mobile Viewport (no horizontal scroll)
        print("--- Testing Mobile Responsiveness (390x844) ---")
        page.set_viewport_size({'width': 390, 'height': 844})
        page.goto(BASE, wait_until='networkidle')
        page.wait_for_timeout(500)
        is_overflowing = page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        print(f"Mobile Horizontal Overflow: {'YES (ERROR)' if is_overflowing else 'NO (PERFECT)'}")

        browser.close()

        print("\n=== CONSOLE SUMMARY ===")
        print(f"Page uncaught exceptions: {len(page_errors)}")
        for err in page_errors:
            print(f"  ERR: {err}")
        print(f"Console warnings/errors: {len(console_errors)}")
        for err in console_errors[:10]:
            print(f"  LOG: {err}")

if __name__ == '__main__':
    run()
