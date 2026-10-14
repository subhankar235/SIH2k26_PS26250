"""Isolated browser fixtures for the read-only relief view; no credentials needed."""
import copy
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / 'services/ingestion/web'
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.path = self.path.removeprefix('/monitor') or '/'
        super().do_GET()
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(WEB)))
threading.Thread(target=server.serve_forever, daemon=True).start()
origin = f'http://127.0.0.1:{server.server_port}'
FACTS = dict(generatedAt='2026-10-15T06:00:00Z', records=[], summary=dict(total=0, current=0, expired=0, sequenceGaps=0, disagreements=0), scope=dict(limit=1000, shown=0, truncated=False), delivery=dict(queued=0, dead=0, published=0))
REPORTS = [dict(agentId=agent, eligibleIds=['SIM-A'], findings=[dict(id=f'{agent}-finding', code='AVAILABLE', message='<img src=x onerror="window.injected=true">', entityIds=['SIM-A'])]) for agent in ['fleet', 'crew', 'weather', 'airport', 'cargo']]
READY = dict(status='ready', world=dict(simulation=True, runId='fixture-run', revision=0, tick=0, policy=dict(slots=[0,1,2],slotMinutes=30), aircraft=[], crews=[], airports=[], routes=[], weather=[], requests=[dict(id='SIM-R', category='medical', massKg=100, originId='SIM-HUB', destinationId='SIM-CLINIC', priority=5, deadlineSlot=2, temperatureControlled=True)]), plan=dict(status='optimal', assignments=[dict(requestId='SIM-R', aircraftId='SIM-A', crewId='SIM-C', departureSlot=0, arrivalSlot=1)], unserved=[], objective=dict(servedPriority=5,changedAssignments=0,totalArrivalSlots=1), diagnostics=dict(explored=100,limit=100000), agentReports=REPORTS), validation=dict(valid=True,errors=[]), demand=dict(forecast=dict(day=121,demand=42), evaluation=dict(mae=2, baselineMae=5)), annotations=dict(status='ready',mode='deterministic',runId='fixture-run',revision=0,modelsUsed=[], highlights=[dict(agentId='fleet',findingIds=['fleet-finding'],status='deterministic')]), nextPhase='weather-change',history=[], generatedAt='2026-10-15T06:00:00Z')
READY['demand']=dict(modelId='synthetic-demand-ols',simulation=True,forecastDay=120,predictedRequests=42,trainingCount=96,testCount=24,evaluation=dict(mae=2,baselineMae=5))
READY['world']['requests'][0]['validThroughTick']=5
state = dict(sim=copy.deepcopy(READY), sim_status=200, facts_status=200, logout_status=200)
errors=[]
def reply(route, key, status):
    body = state[key] if status == 200 else {'error': {'code':'UNAUTHORIZED' if status == 401 else 'UNAVAILABLE'}}
    route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport=dict(width=1440,height=1000))
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/monitor/api/snapshot*', lambda route: route.fulfill(status=state['facts_status'],content_type='application/json',body=json.dumps(FACTS if state['facts_status']==200 else {'error':{'code':'UNAUTHORIZED'}})))
        page.route('**/monitor/api/simulation', lambda route: reply(route,'sim',state['sim_status']))
        page.route('**/monitor/logout', lambda route: route.fulfill(status=state['logout_status'],content_type='application/json',body='{}'))
        page.route('**/monitor/session', lambda route: route.fulfill(status=200,content_type='application/json',body='{}'))
        page.goto(origin+'/monitor/')
        page.wait_for_load_state('networkidle')
        expect(page.get_by_role('heading',name='Civilian relief simulation',exact=True)).to_be_visible()
        expect(page.locator('#relief-content')).to_contain_text('Exact optimum')
        expect(page.locator('#relief-content')).to_contain_text('fleet-finding')
        expect(page.locator('#relief-content')).to_contain_text('synthetic-demand-ols')
        fleet=page.locator('[data-relief-detail="fleet"] summary')
        fleet.focus(); page.keyboard.press('Enter')
        expect(page.locator('[data-relief-detail="fleet"]')).to_have_attribute('open','')
        assert not page.locator('#relief-content img').count()
        assert page.evaluate('window.injected === undefined')
        def refresh():
            page.get_by_role('button',name='Refresh',exact=True).click()
            expect(page.locator('#refresh')).to_be_enabled()
        state['sim']['plan']['status']='feasible_budget'
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('Budget-limited feasible')
        expect(page.locator('[data-relief-detail="fleet"]')).to_have_attribute('open','')
        state['sim']['annotations'].update(mode='ollama',modelsUsed=['fixture-local-model'])
        state['sim']['annotations']['highlights'][0].update(status='model',model='fixture-local-model')
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('Local LLM evidence selection')
        expect(page.locator('#relief-content')).to_contain_text('fixture-local-model')
        state['sim']['annotations'].update(mode='deterministic-fallback',modelsUsed=[])
        state['sim']['annotations']['highlights'][0].update(status='deterministic-fallback')
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('Provider: deterministic fallback after local model failure')
        state['sim']['annotations']['revision']=99
        state['sim']['annotations']['highlights'][0]['model']='STALE-MODEL'
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('Awaiting annotations for this revision')
        expect(page.locator('#relief-content')).not_to_contain_text('STALE-MODEL')
        state['sim']['annotations']=dict(status='pending',runId='fixture-run',revision=0)
        state['sim']['validation']=dict(valid=False,errors=['DUPLICATE_AIRCRAFT'])
        state['sim']['plan']['assignments']=[]
        state['sim']['plan']['unserved']=[dict(requestId='SIM-R',reasonCodes=['NO_ELIGIBLE_AIRCRAFT'])]
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('DUPLICATE_AIRCRAFT')
        expect(page.locator('#relief-content')).to_contain_text('NO_ELIGIBLE_AIRCRAFT')
        expect(page.locator('#relief-content')).to_contain_text('Annotation pending')
        state['sim']['history']=[dict(revision=0,phase='start',servedPriority=5,assignedCount=1,changedAssignments=0)]
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('Initial scenario')
        for width in (320,768,1024,1440):
            page.set_viewport_size(dict(width=width,height=900))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}'
        artifact=ROOT/'.superpowers/sdd/civilian-relief-engine-plan'
        page.screenshot(path=str(artifact/'ui-desktop.png'),full_page=True)
        page.set_viewport_size(dict(width=320,height=900))
        page.screenshot(path=str(artifact/'ui-mobile.png'),full_page=True)
        state['sim_status']=404
        refresh()
        expect(page.locator('#relief-state')).to_contain_text('not available')
        expect(page.locator('#connection-text')).to_contain_text('Updated')
        assert page.locator('#relief-content').text_content()==''
        state['sim_status']=200; state['sim']=dict(status='idle')
        refresh()
        expect(page.locator('#relief-state')).to_contain_text('No simulation')
        state['sim']=copy.deepcopy(READY)
        refresh()
        expect(page.locator('#relief-content')).to_contain_text('SIM-R')
        state['sim_status']=401
        refresh()
        expect(page.locator('#login-panel')).to_be_visible()
        assert page.locator('#relief-content').text_content()==''
        assert page.locator('#relief-state').text_content()==''
        state['sim_status']=200
        page.get_by_label('Viewer token',exact=True).fill('fixture-only')
        page.get_by_role('button',name='Open session',exact=True).click()
        expect(page.locator('#relief-content')).to_contain_text('SIM-R')
        state['logout_status']=503
        page.get_by_role('button',name='Sign out',exact=True).click()
        expect(page.locator('#connection-text')).to_contain_text('Sign out failed')
        assert page.locator('#relief-content').text_content()==''
        assert page.locator('#relief-state').text_content()==''
        state['logout_status']=200
        page.get_by_role('button',name='Sign out',exact=True).click()
        expect(page.locator('#login-panel')).to_be_visible()
        # A delayed response from the previous poll must never repopulate a cleared view.
        page.get_by_label('Viewer token',exact=True).fill('fixture-only')
        page.get_by_role('button',name='Open session',exact=True).click()
        expect(page.locator('#relief-content')).to_contain_text('SIM-R')
        held=[]
        page.route('**/monitor/api/simulation',lambda route: held.append(route))
        page.get_by_role('button',name='Refresh',exact=True).click()
        page.wait_for_timeout(200)
        assert len(held)==1, 'One active simulation request per poll'
        page.evaluate('document.querySelector("#refresh").dispatchEvent(new Event("click"))')
        page.wait_for_timeout(100)
        assert len(held)==1, 'Overlapping refresh was not suppressed'
        page.get_by_role('button',name='Sign out',exact=True).click()
        expect(page.locator('#login-panel')).to_be_visible()
        try:
            held[0].fulfill(status=200,content_type='application/json',body=json.dumps(READY))
        except Exception:
            pass  # The shared AbortController may already have canceled the held route.
        page.wait_for_timeout(200)
        assert page.locator('#relief-content').text_content()==''
        assert page.locator('#relief-state').text_content()==''
        assert not errors, errors
        assert page.evaluate('Object.keys(localStorage).length')==0
        browser.close()
finally:
    server.shutdown()
print('Relief browser fixtures passed: proposed assignments, exact/budget labels, safe evidence, keyboard disclosure persistence, local/deterministic/fallback models, stale/pending annotations, checker errors, empty plan/history, four viewports, idle/404 isolation, simulation 401, failed/successful logout clearing, nonoverlap and delayed-response discard.')
