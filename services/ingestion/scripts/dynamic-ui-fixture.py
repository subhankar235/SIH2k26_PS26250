"""Browser contract fixtures for dynamic relief inspection; all API responses are local."""
import copy
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / 'services/ingestion/dashboard'
ARTIFACT = ROOT / '.superpowers/sdd/civilian-dynamic-extensions-plan'
UNTRUSTED = '<img src=x onerror="window.injected=true">'
NOW = '2026-10-15T06:00:00Z'
FACTS = dict(generatedAt=NOW, records=[], summary=dict(total=0, current=0, expired=0, sequenceGaps=0, disagreements=0), scope=dict(limit=1000, shown=0, truncated=False), delivery=dict(queued=0, dead=0, published=0))
REPORTS = [dict(agentId=agent, eligibleIds=['SIM-A'], findings=[dict(id=f'{agent}-finding', code='AVAILABLE', message=UNTRUSTED, entityIds=['SIM-A'])]) for agent in ['fleet', 'crew', 'weather', 'airport', 'cargo']]
READY = dict(status='ready', world=dict(simulation=True, runId='fixture-run', revision=3, tick=0, policy=dict(slots=[0, 1, 2], slotMinutes=30), aircraft=[], crews=[], airports=[], routes=[], weather=[], requests=[]), plan=dict(status='optimal', assignments=[], unserved=[], objective=dict(servedPriority=5, changedAssignments=0, totalArrivalSlots=1), diagnostics=dict(nodesExplored=100, nodeLimit=100000), agentReports=REPORTS), validation=dict(valid=True, errors=[]), nextPhase=None, history=[], generatedAt=NOW)
READY['inputs'] = dict(mode='gateway', namespace='input-fixture-run-', authorities={'weather.observation': UNTRUSTED, 'aircraft.status': 'fleet-source'}, bindings=[dict(type='weather.observation', entityId=f'input-fixture-run-SIM-{index}', scenarioEntityId=f'SIM-{index}', eventId=f'event-{index}', sourceId=UNTRUSTED, observedAt=NOW, validUntil='2026-10-15T06:10:00Z', expired=index % 2 == 0) for index in range(40)])
READY['inputFreshness'] = dict(status='current', expiredCount=0, replanPending=False)
READY['planUsable'] = True
READY['coordination'] = dict(version=1, topology='specialists-supervisor', messages=[dict(id=f'message-{index}', **{'from': 'weather', 'to': 'supervisor'}, kind='evidence', entityIds=['SIM-A'], findingIds=['weather-finding', 'UNGROUNDED-ID'], summary=UNTRUSTED + ' Long evidence summary ' * 6) for index in range(40)], decision=dict(status='verified', servedPriority=5, assignedCount=1))
READY['weatherFeed'] = dict(status='ready', runId='fixture-run', revision=3, commandId='weather-command', airportId='SIM-HUB', location='delhi', generatedAt=NOW, provenance=dict(provider='Open-Meteo', location='delhi', latitude=28.6139, longitude=77.209, fetchedAt=NOW, weatherTime=NOW, visibilityTime=NOW, unexpectedSecret='DO-NOT-RENDER'))
state = dict(sim=copy.deepcopy(READY), status=200)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.path = self.path.removeprefix('/monitor') or '/'
        super().do_GET()

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(WEB)))
threading.Thread(target=server.serve_forever, daemon=True).start()
origin = f'http://127.0.0.1:{server.server_port}'
errors, writes = [], []


