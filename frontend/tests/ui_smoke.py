"""Browser integration checks. Run against a built frontend on port 3100.
Uses intercepted API responses; never writes to a real backend.
Run: python frontend/tests/ui_smoke.py
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('UI_TEST_URL', 'http://localhost:3100')
DECISION = dict(id='DEC-1', type='Dispatch', version=2, status='stale', createdAt='2026-10-14', assumptions=[dict(id='A1', description='Reserve available')], dependencies=[dict(inputId='REC-1', inputVersion=3)])
ASSIGNMENT = dict(taskId='T1', resourceId='R1', start=0, end=2)
SCHEDULE = dict(id='SCH-1', version=1, assignments=[ASSIGNMENT], objectives=dict(utilization=75, cost=200), verification='verified')
APPROVAL = dict(id='APP-1', targetId='SCH-1', type='Schedule', status='pending', verification='verified', submittedBy='Planner', submittedAt='2026-10-14', summary='Dispatch review')
RUN = dict(id='RUN-1', scenario='clean', seed=0, faultSeverity='medium', status='running', detectionRate=0, falseAlarms=0, failureRate=0, feasibility=100, recoveryTime=0, baseline=8, createdAt='2026-10-14')
AGENT = dict(id='AGENT-1', status='running', query='Explain DEC-1', nodesVisited=['verifier'], retries=1, explanation='Reserve checked', evidenceLinks=[dict(id='REC-1', label='Validator result', version=3)], createdAt='2026-10-14')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel=os.environ.get('UI_TEST_BROWSER', 'msedge'))
    page = browser.new_page(viewport=dict(width=1440, height=1000))
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    state = dict(outcome='invalid', submissions=[], run_polls=0, agent_polls=0, fail_approval=False, fail_reads=False)
    def route_api(route):
        path = urlparse(route.request.url).path.removeprefix('/api/v1')
        method = route.request.method
        if method == 'OPTIONS':
            route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'})
            return
        status = 200
        data = None
        if path == '/health': data = dict(status='ok', service='test-api')
        elif state['fail_reads'] and method == 'GET': status, data = 503, dict(code='unavailable', message='Service unavailable')
        elif path == '/validity/decisions': data = [DECISION]
        elif path == '/validity/decisions/DEC-1': data = DECISION
        elif path == '/validity/reverify':
            # An API success must not force the decision to verified.
            data = dict(success=True, status='stale')
        elif path == '/ingestion/status': data = [dict(topic='telemetry', status='active', rate='20/s', lag=0, errorCount=2)]
        elif path == '/ingestion/flagged': data = [dict(id='REC-1', source='Telemetry', time='2026-10-14', reason='Stale timestamp', status='Stale', version=3, duplicate=False)]
        elif path == '/evidence/issues': data = [dict(id='REC-1', issueClass='stale', status='open', sourceId='SRC-1', detectedAt='2026-10-14', affectedResource='R1')]
        elif path == '/evidence/issues/REC-1/autopsy': data = dict(issueId='REC-1', issueClass='stale', claims=[dict(id='C1', attribute='capacity', value='4', sourceId='SRC-1', observedAt='2026-10-14')], provenance=[dict(step='Ingested', at='2026-10-14', sourceId='SRC-1')], missingInformation=['Updated timestamp'], uncertainty=[dict(label='Delay', value=0.2)])
        elif path == '/forecasts/FORECAST-01': data = dict(id='FORECAST-01', target='Demand', points=[dict(t='00', mean=5, lower=3, upper=7), dict(t='04', mean=8, lower=6, upper=10)], coverage=88, highUncertainty=True)
        elif path == '/planning/alternatives': data = [SCHEDULE, dict(SCHEDULE, id='SCH-2', objectives=dict(utilization=80, cost=230))]
        elif path in ['/planning/solve', '/planning/schedules/SCH-1']: data = SCHEDULE
        elif path.startswith('/replanning/diff/'): data = dict(added=[ASSIGNMENT], removed=[], moved=[], unchanged=2)
        elif path == '/stress/runs': data = RUN if method == 'POST' else []
        elif path == '/stress/runs/RUN-1':
            state['run_polls'] += 1
            data = dict(RUN, status='completed' if state['run_polls'] >= 2 else 'running')
        elif path == '/agents/requests': data = AGENT if method == 'POST' else []
        elif path == '/agents/requests/AGENT-1':
            state['agent_polls'] += 1
            data = dict(AGENT, status='completed' if state['agent_polls'] >= 2 else 'running')
        elif path == '/approvals': data = [APPROVAL]
        elif path == '/verification/check': data = dict(outcome=state['outcome'], violations=[dict(rule='reserve', message='Review reserve', refs=['REC-1'])] if state['outcome'] == 'invalid' else [], uncertainty_flags=['Capacity uncertain'] if state['outcome'] == 'invalid' else [])
        elif path == '/approvals/APP-1/decision':
            state['submissions'].append(route.request.post_data_json)
            status, data = (503, dict(code='unavailable', message='Review service unavailable')) if state['fail_approval'] else (200, dict(APPROVAL, status=route.request.post_data_json['decision']))
        elif path == '/audit': data = [dict(id='AUD-1', entity='DEC-1 REC-1 SCH-1', action='Status changed to stale', actor='Verifier', timestamp='2026-10-14T10:00:00Z')]
        elif path == '/benchmarks/results': data = [dict(metric='Detection', system=90, baseline=70, effectSize='0.8', pValue=0.02, ci=[0.4, 1.2])]
        elif path == '/benchmarks/ablations': data = [dict(name='Full system', accuracy='90%', recoveryTime='2s', feasibility='100%')]
        else: status, data = 404, dict(code='not_found', message=path)
        route.fulfill(status=status, content_type='application/json', body=json.dumps(data), headers={'Access-Control-Allow-Origin': '*'})
    page.route('http://localhost:8000/**', route_api)
    page.goto(BASE + '/', wait_until='networkidle')
    expect(page.get_by_label('Dashboard data source')).to_have_value('demo')
    page.get_by_label('Dashboard data source').select_option('live')
    expect(page.locator('.source-column')).to_have_count(1)
    expect(page.locator('.dashboard-data-note')).to_contain_text('Live workspace')
    page.get_by_label('Dashboard data source').select_option('demo')
    expect(page.locator('.source-column')).to_have_count(4)
    page.get_by_label('Forecast time window').select_option('12')
    expect(page.get_by_label('Forecast time window')).to_have_value('12')
    page.get_by_label('Forecast time window').select_option('24')
    page.get_by_role('button', name='Workspace settings').click()
    expect(page.locator('.workspace-popover')).to_be_visible()
    page.get_by_role('button', name='Close settings').click()
    page.get_by_label('Search routes').fill('ingestion')
    page.locator('.search-results').get_by_role('link').click()
    expect(page).to_have_url(BASE + '/ingestion')
    page.get_by_label('Workspace data source').select_option('live')
    routes = ['/', '/ingestion', '/evidence', '/evidence/REC-1', '/validity', '/validity/DEC-1', '/forecasts', '/planning', '/planning/compare', '/stress-lab', '/explanations', '/approvals', '/audit', '/benchmarks']
    for path in routes:
        page.goto(BASE + path, wait_until='networkidle')
        expect(page.locator('h1')).to_be_visible()
        assert not [text for text in page.get_by_role('alert').all_inner_texts() if text.strip()] or path == '/forecasts', (path, page.get_by_role('alert').all_inner_texts())
    page.goto(BASE + '/evidence', wait_until='networkidle')
    page.get_by_role('button', name='conflict', exact=True).click()
    expect(page.get_by_text('No results', exact=True)).to_be_visible()
    page.goto(BASE + '/validity/DEC-1', wait_until='networkidle')
    page.get_by_role('button', name='Re-verify', exact=True).click()
    expect(page.get_by_text('stale', exact=True)).to_be_visible()
    page.goto(BASE + '/planning', wait_until='networkidle')
    page.get_by_role('button', name='Run Optimisation').click()
    expect(page.get_by_text('T1', exact=True)).to_be_visible()
    page.goto(BASE + '/planning/compare', wait_until='networkidle')
    page.get_by_label('Original schedule').fill('SCH-1')
    page.get_by_label('New schedule').fill('SCH-2')
    page.get_by_role('button', name='Compare', exact=True).click()
    expect(page.locator('p[role="status"]')).to_contain_text('1 added')
    page.goto(BASE + '/stress-lab', wait_until='networkidle')
    page.get_by_label('Seed', exact=True).fill('0')
    page.get_by_role('button', name='Launch stress run').click()
    expect(page.locator('p[role="status"]')).to_contain_text('completed', timeout=10000)
    count = state['run_polls']
    page.wait_for_timeout(1900)
    assert state['run_polls'] == count, 'Stress polling continued after completion'
    expect(page.get_by_text('0%', exact=True).first).to_be_visible()
    page.goto(BASE + '/explanations', wait_until='networkidle')
    page.get_by_label('Agent question').fill('Explain DEC-1')
    page.get_by_role('button', name='Ask Agent').click()
    expect(page.get_by_text('COMPLETED', exact=True)).to_be_visible(timeout=10000)
    count = state['agent_polls']
    page.wait_for_timeout(1900)
    assert state['agent_polls'] == count, 'Agent polling continued after completion'
    page.goto(BASE + '/approvals', wait_until='networkidle')
    page.get_by_role('button', name='Review', exact=True).click()
    expect(page.get_by_role('button', name='Approve Result')).to_be_disabled()
    page.get_by_role('button', name='Close review').click()
    state['outcome'] = 'verified'
    page.get_by_role('button', name='Review', exact=True).click()
    expect(page.get_by_role('button', name='Approve Result')).to_be_enabled()
    page.get_by_role('button', name='Approve Result').click()
    expect(page.get_by_role('alert').filter(has_text='mandatory')).to_be_visible()
    assert not state['submissions']
    page.get_by_label('Reviewer name', exact=True).fill('Tester')
    page.get_by_label('Decision rationale', exact=True).fill('Verified evidence reviewed')
    state['fail_approval'] = True
    page.get_by_role('button', name='Approve Result').click()
    expect(page.get_by_role('alert').filter(has_text='Review submission')).to_contain_text('This action could not be confirmed')
    expect(page.get_by_label('Decision rationale', exact=True)).to_have_value('Verified evidence reviewed')
    state['fail_approval'] = False
    page.get_by_role('button', name='Approve Result').click()
    expect(page.get_by_label('Decision rationale', exact=True)).to_have_count(0)
    assert state['submissions'][-1]['rationale'] == 'Verified evidence reviewed'
    page.goto(BASE + '/audit?entity=missing', wait_until='networkidle')
    expect(page.get_by_text('No results', exact=True)).to_be_visible()
    state['fail_reads'] = True
    page.goto(BASE + '/ingestion', wait_until='networkidle')
    expect(page.get_by_role('alert').first).to_contain_text('Service temporarily unavailable')
    state['fail_reads'] = False
    page.get_by_role('button', name='Refresh', exact=True).click()
    expect(page.get_by_text('telemetry', exact=True)).to_be_visible()
    page.set_viewport_size(dict(width=390, height=844))
    page.goto(BASE + '/', wait_until='networkidle')
    page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
    page.get_by_role('button', name='Toggle navigation').click()
    expect(page.get_by_role('navigation', name='Main navigation')).to_be_visible()
    page.get_by_role('navigation').get_by_role('link', name='Ingestion', exact=True).click()
    expect(page.locator('h1')).to_contain_text('Ingestion')
    assert not errors, errors
    output = Path('frontend/test-results')
    output.mkdir(exist_ok=True)
    page.screenshot(path=str(output / 'ingestion-mobile.png'), full_page=True)
    page.set_viewport_size(dict(width=1591, height=960))
    page.goto(BASE + '/', wait_until='networkidle')
    page.screenshot(path=str(output / 'overview.png'), full_page=True)
    browser.close()
    print('PASS: demo/live toggle; time window; search; settings; 14 routes; evidence filters; reverify; solve; compare; polling; approval gates, rationale and failures; audit filter; API retry; mobile navigation.')


