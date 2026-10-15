"""Local Chromium contracts for the read-only contract-net negotiation viewer."""
import argparse
import copy
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mutate-grounding', action='store_true', help='Serve a bypassed finding filter; this negative control must fail.')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / 'services/ingestion/web'
ARTIFACT = ROOT / '.superpowers/sdd/civilian-negotiation-plan'
NOW = '2026-10-15T06:00:00Z'
HTML = '<img src=x onerror="window.injected=true">'
AGENTS = ['fleet', 'crew', 'weather', 'airport', 'cargo']
ASSIGNMENT = dict(requestId='SIM-R', aircraftId='SIM-A', crewId='SIM-C', departureSlot=0, arrivalSlot=1)
CANDIDATE = 'SIM-CAND-R~A~C~0~1'
FACTS = dict(generatedAt=NOW, records=[], summary=dict(total=0, current=0, expired=0, sequenceGaps=0, disagreements=0), scope=dict(limit=1000, shown=0, truncated=False), delivery=dict(queued=0, dead=0, published=0))
READY = dict(status='ready', generatedAt=NOW, nextPhase=None, history=[], validation=dict(valid=True, errors=[]), world=dict(simulation=True, runId='fixture-run', revision=3, tick=0, policy=dict(slots=[0, 1, 2], slotMinutes=30), aircraft=[dict(id='SIM-A')], crews=[dict(id='SIM-C')], airports=[dict(id='SIM-HUB'), dict(id='SIM-CLINIC')], weather=[], routes=[dict(originId='SIM-HUB', destinationId='SIM-CLINIC', durationSlots=1)], requests=[dict(id='SIM-R', originId='SIM-HUB', destinationId='SIM-CLINIC', priority=5)]), plan=dict(status='optimal', assignments=[ASSIGNMENT], unserved=[], objective=dict(servedPriority=5, changedAssignments=0, totalArrivalSlots=1), diagnostics=dict(nodesExplored=100, nodeLimit=100000), agentReports=[dict(agentId=agent, findings=[dict(id=f'{agent}-finding', code='AVAILABLE', message='Canonical finding', entityIds=['SIM-A'])]) for agent in AGENTS]))
messages = [dict(id=f'fixture-run-r3-message-{index}', round=1, requestId='SIM-R', proposalId='SIM-PROP-fixture-run-3-R-1', **{'from': 'cargo' if index % 10 < 2 else 'fleet', 'to': 'supervisor'}, kind=kind, entityIds=['SIM-A', 'UNKNOWN-ENTITY'], findingIds=['fleet-finding', 'UNKNOWN-FINDING'], ruleCodes=['CAPACITY'], summary=HTML + ' Evidence summary ' * 8, candidateId=CANDIDATE, candidateIds=[CANDIDATE], assignment=ASSIGNMENT) for index, kind in enumerate(['cfp', 'proposal', 'accept', 'reject', 'bid', 'counterproposal', 'commit', 'defer', 'resolution', 'accept'] * 4)]
messages.extend([
    dict(messages[0], id='bad-actor', to='UNKNOWN-RECIPIENT', summary='BAD-ACTOR'),
    dict(messages[0], id='bad-kind', kind='execute-tool', summary='BAD-KIND'),
    dict(messages[0], id='bad-assignment', assignment=dict(ASSIGNMENT, aircraftId='UNKNOWN-AIRCRAFT'), summary='BAD-ASSIGNMENT'),
    dict(messages[0], id='bad-candidate', candidateId='UNKNOWN-CANDIDATE', summary='BAD-CANDIDATE'),
])
READY['negotiation'] = dict(version=1, runId='fixture-run', revision=3, mode='deterministic-autonomous', topology='fully-connected-peers', settings=dict(enabled=True, maxRounds=4, maxMessages=64), status='agreed', roundsCompleted=4, requests=[dict(requestId='SIM-R', status='agreed', rounds=4, assignment=ASSIGNMENT), dict(requestId='UNKNOWN-REQUEST', status='agreed', rounds=4)], agentStates=[dict(agentId=agent, acceptedProposalIds=['SIM-PROP-fixture-run-3-R-1', 'UNKNOWN-PROPOSAL'], rejectedProposalIds=[], bidsSent=2) for agent in AGENTS] + [dict(agentId='UNKNOWN-AGENT')], messages=messages, assignments=[ASSIGNMENT, dict(ASSIGNMENT, crewId='UNKNOWN-CREW')], outcome=dict(status='solver-refined', seedServedPriority=4, finalServedPriority=5, verified=True))
state = dict(sim=copy.deepcopy(READY), status=200)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.path = self.path.removeprefix('/monitor') or '/'
        if args.mutate_grounding and self.path.split('?')[0] == '/relief.js':
            original = (WEB / 'relief.js').read_text(encoding='utf-8')
            mutated = original.replace('grounded(message.findingIds, refs.knownFindings)', 'list(message.findingIds)')
            assert mutated != original, 'Grounding mutation target was not found'
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript')
            self.end_headers()
            self.wfile.write(mutated.encode('utf-8'))
            return
        super().do_GET()

    def log_message(self, *unused):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(WEB)))
