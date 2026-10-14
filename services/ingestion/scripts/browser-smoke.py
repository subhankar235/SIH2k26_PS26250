"""Real gateway browser smoke. Run after npm start; secrets are never printed."""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('MONITOR_TEST_URL', 'http://127.0.0.1:3100')
if urlparse(base).hostname not in ('127.0.0.1', 'localhost', '::1'):
    raise RuntimeError('Browser smoke credentials may only be sent to loopback.')
env = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
viewer = os.environ.get('MONITOR_VIEWER_TOKEN') or env.get('MONITOR_VIEWER_TOKEN')
sources = json.loads(os.environ.get('INGESTION_SOURCES_JSON') or env['INGESTION_SOURCES_JSON'])
source = next(s for s in sources if 'airport.capacity' in s['types'])
entity = 'fixture-browser-' + uuid.uuid4().hex[:12]
def send(sequence, status, seconds=120):
    now = datetime.now(timezone.utc)
    stamp = lambda time: time.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    event = dict(schemaVersion=1, eventId=str(uuid.uuid4()), sourceId=source['sourceId'], type='airport.capacity',
                 entityId=entity, sequence=sequence, observedAt=stamp(now), validUntil=stamp(now+timedelta(seconds=seconds)),
                 data=dict(status=status, arrivalsPerHour=0 if status=='closed' else 4, departuresPerHour=0 if status=='closed' else 4))
    req = Request(base+'/v1/events', data=json.dumps(event).encode(), headers={'Content-Type':'application/json', 'Authorization':'Bearer '+source['token']})
    with urlopen(req, timeout=10) as response:
        assert response.status == 201

send(1, 'open')
Path('var').mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width':1440, 'height':1000}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(type(error).__name__))
    page.goto(base+'/monitor/')
    page.wait_for_load_state('networkidle')
    expect(page.locator('#login-panel')).to_be_visible()
    page.get_by_label('Viewer token', exact=True).fill(viewer)
    page.get_by_role('button', name='Open session', exact=True).click()
    expect(page.locator('#workspace')).to_be_visible()
    page.locator('#type-filter').select_option('airport.capacity')
    page.locator('#source-filter').fill(source['sourceId'])
    page.get_by_role('button', name='Apply filters', exact=True).click()
    row = page.locator('#records tr').filter(has_text=entity)
    expect(row).to_be_visible()
    expect(row).to_contain_text('open')
    row.get_by_role('button', name='Inspect '+entity+' from '+source['sourceId'], exact=True).click()
    expect(page.locator('#inspector')).to_be_visible()
    expect(page.locator('#inspector-content')).to_contain_text('Source ID')
    page.get_by_role('button', name='Close', exact=True).click()
    send(2, 'closed', seconds=2)
    page.get_by_role('button', name='Refresh', exact=True).click()
    expect(row).to_contain_text('closed')
    expect(row.locator('td').nth(3).get_by_text('Expired', exact=True)).to_be_visible(timeout=12000)
    with page.expect_download() as download:
        page.get_by_role('button', name='Download JSON', exact=True).click()
    data = json.loads(Path(download.value.path()).read_text())
    assert data['deliveryScope'] == 'global_outbox'
    assert viewer not in json.dumps(data)
    assert data['records']
    page.screenshot(path='var/monitor-desktop.png', full_page=True)
    for width in (320, 768, 1024, 1440):
        page.set_viewport_size({'width':width, 'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Viewport overflow'
        if width == 320:
            page.screenshot(path='var/monitor-mobile.png', full_page=True)
    # Keyboard access and return from modal.
    page.locator('#refresh').focus()
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.id') == 'download'
    assert not errors, 'Browser runtime error'
    assert page.evaluate('Object.keys(localStorage).length') == 0
    # Failure fixtures exercise report clearing against the real assembled UI.
    row.get_by_role('button', name='Inspect '+entity+' from '+source['sourceId'], exact=True).click()
    page.route('**/monitor/api/snapshot*', lambda route: route.fulfill(status=401, content_type='application/json', body='{"error":{"code":"UNAUTHORIZED"}}'))
    expect(page.locator('#login-panel')).to_be_visible(timeout=12000)
    assert page.locator('#inspector-title').text_content() == 'Record details'
    assert page.locator('#inspector').get_attribute('data-inspection-id') is None
    assert page.locator('#inspector-content').text_content() == ''
    assert page.locator('#records').text_content() == ''
    page.unroute('**/monitor/api/snapshot*')
    page.get_by_label('Viewer token', exact=True).fill(viewer)
    page.get_by_role('button', name='Open session', exact=True).click()
    expect(row).to_be_visible()
    row.get_by_role('button', name='Inspect '+entity+' from '+source['sourceId'], exact=True).click()
    page.get_by_role('button', name='Close', exact=True).click()
    page.route('**/monitor/logout', lambda route: route.fulfill(status=503, content_type='application/json', body='{"error":{"code":"UNAVAILABLE"}}'))
    page.get_by_role('button', name='Sign out', exact=True).click()
    expect(page.locator('#connection-text')).to_contain_text('Sign out failed')
    assert page.locator('#inspector-title').text_content() == 'Record details'
    assert page.locator('#inspector').get_attribute('data-inspection-id') is None
    assert page.locator('#inspector-content').text_content() == ''
    assert page.locator('#records').text_content() == ''
    assert page.locator('#download').is_disabled()
    page.unroute('**/monitor/logout')
    page.get_by_role('button', name='Sign out', exact=True).click()
    expect(page.locator('#login-panel')).to_be_visible()
    assert context.request.get(base+'/monitor/api/snapshot').status == 401
    assert page.locator('#inspector-title').text_content() == 'Record details'
    assert page.locator('#inspector').get_attribute('data-inspection-id') is None
    browser.close()
print('Browser smoke passed: real session, ingestion updates, expiry polling, provenance, download, keyboard, 4 viewports/logout; failure fixtures verify auth-loss/failed-logout clearing. Screenshots in var/.')
