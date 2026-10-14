"""Real authenticated source update -> replanning -> viewer polling, with no secret output."""
import json
import os
import uuid
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('MONITOR_TEST_URL', 'http://127.0.0.1:3100').rstrip('/')
parsed = urlparse(base)
if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password:
    raise RuntimeError('Browser credentials are loopback-only')
env = dict(os.environ)
if not env.get('INGESTION_ADMIN_TOKEN'):
    env.update(dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#')))
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
opener = build_opener(NoRedirect())
def request(path, body=None, token=None):
    req = Request(base+path, data=json.dumps(body).encode() if body else None,
                  headers={'Authorization':'Bearer '+(token or env['INGESTION_ADMIN_TOKEN']), **({'Content-Type':'application/json'} if body else {})})
    with opener.open(req,timeout=15) as response: return json.load(response)
current=request('/v1/simulation')
body={'scenario':'civilian-relief','inputMode':'gateway','commandId':str(uuid.uuid4())}
if current['status']=='ready': body['replaceRunId']=current['world']['runId']
state=request('/v1/simulation/start',body)
source=next(s for s in json.loads(env['INGESTION_SOURCES_JSON']) if s['sourceId']==state['inputs']['authorities']['weather.observation'])
Path('var').mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error: errors.append(type(error).__name__))
    page.goto(base+'/monitor/');page.wait_for_load_state('networkidle')
    page.get_by_label('Viewer token',exact=True).fill(env['MONITOR_VIEWER_TOKEN'])
    page.get_by_role('button',name='Open session',exact=True).click()
    expect(page.locator('#relief-state')).to_contain_text('Revision 0')
    expect(page.locator('#relief-content')).to_contain_text(state['inputs']['namespace'])
    expect(page.locator('#relief-content')).to_contain_text('Deterministic specialist coordination')
    from datetime import datetime,timezone,timedelta
    now=datetime.now(timezone.utc)
    event={'schemaVersion':1,'eventId':str(uuid.uuid4()),'sourceId':source['sourceId'],'type':'weather.observation','entityId':state['inputs']['namespace']+'SIM-CLINIC','sequence':1,'observedAt':now.isoformat(),'validUntil':(now+timedelta(seconds=15)).isoformat(),'data':{'temperatureC':24,'windSpeedMps':25,'visibilityM':1500,'condition':'storm'}}
    request('/v1/events',event,source['token'])
    expect(page.locator('#relief-state')).to_contain_text('Revision 1',timeout=12000)
    expect(page.locator('#relief-content')).to_contain_text(event['eventId'])
    expect(page.locator('#relief-state')).to_contain_text('Revision 2',timeout=20000)
    expect(page.locator('#relief-content')).to_contain_text('Expired')
    assert request('/v1/simulation')['validation']['valid']
    for width in (320,768,1024,1440):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Viewport overflow'
    page.screenshot(path='var/dynamic-browser-live.png',full_page=True)
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.locator('#login-panel')).to_be_visible()
    assert page.locator('#relief-content').text_content()==''
    assert not errors,'Browser runtime error'
    browser.close()
print('Real source-driven viewer polling, automatic expiry, four viewports and logout passed.')
