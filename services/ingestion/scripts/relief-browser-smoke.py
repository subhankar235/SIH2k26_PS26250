"""Authenticated live relief browser smoke. Uses private local .env; never prints secrets."""
import json
import os
import uuid
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('MONITOR_TEST_URL', 'http://127.0.0.1:3100').rstrip('/')
parsed = urlparse(base)
if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
    raise RuntimeError('Live fixture credentials may only be sent to a loopback origin.')
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Live fixture does not follow redirects.')
opener = build_opener(NoRedirect())
env = dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
def command(path, body=None):
    req = Request(base+'/v1/simulation'+path, data=json.dumps(body).encode() if body else None,
                  headers={'Authorization':'Bearer '+env['INGESTION_ADMIN_TOKEN'], **({'Content-Type':'application/json'} if body else {})})
    with opener.open(req, timeout=10) as response: return json.load(response)
current = command('')
body = {'scenario':'civilian-relief', 'commandId':str(uuid.uuid4())}
if current['status']=='ready': body['replaceRunId']=current['world']['runId']
state = command('/start', body)
Path('var').mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror', lambda error: errors.append(type(error).__name__))
    page.goto(base+'/monitor/'); page.wait_for_load_state('networkidle')
    page.get_by_label('Viewer token',exact=True).fill(env['MONITOR_VIEWER_TOKEN'])
    page.get_by_role('button',name='Open session',exact=True).click()
    expect(page.locator('#relief-state')).to_contain_text('Revision 0')
    diagnostics=state['plan']['diagnostics']
    search_nodes=page.locator('#relief-content').get_by_text('Search nodes explored / limit',exact=True).locator('xpath=following-sibling::dd[1]')
    expect(search_nodes).to_have_text(f"{diagnostics['nodesExplored']} / {diagnostics['nodeLimit']}")
    expect(page.locator('#relief-content')).to_contain_text('Independent checker')
    expect(page.locator('#relief-content')).to_contain_text('Synthetic demand forecast')
    expect(page.locator('#relief-content')).to_contain_text('Specialist reports')
    page.locator('#relief-panel').scroll_into_view_if_needed()
    page.screenshot(path='var/relief-live-initial.png',full_page=True)
    scores=[state['plan']['objective']['servedPriority']]
    while state['nextPhase']:
        state = command('/step',{'commandId':str(uuid.uuid4()),'runId':state['world']['runId'], 'expectedRevision':state['world']['revision'],'phase':state['nextPhase']})
        expect(page.locator('#relief-state')).to_contain_text('Revision '+str(state['world']['revision']),timeout=12000)
        assert state['validation']['valid']
        scores.append(state['plan']['objective']['servedPriority'])
    assert scores==[9,7,7,0,10,0]
    expect(page.locator('#relief-content')).to_contain_text('No feasible assignments proposed')
    for width in (320,768,1024,1440):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Viewport overflow'
    page.screenshot(path='var/relief-live-final.png',full_page=True)
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.locator('#login-panel')).to_be_visible()
    assert page.locator('#relief-content').text_content()==''
    assert not errors, 'Browser runtime error'
    browser.close()
print('Live relief browser passed authenticated 6revision replanning, grounded reports/forecast/checker,4viewports and logout clearing. Screenshots in var/.')
