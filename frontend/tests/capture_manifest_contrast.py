import os
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000"

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(headless=True, channel="msedge")
    except Exception:
        browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    print("Navigating to Homepage...")
    page.goto(BASE + "/", wait_until="networkidle")
    time.sleep(1)

    # Scroll to Flight Dispatch Manifest
    manifest = page.locator("text=Active Sortie Dispatch & Mission Allocation Board").first
    manifest.scroll_into_view_if_needed()
    time.sleep(0.5)

    os.makedirs("frontend/test-results", exist_ok=True)
    page.screenshot(path="frontend/test-results/manifest_high_contrast.png")
    print("Saved frontend/test-results/manifest_high_contrast.png")

    # Click Storm Front scenario button
    storm_btn = page.locator("button:has-text('Storm Front in Corridor Charlie')").first
    if storm_btn.count() > 0:
        storm_btn.click()
        time.sleep(1)
        manifest.scroll_into_view_if_needed()
        page.screenshot(path="frontend/test-results/manifest_storm_disruption.png")
        print("Saved frontend/test-results/manifest_storm_disruption.png")

        # Click Rerouted / Alert filter
        reroute_filter = page.locator("button:has-text('Rerouted / Alert')").first
        if reroute_filter.count() > 0:
            reroute_filter.click()
            time.sleep(0.5)
            page.screenshot(path="frontend/test-results/rerouted_sortie_card.png")
            print("Saved frontend/test-results/rerouted_sortie_card.png")

    # Navigate to Planning page to verify ASSIGNMENT_MANIFEST table
    print("Navigating to Planning page...")
    page.goto(BASE + "/planning", wait_until="networkidle")
    time.sleep(1)
    plan_manifest = page.locator("text=Authoritative Flight & Resource Allocation Manifest").first
    if plan_manifest.count() > 0:
        plan_manifest.scroll_into_view_if_needed()
        page.screenshot(path="frontend/test-results/planning_manifest.png")
        print("Saved frontend/test-results/planning_manifest.png")

    browser.close()
    print("Done capturing manifest contrast and disruption!")
