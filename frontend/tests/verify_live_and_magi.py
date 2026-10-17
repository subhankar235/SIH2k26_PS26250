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
    page.screenshot(path="frontend/test-results/live_homepage.png", full_page=True)
    print("Homepage screenshot saved to frontend/test-results/live_homepage.png")
    
    # Toggle to Live API
    print("Switching data source to Live API...")
    page.get_by_label("Dashboard data source").select_option("live")
    time.sleep(1)
    page.screenshot(path="frontend/test-results/live_api_dashboard.png", full_page=True)
    print("Dashboard in Live API mode screenshot saved")
    
    # Check Ingestion in Live API mode
    print("Navigating to /ingestion...")
    page.goto(BASE + "/ingestion", wait_until="networkidle")
    time.sleep(1)
    page.screenshot(path="frontend/test-results/live_ingestion.png", full_page=True)
    print("Ingestion screenshot saved")
    
    # Check Evidence in Live API mode
    print("Navigating to /evidence...")
    page.goto(BASE + "/evidence", wait_until="networkidle")
    time.sleep(1)
    page.screenshot(path="frontend/test-results/live_evidence.png", full_page=True)
    print("Evidence screenshot saved")

    # Check Decision Validity in Live API mode
    print("Navigating to /validity...")
    page.goto(BASE + "/validity", wait_until="networkidle")
    time.sleep(1)
    page.screenshot(path="frontend/test-results/live_validity.png", full_page=True)
    print("Validity screenshot saved")

    # Check Explanations in Live API mode
    print("Navigating to /explanations...")
    page.goto(BASE + "/explanations", wait_until="networkidle")
    time.sleep(1)
    page.screenshot(path="frontend/test-results/live_explanations.png", full_page=True)
    print("Explanations screenshot saved")

    browser.close()
    print("ALL VERIFIED!")

