"""Check request failures without relying on a running backend."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='msedge')
    page = browser.new_page(viewport={'width': 1440, 'height': 950})
    page.add_init_script("localStorage.setItem('air-power-data-mode', 'live')")
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    mode = {'value': 'network'}
    calls = []
    def intercept(route):
        calls.append(route.request.url)
        if mode['value'] == 'network':
            route.abort('failed')
        else:
            status = int(mode['value'])
            route.fulfill(status=status, content_type='application/json', body=json.dumps({'code': 'test_error', 'message': 'Backend test message'}), headers={'Access-Control-Allow-Origin': '*'})
    page.route('http://localhost:8000/**', intercept)
    paths = ['/ingestion', '/evidence', '/evidence/REC-1', '/validity', '/validity/DEC-1', '/forecasts', '/planning', '/stress-lab', '/stress-lab/RUN-1', '/explanations', '/approvals', '/audit', '/benchmarks']
    for path in paths:
        page.goto('http://localhost:3100' + path, wait_until='networkidle')
        expect(page.locator('.request-failure').first).to_be_visible()
        expect(page.locator('.request-failure').first).to_contain_text('Connection unavailable')
        assert 'Failed to fetch' not in page.locator('body').inner_text(), path
        if path in ['/ingestion', '/evidence', '/validity', '/audit', '/benchmarks']:
            expect(page.locator('table')).to_have_count(0)
    page.goto('http://localhost:3100/ingestion', wait_until='networkidle')
    before = len(calls)
    page.get_by_role('button', name='Try again', exact=True).first.click()
    expect(page.locator('.request-failure').first).to_be_visible()
    assert len(calls) > before
    page.locator('.request-failure').first.locator('summary').click()
    expect(page.locator('.request-failure-details').first).to_contain_text('connection_unavailable')
    Path('frontend/test-results').mkdir(exist_ok=True)
    page.screenshot(path='frontend/test-results/connection-failure-desktop.png', full_page=True)
    for status, label in [(404, 'Data not available'), (403, 'Access required'), (429, 'Too many requests'), (503, 'Service temporarily unavailable')]:
        mode['value'] = str(status)
        page.goto('http://localhost:3100/forecasts', wait_until='networkidle')
        expect(page.locator('.request-failure')).to_contain_text(label)
        page.locator('summary').click()
        expect(page.locator('.request-failure')).to_contain_text(f'HTTP {status}')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto('http://localhost:3100/forecasts', wait_until='networkidle')
    page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='frontend/test-results/connection-failure-mobile.png', full_page=True)
    mode['value'] = 'network'
    page.goto('http://localhost:3100', wait_until='networkidle')
    page.get_by_label('Dashboard data source').select_option('live')
    expect(page.locator('.request-failure')).to_contain_text('Live dashboard data')
    expect(page.locator('.summary-card > strong').first).to_have_text('--')
    expect(page.locator('.dashboard-middle-row')).to_have_count(0)
    page.get_by_label('Dashboard data source').select_option('demo')
    expect(page.locator('.source-column')).to_have_count(4)
    assert not errors, errors
    browser.close()
    print('PASS: network errors across 13 routes; retry; technical details; HTTP 404/403/429/503; mobile layout; live dashboard recovery to demo.')