def simulation_reply(route):
    route.fulfill(status=state['status'], content_type='application/json', body=json.dumps(state['sim'] if state['status'] == 200 else {'error': {'code': 'UNAUTHORIZED'}}))


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1000))
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: writes.append(request.url) if request.method != 'GET' and '/monitor/session' not in request.url and '/monitor/logout' not in request.url else None)
        page.route('**/monitor/api/snapshot*', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(FACTS)))
        page.route('**/monitor/api/simulation', simulation_reply)
        page.route('**/monitor/session', lambda route: route.fulfill(status=200, content_type='application/json', body='{}'))
        page.goto(origin + '/monitor/')
        page.wait_for_load_state('networkidle')
        panel = page.locator('#relief-content')
        expect(panel).to_contain_text('Gateway inputs')
        expect(panel).to_contain_text('input-fixture-run-')
        expect(panel).to_contain_text('Deterministic specialist coordination')
        expect(panel).to_contain_text('Weather feed ready')
        expect(panel).to_contain_text('2026-10-15 06:10:00 UTC')
        expect(panel).to_contain_text('Expired')
        expect(panel).to_contain_text('Current')
        expect(panel).not_to_contain_text('UNGROUNDED-ID')
        expect(panel).not_to_contain_text('DO-NOT-RENDER')
        expect(panel).to_contain_text('References outside the current specialist reports were omitted')
        assert panel.locator('img, script, iframe, a').count() == 0
        assert page.evaluate('window.injected === undefined')
        assert panel.locator('button, input, select').count() == 0

        def refresh():
            with page.expect_response(lambda response: '/monitor/api/simulation' in response.url):
                page.evaluate('document.querySelector("#refresh").dispatchEvent(new Event("click"))')
            expect(page.locator('#refresh')).to_be_enabled()

        ledger = panel.locator('[data-relief-detail="coordination"]')
        summary = ledger.locator('summary')
        summary.focus()
        page.keyboard.press('Enter')
        expect(ledger).to_have_attribute('open', '')
        expect(panel.locator('#relief-table-coordination tbody tr')).to_have_count(40)
        refresh()
        expect(summary).to_be_focused()
        expect(ledger).to_have_attribute('open', '')

        for status, text in [('pending', 'Weather refresh pending'), ('degraded', 'Weather feed degraded'), ('ready', 'Weather feed ready')]:
            state['sim']['weatherFeed']['status'] = status
            state['sim']['weatherFeed']['errorCode'] = 'WEATHER_VISIBILITY_MISSING' if status == 'degraded' else None
            refresh()
            expect(panel).to_contain_text(text)
        state['sim']['weatherFeed'].update(status='degraded', revision=2, errorCode='WEATHER_TIMEOUT')
        refresh()
        expect(panel).to_contain_text('Feed result from earlier revision')
        expect(panel).to_contain_text('WEATHER_TIMEOUT')
        expect(panel).to_contain_text('Open-Meteo')
        state['sim']['weatherFeed']['runId'] = 'older-run'
        refresh()
        expect(panel).not_to_contain_text('WEATHER_TIMEOUT')
        expect(panel).not_to_contain_text('Open-Meteo')
        state['sim']['weatherFeed'] = copy.deepcopy(READY['weatherFeed'])
        refresh()
        state['sim'].update(inputFreshness=dict(status='expired', expiredCount=2, replanPending=True), planUsable=False)
        refresh()
        expect(panel).to_contain_text('Historical plan only')
        expect(panel.get_by_role('heading', name='Historical assignments', exact=True)).to_be_visible()
        expect(panel).to_contain_text('Expiry replan pending')
        expect(panel).not_to_contain_text('Passed · Plan satisfies')
        ARTIFACT.mkdir(parents=True, exist_ok=True)
        panel.screenshot(path=str(ARTIFACT / 'dynamic-ui-expired-pending.png'))
        state['sim'].update(inputFreshness=dict(status='expired', expiredCount=2, replanPending=False))
        refresh()
        expect(panel).to_contain_text('Historical plan only')
        expect(panel).to_contain_text('Expiry replan not pending')
        state['sim'].update(inputFreshness=dict(status='current', expiredCount=0, replanPending=False), planUsable=True)
        refresh()
        expect(panel.get_by_role('heading', name='Proposed assignments', exact=True)).to_be_visible()
        expect(panel).not_to_contain_text('Historical plan only')

        page.set_viewport_size(dict(width=320, height=900))
        bindings = panel.locator('#relief-table-bindings')
        bindings.focus()
        bindings.evaluate('(element) => { element.scrollLeft=180; element.scrollTop=100; }')
        position = bindings.evaluate('(element) => [element.scrollLeft, element.scrollTop]')
        assert all(item > 0 for item in position)
        state['sim']['world']['revision'] = 4
        refresh()
        expect(bindings).to_be_focused()
        assert bindings.evaluate('(element) => [element.scrollLeft, element.scrollTop]') == position
        with page.expect_response(lambda response: '/monitor/api/simulation' in response.url):
            page.wait_for_timeout(5200)
        expect(page.locator('#refresh')).to_be_enabled()
        expect(bindings).to_be_focused()
        assert bindings.evaluate('(element) => [element.scrollLeft, element.scrollTop]') == position
        messages = panel.locator('#relief-table-coordination')
        messages.focus()
        messages.evaluate('(element) => { element.scrollLeft=100; element.scrollTop=100; }')
        refresh()
        expect(messages).to_be_focused()
        expect(ledger).to_have_attribute('open', '')
        assert messages.evaluate('(element) => element.scrollTop') == 100

        ARTIFACT.mkdir(parents=True, exist_ok=True)
        for width in (320, 768, 1024, 1440):
            page.set_viewport_size(dict(width=width, height=1000))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}'
            if width in (320, 1440):
                panel.screenshot(path=str(ARTIFACT / f'dynamic-ui-{width}.png'))
        state['sim']['inputs']['bindings'] = []
        state['sim']['coordination']['messages'] = []
        refresh()
        expect(panel).to_contain_text('No gateway facts bound to this run')
        expect(panel).to_contain_text('No coordination messages reported')
        expect(panel.locator('#relief-table-coordination')).to_be_focused()
        panel.locator('#relief-table-authorities').focus()
        state['sim']['inputs'] = dict(mode='scripted', bindings=[])
        state['sim'].pop('weatherFeed')
        refresh()
        expect(panel).to_contain_text('Scripted scenario inputs')
        expect(panel).not_to_contain_text('Gateway input authority')
        expect(page.locator('#relief-title')).to_be_focused()
        state['sim'].pop('inputs')
        state['sim'].pop('coordination')
        refresh()
        expect(panel).to_contain_text('Exact optimum')
        expect(panel).not_to_contain_text('Deterministic specialist coordination')
        # Lost permission must clear optional sections as well as the original view.
        state['sim'] = copy.deepcopy(READY)
        refresh()
        state['status'] = 401
        refresh()
        expect(page.locator('#login-panel')).to_be_visible()
        expect(panel).to_be_empty()
        expect(page.locator('#relief-state')).to_be_empty()
        assert not errors, errors
        assert not writes, writes
        browser.close()
finally:
    server.shutdown()
    server.server_close()
print('Dynamic UI fixtures passed: authorities, bindings/TTL, grounded coordination, weather states/staleness/provenance, safe text, long lists, disclosure/table focus and scroll, timer polling, four viewports, legacy/empty states, auth clearing, and no mutation requests.')