threading.Thread(target=server.serve_forever, daemon=True).start()
errors, writes = [], []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1000))
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: writes.append(request.url) if request.method != 'GET' and '/monitor/session' not in request.url and '/monitor/logout' not in request.url else None)
        page.route('**/monitor/api/snapshot*', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(FACTS)))
        page.route('**/monitor/api/simulation', lambda route: route.fulfill(status=state['status'], content_type='application/json', body=json.dumps(state['sim'] if state['status'] == 200 else {'error': {'code': 'UNAUTHORIZED'}})))
        page.route('**/monitor/session', lambda route: route.fulfill(status=200, content_type='application/json', body='{}'))
        page.route('**/monitor/logout', lambda route: route.fulfill(status=200, content_type='application/json', body='{}'))
        page.goto(f'http://127.0.0.1:{server.server_port}/monitor/')
        page.wait_for_load_state('networkidle')
        panel = page.locator('#relief-negotiation')
        expect(panel).to_be_visible()
        expect(panel).to_contain_text('Deterministic policies make negotiation decisions')
        expect(panel).to_contain_text('Optimizer refined negotiated seed')
        def metric(label):
            return panel.get_by_text(label, exact=True).locator('xpath=following-sibling::dd[1]')
        expect(metric('Messages used / budget')).to_have_text('44 / 64')
        expect(metric('Maximum rounds per request')).to_have_text('4')
        expect(metric('Negotiated seed served priority')).to_have_text('4')
        expect(metric('Optimizer final served priority')).to_have_text('5')
        expect(metric('Outcome independently verified')).to_have_text('Yes')
        expect(panel).to_contain_text('fleet-finding')
        for forbidden in ['UNKNOWN-', 'BAD-ACTOR', 'BAD-KIND', 'BAD-ASSIGNMENT', 'BAD-CANDIDATE']:
            expect(panel).not_to_contain_text(forbidden)
        assert panel.locator('img, script, iframe, a, button, input, select').count() == 0
        assert page.evaluate('window.injected === undefined')
        expect(panel.locator('#relief-table-negotiation-messages tbody tr')).to_have_count(40)
        expect(panel.locator('#relief-table-negotiation-agents tbody tr')).to_have_count(5)
        expect(panel.locator('#relief-table-negotiation-seed tbody tr')).to_have_count(1)
        expect(panel).to_contain_text('Unsupported or ungrounded references were omitted')

        def refresh():
            with page.expect_response(lambda response: '/monitor/api/simulation' in response.url):
                page.evaluate('document.querySelector("#refresh").dispatchEvent(new Event("click"))')
            expect(page.locator('#refresh')).to_be_enabled()

        ledger = panel.locator('[data-relief-detail="negotiation"]')
        summary = ledger.locator('summary')
        summary.focus(); page.keyboard.press('Enter')
        expect(ledger).to_have_attribute('open', '')
        for kind in ['Proposal', 'Objection', 'Counterproposal', 'Commit']:
            expect(panel.locator('#relief-table-negotiation-messages')).to_contain_text(kind)
        refresh(); expect(summary).to_be_focused()
        page.set_viewport_size(dict(width=320, height=900))
        table = panel.locator('#relief-table-negotiation-messages')
        table.focus(); table.evaluate('(element) => { element.scrollLeft=180; element.scrollTop=100; }')
        position = table.evaluate('(element) => [element.scrollLeft, element.scrollTop]')
        assert all(number > 0 for number in position)
        refresh(); expect(table).to_be_focused()
        assert table.evaluate('(element) => [element.scrollLeft, element.scrollTop]') == position
        with page.expect_response(lambda response: '/monitor/api/simulation' in response.url):
            page.wait_for_timeout(5200)
        expect(table).to_be_focused()
        assert table.evaluate('(element) => [element.scrollLeft, element.scrollTop]') == position
        state['sim']['world']['revision'] = 4
        state['sim']['negotiation']['revision'] = 4
        for message in state['sim']['negotiation']['messages']:
            message['proposalId'] = 'SIM-PROP-fixture-run-4-R-1'
        for agent in state['sim']['negotiation']['agentStates']:
            agent['acceptedProposalIds'] = ['SIM-PROP-fixture-run-4-R-1']
        refresh(); expect(table).to_be_focused()
        expect(ledger).to_have_attribute('open', '')

        ARTIFACT.mkdir(parents=True, exist_ok=True)
        for width in [320, 768, 1024, 1440]:
            page.set_viewport_size(dict(width=width, height=1000))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}'
            if width in [320, 1440]:
                panel.screenshot(path=str(ARTIFACT / f'negotiation-ui-{width}.png'))

        for status in ['partial', 'no_agreement', 'budget_exhausted', 'failed', 'disabled']:
            state['sim']['negotiation']['status'] = status
            refresh(); expect(panel).to_contain_text(status.replace('_', ' ').capitalize())
        for outcome, label in [('seed-retained', 'Negotiated seed retained'), ('deterministic-fallback', 'Deterministic optimizer fallback'), ('disabled', 'Negotiation disabled')]:
            state['sim']['negotiation']['outcome']['status'] = outcome
            refresh(); expect(panel).to_contain_text(label)
        state['sim']['planUsable'] = False
        state['sim']['inputFreshness'] = dict(status='expired', expiredCount=1, replanPending=True)
        refresh(); expect(panel).to_contain_text('Historical negotiation only')
        expect(panel).to_contain_text('Historical outcome')
        expect(panel).to_contain_text('Historical negotiated seed')
        panel.screenshot(path=str(ARTIFACT / 'negotiation-ui-historical.png'))
        state['sim']['negotiation']['runId'] = 'different-run'
        table.focus(); refresh()
        expect(panel).to_contain_text('No negotiation report for this run and revision')
        expect(panel).not_to_contain_text('SIM-PROP-fixture-run-3-R-1')
        expect(page.locator('#relief-title')).to_be_focused()
        state['sim']['negotiation'].update(runId='fixture-run', revision=99)
        refresh(); expect(panel).not_to_contain_text('fleet-finding')
        state['sim']['negotiation'] = copy.deepcopy(READY['negotiation'])
        state['sim']['world']['revision'] = 3
        state['sim']['negotiation']['messages'] = []
        refresh(); expect(panel).to_contain_text('No supported negotiation messages reported')
        state['sim'].pop('negotiation')
        refresh(); expect(panel).to_have_count(0)
        expect(page.locator('#relief-content')).to_contain_text('Historical assignments')
        state['sim'] = copy.deepcopy(READY)
        refresh(); expect(panel).to_be_visible()
        state['status'] = 401
        refresh(); expect(page.locator('#login-panel')).to_be_visible()
        expect(page.locator('#relief-content')).to_be_empty()
        state['status'] = 200
        page.get_by_label('Viewer token', exact=True).fill('fixture-only')
        page.get_by_role('button', name='Open session', exact=True).click()
        expect(panel).to_be_visible()
        page.get_by_role('button', name='Sign out', exact=True).click()
        expect(page.locator('#relief-content')).to_be_empty()
        assert not errors, errors
        assert not writes, writes
        browser.close()
finally:
    server.shutdown(); server.server_close()
print('Negotiation UI fixtures passed: typed transcript, grounded references, agent activity, budgets/outcomes, history/staleness, safe DOM, keyboard/scroll/timer preservation, four viewports, legacy/empty states, auth clearing and no writes.')
